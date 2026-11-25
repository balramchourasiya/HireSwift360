import hashlib
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import audit, current_user

router = APIRouter(prefix="/api")

CODE_SKILLS = {
    "python", "javascript", "typescript", "java", "c", "c++", "c#", "go",
    "rust", "sql", "ruby", "php", "kotlin", "swift",
}
CODING_TEST_CASES = [
    {"input": "[3, 1, 3]", "expected_output": "[1, 3]"},
    {"input": "[]", "expected_output": "[]"},
]
DISCLOSURE = (
    "This interview stores your answers, code submissions, and a text transcript. "
    "You may choose text or browser voice transcription. This app does not record or "
    "store audio; browser speech recognition may process audio according to your browser "
    "provider's policies. Your responses will be shared with the hiring team. "
    "The report is decision support only and does not make hiring decisions."
)


class CreateAIInterview(BaseModel):
    candidate_id: int
    job_id: int


class ConsentInput(BaseModel):
    consent: bool
    modality: str = Field(pattern="^(text|voice)$")


class AnswerInput(BaseModel):
    answer: str = Field(default="", max_length=12000)
    code: str = Field(default="", max_length=20000)
    language: str = Field(default="javascript", max_length=40)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _public_token(header_token: str | None) -> str:
    if not header_token:
        raise HTTPException(401, "Interview link is invalid or expired")
    return header_token


def _load_public(db: Session, token: str) -> models.AIInterview:
    interview = db.query(models.AIInterview).filter(
        models.AIInterview.token_hash == _token_hash(token)
    ).first()
    if not interview:
        raise HTTPException(404, "Interview link is invalid or expired")
    return interview


def _generate_questions(job: models.Job) -> list[dict]:
    questions = [{
        "id": "experience",
        "type": "experience",
        "prompt": f"Please introduce yourself and describe the experience most relevant to the {job.title} role.",
        "expected_concepts": [job.title, *((job.required_skills or [])[:3])],
        "followup_prompt": "Could you give a specific example of your contribution and its outcome?",
        "followup_asked": False,
    }]
    for index, skill in enumerate((job.required_skills or [])[:4]):
        questions.append({
            "id": f"technical-{index + 1}",
            "type": "technical",
            "skill": skill,
            "prompt": f"Tell us how you have used {skill} in a project. What decisions or trade-offs did you make?",
            "expected_concepts": [skill],
            "followup_prompt": f"Could you walk through a concrete {skill} example and explain your specific contribution?",
            "followup_asked": False,
        })
    questions.append({
        "id": "scenario",
        "type": "scenario",
        "prompt": f"Based on this role: {job.description[:400]} — how would you approach a challenging problem in your first project?",
        "expected_concepts": (job.required_skills or [])[:4],
        "followup_prompt": "What would you measure to check whether your approach worked?",
        "followup_asked": False,
    })
    skill_names = {skill.strip().lower() for skill in (job.required_skills or [])}
    if skill_names.intersection(CODE_SKILLS):
        language = next(skill for skill in (job.required_skills or []) if skill.strip().lower() in CODE_SKILLS)
        questions.append({
            "id": "coding",
            "type": "coding",
            "skill": language,
            "prompt": "Write a function that returns a sorted list of the unique integers in its input. Explain the time and space complexity.",
            "expected_concepts": ["sort", "unique"],
            "test_cases": CODING_TEST_CASES,
            "followup_asked": False,
        })
    return questions


def _question_view(interview: models.AIInterview) -> dict | None:
    if interview.question_index >= len(interview.questions):
        return None
    question = interview.questions[interview.question_index]
    return {
        "id": question["id"],
        "type": question["type"],
        "skill": question.get("skill"),
        "prompt": question.get("followup_prompt") if interview.followup_pending else question["prompt"],
        "is_followup": interview.followup_pending,
        "test_cases": question.get("test_cases", []),
    }


