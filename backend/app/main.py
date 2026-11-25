import logging
import os, smtplib, ssl
from email.message import EmailMessage
from pathlib import Path
from typing import List
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from .database import Base, engine, get_db
from . import models, schemas
from .parser import extract_text, parse_resume
from .matching import score_candidate
from .security import current_user, require_admin, hash_password, verify_password, create_token, audit
from .ai_interviews import router as ai_interview_router

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)
# Lightweight forward migration for databases created by the earlier MVP schema.
from sqlalchemy import inspect as sa_inspect
with engine.begin() as conn:
    existing = {c["name"] for c in sa_inspect(engine).get_columns("candidates")}
    for column, ddl in [("skill_evidence", "JSON"), ("sections", "JSON")]:
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE candidates ADD COLUMN {column} {ddl}")
app = FastAPI(title="HireSwift 360 API", version="0.2.0", description="Secure multi-tenant talent intelligence platform")
origins = [
    x.strip()
    for x in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    ).split(",")
    if x.strip()
]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET","POST","PATCH","OPTIONS"], allow_headers=["Authorization","Content-Type","X-Interview-Token"])
app.include_router(ai_interview_router)

@app.get("/health")
@app.get("/api/health")
def health(): return {"status":"ok", "service":"HireSwift 360 API", "version":"0.2.0"}

@app.post("/api/auth/register")
def register(payload: schemas.RegisterInput, db: Session = Depends(get_db)):
    email = payload.email.lower()
    if db.query(models.User).filter(func.lower(models.User.email) == email).first(): raise HTTPException(409, "An account with this email already exists")
    company = models.Company(name=payload.company_name.strip()); db.add(company); db.flush()
    user = models.User(company_id=company.id, full_name=payload.full_name.strip(), email=email, password_hash=hash_password(payload.password), role="admin")
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token":create_token(user), "token_type":"bearer", "user":user_out(user), "company":{"id":company.id,"name":company.name}}