def _build_report(interview: models.AIInterview) -> dict:
    transcript_by_question = {}
    for item in interview.transcript:
        transcript_by_question.setdefault(item["question_id"], []).append(item)

    evaluations = []
    for question in interview.questions:
        turns = transcript_by_question.get(question["id"], [])
        answer = " ".join(
            turn.get("answer", "") for turn in turns
        ).strip()
        code = next((turn.get("code") for turn in turns if turn.get("code")), "")
        if question["type"] == "coding":
            evaluations.append({
                "question": question["prompt"],
                "type": "coding",
                "skill": question.get("skill"),
                "score": None,
                "evidence": code[:5000] if code else "No code submission.",
                "feedback": "Code and sample tests are saved for recruiter review; code is not executed by this app.",
            })
            continue

        concepts = question.get("expected_concepts", [])
        normalized = answer.lower()
        covered = [
            concept for concept in concepts
            if concept and re.search(
                r"(?<!\w)" + re.escape(concept.lower()) + r"(?!\w)",
                normalized,
            )
        ]
        score = round(len(covered) / len(concepts) * 100) if concepts else None
        evidence = answer[:400] if answer else "No text answer was submitted."
        evaluations.append({
            "question": question["prompt"],
            "type": question["type"],
            "skill": question.get("skill"),
            "score": score,
            "covered_concepts": covered,
            "expected_concepts": concepts,
            "evidence": evidence,
            "feedback": (
                "Role-related concepts were present in the response."
                if covered else
                "Review this response against the role criteria; expected concepts were not detected by the local rubric."
            ),
        })

    scored = [item["score"] for item in evaluations if item["score"] is not None]
    return {
        "assessment": "Evidence summary for recruiter review; not a hiring recommendation.",
        "method": "Transparent local keyword-coverage rubric; not a validated AI model.",
        "coverage_score": round(sum(scored) / len(scored)) if scored else None,
        "strengths": [
            {"question": item["question"], "evidence": item["evidence"],
             "covered_concepts": item.get("covered_concepts", [])}
            for item in evaluations
            if item["score"] is not None and item.get("covered_concepts")
        ],
        "improvement_areas": [
            {"question": item["question"], "evidence": item["evidence"],
             "focus": [
                 concept for concept in item.get("expected_concepts", [])
                 if concept not in item.get("covered_concepts", [])
             ]}
            for item in evaluations
            if item["score"] is not None and item.get("score") < 100
        ],
        "evaluations": evaluations,
        "coding_review_required": any(q["type"] == "coding" for q in interview.questions),
    }


def _session_summary(interview: models.AIInterview, candidate: models.Candidate, job: models.Job) -> dict:
    return {
        "id": interview.id,
        "candidate_id": candidate.id,
        "candidate_name": candidate.full_name,
        "candidate_email": candidate.email,
        "job_id": job.id,
        "job_title": job.title,
        "status": interview.status,
        "progress": min(interview.question_index, len(interview.questions)),
        "question_count": len(interview.questions),
        "created_at": interview.created_at,
        "completed_at": interview.completed_at,
    }


@router.post("/ai-interviews")
def create_ai_interview(payload: CreateAIInterview, db: Session = Depends(get_db),
                        user: models.User = Depends(current_user)):
    candidate = db.query(models.Candidate).filter(
        models.Candidate.id == payload.candidate_id,
        models.Candidate.company_id == user.company_id,
    ).first()
    job = db.query(models.Job).filter(
        models.Job.id == payload.job_id,
        models.Job.company_id == user.company_id,
    ).first()
    if not candidate or not job:
        raise HTTPException(404, "Candidate or job not found in this workspace")
    token = secrets.token_urlsafe(32)
    interview = models.AIInterview(
        company_id=user.company_id,
        candidate_id=candidate.id,
        job_id=job.id,
        token_hash=_token_hash(token),
        questions=_generate_questions(job),
    )
    db.add(interview)
    db.flush()
    audit(db, user, "ai_interview.created", "ai_interview", interview.id,
          {"candidate_id": candidate.id, "job_id": job.id})
    db.commit()
    db.refresh(interview)
    return {**_session_summary(interview, candidate, job), "share_token": token}


@router.get("/ai-interviews")
def list_ai_interviews(db: Session = Depends(get_db), user: models.User = Depends(current_user)):
    rows = db.query(models.AIInterview).filter(
        models.AIInterview.company_id == user.company_id
    ).order_by(models.AIInterview.created_at.desc()).all()
    return [_session_summary(row, row.candidate, row.job) for row in rows]


@router.post("/ai-interviews/{interview_id}/invite")
def rotate_ai_interview_invite(interview_id: int, db: Session = Depends(get_db),
                               user: models.User = Depends(current_user)):
    interview = db.query(models.AIInterview).filter(
        models.AIInterview.id == interview_id,
        models.AIInterview.company_id == user.company_id,
    ).first()
    if not interview:
        raise HTTPException(404, "Interview not found")
    if interview.status != "Invited":
        raise HTTPException(409, "An interview link cannot be reissued after the candidate starts")
    token = secrets.token_urlsafe(32)
    interview.token_hash = _token_hash(token)
    interview.status = "Invited"
    interview.consented_at = None
    interview.modality = "text"
    interview.question_index = 0
    interview.followup_pending = False
    interview.transcript = []
    interview.report = None
    interview.started_at = None
    db.commit()
    return {"share_token": token}


@router.get("/ai-interviews/{interview_id}/report")
def get_ai_interview_report(interview_id: int, db: Session = Depends(get_db),
                            user: models.User = Depends(current_user)):
    interview = db.query(models.AIInterview).filter(
        models.AIInterview.id == interview_id,
        models.AIInterview.company_id == user.company_id,
    ).first()
    if not interview:
        raise HTTPException(404, "Interview not found")
    if interview.status != "Completed" or interview.report is None:
        raise HTTPException(409, "The interview report is available after the candidate completes the interview")
    candidate = db.query(models.Candidate).filter(
        models.Candidate.id == interview.candidate_id,
        models.Candidate.company_id == user.company_id,
    ).first()
    job = db.query(models.Job).filter(
        models.Job.id == interview.job_id,
        models.Job.company_id == user.company_id,
    ).first()
    return {
        **_session_summary(interview, candidate, job),
        "report": interview.report,
        "transcript": interview.transcript,
        "modality": interview.modality,
        "consented_at": interview.consented_at,
    }


@router.get("/public/ai-interviews/session")
def public_ai_interview_session(
    x_interview_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    interview = _load_public(db, _public_token(x_interview_token))
    candidate = db.query(models.Candidate).filter(
        models.Candidate.id == interview.candidate_id,
        models.Candidate.company_id == interview.company_id,
    ).first()
    job = db.query(models.Job).filter(
        models.Job.id == interview.job_id,
        models.Job.company_id == interview.company_id,
    ).first()
    return {
        "candidate_name": candidate.full_name,
        "company_name": db.query(models.Company).filter(
            models.Company.id == interview.company_id
        ).first().name,
        "job_title": job.title,
        "status": interview.status,
        "consented": interview.consented_at is not None,
        "disclosure": DISCLOSURE,
        "progress": min(interview.question_index, len(interview.questions)),
        "question_count": len(interview.questions),
        "question": _question_view(interview) if interview.consented_at else None,
    }


@router.post("/public/ai-interviews/consent")
def consent_ai_interview(payload: ConsentInput,
                         x_interview_token: str | None = Header(default=None),
                         db: Session = Depends(get_db)):
    interview = _load_public(db, _public_token(x_interview_token))
    if not payload.consent:
        raise HTTPException(400, "Consent is required to begin the interview")
    if interview.status == "Completed":
        raise HTTPException(409, "This interview has already been completed")
    if interview.consented_at is None:
        interview.consented_at = datetime.now(timezone.utc)
        interview.started_at = interview.consented_at
    interview.modality = payload.modality
    interview.status = "In Progress"
    db.commit()
    return {
        "question": _question_view(interview),
        "progress": interview.question_index,
        "question_count": len(interview.questions),
    }


@router.post("/public/ai-interviews/answer")
def answer_ai_interview(payload: AnswerInput,
                        x_interview_token: str | None = Header(default=None),
                        db: Session = Depends(get_db)):
    interview = _load_public(db, _public_token(x_interview_token))
    if interview.consented_at is None or interview.status != "In Progress":
        raise HTTPException(409, "Consent is required before submitting an answer")
    if interview.question_index >= len(interview.questions):
        raise HTTPException(409, "This interview has already been completed")
    question = interview.questions[interview.question_index]
    answer = payload.answer.strip()
    code = payload.code.strip()
    if question["type"] == "coding" and not code:
        raise HTTPException(400, "Add your code submission before continuing")
    if question["type"] != "coding" and not answer:
        raise HTTPException(400, "Enter an answer before continuing")
    if question["type"] == "coding":
        answer = answer or "Candidate submitted a code response."
    interview.transcript = [*interview.transcript, {
        "question_id": question["id"],
        "question": _question_view(interview)["prompt"],
        "answer": answer,
        "code": code,
        "language": payload.language if code else None,
        "answered_at": datetime.now(timezone.utc).isoformat(),
        "is_followup": interview.followup_pending,
    }]
    if interview.followup_pending:
        interview.followup_pending = False
        interview.question_index += 1
    elif (
        question["type"] in {"technical", "scenario"}
        and len(answer.split()) < 30
        and not question.get("followup_asked")
    ):
        question["followup_asked"] = True
        interview.questions = list(interview.questions)
        interview.questions[interview.question_index] = question
        interview.followup_pending = True
    else:
        interview.question_index += 1
    completed = interview.question_index >= len(interview.questions)
    if completed:
        interview.status = "Completed"
        interview.completed_at = datetime.now(timezone.utc)
        interview.report = _build_report(interview)
    db.commit()
    return {
        "status": interview.status,
        "progress": min(interview.question_index, len(interview.questions)),
        "question_count": len(interview.questions),
        "question": _question_view(interview),
        "report_ready": completed,
    }