@app.post("/api/auth/login")
def login(payload: schemas.LoginInput, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active: raise HTTPException(401, "Incorrect email or password")
    return {"access_token":create_token(user), "token_type":"bearer", "user":user_out(user), "company":{"id":user.company_id,"name":user.company.name}}

def user_out(u): return {"id":u.id,"company_id":u.company_id,"full_name":u.full_name,"email":u.email,"role":u.role}
def job_out(j): return {"id":j.id,"title":j.title,"department":j.department,"description":j.description,"required_skills":j.required_skills or [],"min_experience":j.min_experience,"min_10th":j.min_10th,"min_12th":j.min_12th,"min_cgpa":j.min_cgpa,"location":j.location,"created_at":j.created_at}
def candidate_out(c, include_resume=False):
    out={"id":c.id,"full_name":c.full_name,"email":c.email,"phone":c.phone,"location":c.location,"education":c.education,"graduation_year":c.graduation_year,"tenth_percentage":c.tenth_percentage,"twelfth_percentage":c.twelfth_percentage,"cgpa":c.cgpa,"experience_years":c.experience_years,"skills":c.skills or [],"skill_evidence":c.skill_evidence or {},"sections":c.sections or {},"resume_filename":c.resume_filename,"status":c.status}
    if include_resume: out["resume_text"]=c.resume_text
    return out

def owned_job(db, job_id, user):
    obj=db.query(models.Job).filter(models.Job.id==job_id,models.Job.company_id==user.company_id).first()
    if not obj: raise HTTPException(404,"Job not found")
    return obj

def owned_candidate(db, candidate_id, user):
    obj=db.query(models.Candidate).filter(models.Candidate.id==candidate_id,models.Candidate.company_id==user.company_id).first()
    if not obj: raise HTTPException(404,"Candidate not found")
    return obj

@app.get("/api/auth/me")
def me(user: models.User=Depends(current_user)): return {"user":user_out(user),"company":{"id":user.company_id,"name":user.company.name}}

@app.post("/api/jobs")
def create_job(payload: schemas.JobCreate, db: Session=Depends(get_db), user: models.User=Depends(current_user)):
    job=models.Job(company_id=user.company_id,**payload.model_dump()); db.add(job); db.flush(); audit(db,user,"job.created","job",job.id,{"title":job.title}); db.commit(); db.refresh(job); return job_out(job)

@app.get("/api/jobs")
def list_jobs(db: Session=Depends(get_db), user: models.User=Depends(current_user)):
    return [job_out(j) for j in db.query(models.Job).filter(models.Job.company_id==user.company_id).order_by(models.Job.id.desc()).all()]

@app.post("/api/candidates/upload")
async def upload_resumes(files: List[UploadFile]=File(...), db: Session=Depends(get_db), user: models.User=Depends(current_user)):
    if len(files)>100: raise HTTPException(413,"Upload up to 100 resumes per batch")
    results,errors=[],[]
    for file in files:
        try:
            filename=Path(file.filename or "resume").name
            if Path(filename).suffix.lower() not in {".pdf",".docx"}: raise ValueError("Only PDF and DOCX files are supported")
            content=await file.read()
            if len(content)>8*1024*1024: raise ValueError("File exceeds 8 MB limit")
            text=extract_text(filename,content)
            if not text.strip(): raise ValueError("No selectable text found. OCR for scanned PDFs is not enabled yet")
            parsed=parse_resume(text)
            existing=None
            if parsed["email"]: existing=db.query(models.Candidate).filter(models.Candidate.company_id==user.company_id,func.lower(models.Candidate.email)==parsed["email"].lower()).first()
            if existing: errors.append({"filename":filename,"error":"Possible duplicate: email already exists","candidate_id":existing.id}); continue
            c=models.Candidate(company_id=user.company_id,resume_filename=filename,resume_text=text[:100000],**parsed)
            db.add(c); db.flush(); results.append(candidate_out(c))
        except Exception as exc: errors.append({"filename":file.filename,"error":str(exc)[:250]})
    audit(db,user,"resume.batch_uploaded","candidate",details={"uploaded":len(results),"errors":len(errors)})
    db.commit(); return {"uploaded":len(results),"candidates":results,"errors":errors}

@app.get("/api/candidates")
def list_candidates(q:str="",skill:str="",min_experience:float=0,graduation_year:int|None=None,status:str="",db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    query=db.query(models.Candidate).filter(models.Candidate.company_id==user.company_id)
    if q: query=query.filter(or_(models.Candidate.full_name.ilike(f"%{q}%"),models.Candidate.email.ilike(f"%{q}%")))
    if min_experience: query=query.filter(models.Candidate.experience_years>=min_experience)
    if graduation_year: query=query.filter(models.Candidate.graduation_year==graduation_year)
    if status: query=query.filter(models.Candidate.status==status)
    items=query.order_by(models.Candidate.created_at.desc()).all()
    if skill: items=[c for c in items if skill.lower() in [s.lower() for s in (c.skills or [])]]
    return [candidate_out(c) for c in items]

@app.get("/api/candidates/compare")
def compare_candidates(ids:str=Query(...,description="Comma-separated candidate IDs; maximum 5"),db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    try: parsed=list(dict.fromkeys(int(x) for x in ids.split(",")))
    except ValueError: raise HTTPException(400,"Candidate IDs must be integers")
    if not 2<=len(parsed)<=5: raise HTTPException(400,"Compare between 2 and 5 candidates")
    found=db.query(models.Candidate).filter(models.Candidate.company_id==user.company_id,models.Candidate.id.in_(parsed)).all()
    if len(found)!=len(parsed): raise HTTPException(404,"One or more candidates not found in this workspace")
    audit(db,user,"candidates.compared","candidate",details={"candidate_ids":parsed}); db.commit()
    return {"candidates":[candidate_out(c,True) for c in found],"comparison_fields":["skills","experience_years","education","graduation_year","location","status"]}


@app.get("/api/candidates/{candidate_id}")
def get_candidate(candidate_id:int,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    return candidate_out(owned_candidate(db,candidate_id,user),True)

@app.patch("/api/candidates/{candidate_id}/status")
def update_status(candidate_id:int,payload:schemas.StatusUpdate,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    allowed={"Applied","Shortlisted","Interview","Offer","Rejected","Hired"}
    if payload.status not in allowed: raise HTTPException(400,f"Status must be one of: {', '.join(sorted(allowed))}")
    c=owned_candidate(db,candidate_id,user); old=c.status; c.status=payload.status
    audit(db,user,"candidate.status_changed","candidate",c.id,{"from":old,"to":c.status}); db.commit(); return candidate_out(c)

@app.post("/api/jobs/{job_id}/match")
def match_job(job_id:int,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    job=owned_job(db,job_id,user); candidates=db.query(models.Candidate).filter(models.Candidate.company_id==user.company_id).all(); output=[]
    for c in candidates:
        score,breakdown,matched,missing=score_candidate(c,job)
        match=db.query(models.CandidateMatch).filter_by(candidate_id=c.id,job_id=job.id).first()
        if not match: match=models.CandidateMatch(candidate_id=c.id,job_id=job.id); db.add(match)
        match.score,match.breakdown,match.matched_skills,match.missing_skills=score,breakdown,matched,missing
        output.append({**candidate_out(c),"score":score,"breakdown":breakdown,"matched_skills":matched,"missing_skills":missing})
    audit(db,user,"matching.completed","job",job.id,{"candidate_count":len(output),"scoring":"Local TF-IDF + explicit criteria"}); db.commit(); output.sort(key=lambda x:x["score"],reverse=True)
    return {"job":job_out(job),"count":len(output),"ranked_candidates":output}

@app.get("/api/jobs/{job_id}/matches")
def get_matches(job_id:int,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    owned_job(db,job_id,user)
    rows=db.query(models.CandidateMatch).join(models.Candidate).filter(models.CandidateMatch.job_id==job_id,models.Candidate.company_id==user.company_id).order_by(models.CandidateMatch.score.desc()).all()
    return [{**candidate_out(r.candidate),"score":r.score,"breakdown":r.breakdown,"matched_skills":r.matched_skills,"missing_skills":r.missing_skills} for r in rows]


@app.post("/api/interviews")
def create_interview(payload:schemas.InterviewCreate,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    candidate=owned_candidate(db,payload.candidate_id,user)
    if payload.job_id is not None: owned_job(db,payload.job_id,user)
    interview=models.Interview(company_id=user.company_id,**payload.model_dump()); db.add(interview); db.flush()
    audit(db,user,"interview.scheduled","interview",interview.id,{"candidate_id":candidate.id}); db.commit(); db.refresh(interview)
    return interview_out(interview)

def interview_out(i): return {"id":i.id,"candidate_id":i.candidate_id,"candidate_name":i.candidate.full_name,"job_id":i.job_id,"interviewer":i.interviewer,"scheduled_at":i.scheduled_at,"duration_minutes":i.duration_minutes,"meeting_url":i.meeting_url,"notes":i.notes,"status":i.status}

@app.get("/api/interviews")
def list_interviews(db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    rows=db.query(models.Interview).filter(models.Interview.company_id==user.company_id).order_by(models.Interview.scheduled_at.asc()).all()
    return [interview_out(i) for i in rows]

def email_settings():
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        return {"configured": False, "missing": missing}
    try:
        port = int(os.environ["SMTP_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        return {"configured": False, "error": "SMTP_PORT must be a number from 1 to 65535"}
    return {
        "configured": True,
        "missing": [],
        "use_ssl": os.getenv("SMTP_USE_SSL", "false").lower() == "true",
    }

@app.get("/api/email/status")
def email_status(user:models.User=Depends(current_user)):
    return email_settings()

@app.patch("/api/interviews/{interview_id}")
def update_interview(interview_id:int,payload:schemas.InterviewUpdate,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    i=db.query(models.Interview).filter(models.Interview.id==interview_id,models.Interview.company_id==user.company_id).first()
    if not i: raise HTTPException(404,"Interview not found")
    data=payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in {"Scheduled","Completed","Cancelled","No-show"}: raise HTTPException(400,"Invalid interview status")
    for k,v in data.items(): setattr(i,k,v)
    audit(db,user,"interview.updated","interview",i.id,data); db.commit(); return interview_out(i)

@app.post("/api/interviews/{interview_id}/email")
def email_interview(interview_id:int,db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    i=db.query(models.Interview).filter(models.Interview.id==interview_id,models.Interview.company_id==user.company_id).first()
    if not i: raise HTTPException(404,"Interview not found")
    if not i.candidate.email: raise HTTPException(400,"Candidate email is not available")
    settings = email_settings()
    if not settings["configured"]:
        detail = settings.get("error") or (
            "Email is not configured. Set these variables in backend/.env and restart the backend: "
            + ", ".join(settings["missing"])
        )
        raise HTTPException(503, detail)
    msg=EmailMessage(); msg["Subject"]="Interview invitation"; msg["From"]=os.environ["MAIL_FROM"]; msg["To"]=i.candidate.email
    msg.set_content(f"Hello {i.candidate.full_name},\n\nYour interview has been scheduled.\nDate/time: {i.scheduled_at}\nDuration: {i.duration_minutes} minutes\nInterviewer: {i.interviewer or 'Hiring team'}\nMeeting link: {i.meeting_url or 'To be shared'}\n\nRegards,\n{user.company.name} Recruitment Team")
    try:
        host, port = os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])
        smtp_class = smtplib.SMTP_SSL if settings["use_ssl"] else smtplib.SMTP
        with smtp_class(host, port, timeout=20, **(
            {"context": ssl.create_default_context()} if settings["use_ssl"] else {}
        )) as server:
            if not settings["use_ssl"]:
                server.starttls(context=ssl.create_default_context())
            server.login(os.environ["SMTP_USER"],os.environ["SMTP_PASSWORD"])
            refused = server.send_message(msg)
            if refused:
                logger.error("SMTP server refused interview invitation recipient(s): %s", list(refused))
                raise HTTPException(502, "Mail server refused the candidate's email address")
    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP authentication failed while sending interview invitation")
        raise HTTPException(502, "Email provider rejected SMTP credentials; verify SMTP_USER and SMTP_PASSWORD") from exc
    except HTTPException:
        raise
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        logger.exception("SMTP delivery failed while sending interview invitation")
        raise HTTPException(502, "Could not deliver the invitation; verify SMTP_HOST, SMTP_PORT, and TLS settings") from exc
    audit(db,user,"interview.invitation_sent","interview",i.id,{"recipient":i.candidate.email}); db.commit(); return {"sent":True}

@app.get("/api/analytics")
def analytics(db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    candidates=db.query(models.Candidate).filter(models.Candidate.company_id==user.company_id).all()
    jobs=db.query(models.Job).filter(models.Job.company_id==user.company_id).count()
    stages={s:sum(1 for c in candidates if c.status==s) for s in ["Applied","Shortlisted","Interview","Offer","Hired","Rejected"]}
    interviews=db.query(models.Interview).filter(models.Interview.company_id==user.company_id).count()
    return {"total_candidates":len(candidates),"active_jobs":jobs,"interviews":interviews,"stages":stages,
            "conversion":{"applied_to_shortlisted":round(stages["Shortlisted"]/max(1,len(candidates))*100,1),"shortlisted_to_interview":round(stages["Interview"]/max(1,stages["Shortlisted"])*100,1),"interview_to_offer":round(stages["Offer"]/max(1,stages["Interview"])*100,1)}}

@app.get("/api/dashboard")
def dashboard(db:Session=Depends(get_db),user:models.User=Depends(current_user)):
    return analytics(db,user)

@app.get("/api/audit-logs")
def audit_logs(limit:int=Query(100,ge=1,le=500),db:Session=Depends(get_db),user:models.User=Depends(require_admin)):
    rows=db.query(models.AuditLog).filter(models.AuditLog.company_id==user.company_id).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
    return [{"id":r.id,"user_id":r.user_id,"action":r.action,"entity_type":r.entity_type,"entity_id":r.entity_id,"details":r.details,"created_at":r.created_at} for r in rows]
