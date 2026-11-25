"""Run a local API integration smoke test: python smoke_test.py (from backend/)."""
import os, tempfile
from pathlib import Path
from fastapi.testclient import TestClient

fd, db_path = tempfile.mkstemp(suffix=".db"); os.close(fd)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["JWT_SECRET_KEY"] = "smoke-test-only-secret-key-0123456789-abcdef"
from app.database import normalize_database_url
assert normalize_database_url("postgres://user:pass@db.example.test/app") == "postgresql+psycopg://user:pass@db.example.test/app"
assert normalize_database_url("postgresql://user:pass@db.example.test/app") == "postgresql+psycopg://user:pass@db.example.test/app"
for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"]:
    os.environ.pop(key, None)
from app.main import app  # noqa: E402

client = TestClient(app)
try:
    reg = client.post("/api/auth/register", json={"company_name":"Smoke Workspace","full_name":"Test Admin","email":"admin@smoke.example.com","password":"SmokeTestPass!123"})
    assert reg.status_code == 200, reg.text
    auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    job = client.post("/api/jobs", headers=auth, json={"title":"Embedded Engineer","description":"Embedded C, RTOS, firmware, Python and microcontrollers","required_skills":["C","Embedded C","RTOS","Python"]})
    assert job.status_code == 200, job.text
    b = client.post("/api/auth/register", json={"company_name":"Other Workspace","full_name":"Other Admin","email":"other@smoke.example.com","password":"SmokeTestPass!123"})
    other_auth = {"Authorization": f"Bearer {b.json()['access_token']}"}
    assert client.get("/api/jobs", headers=other_auth).json() == []
    assert client.post(f"/api/jobs/{job.json()['id']}/match", headers=other_auth).status_code == 404
    sample_dir = Path(__file__).resolve().parents[1] / "sample_data" / "resumes"
    uploads = []
    for filename in ["sample_candidate_1.pdf", "sample_candidate_2.docx"]:
        mime = "application/pdf" if filename.endswith(".pdf") else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        uploads.append(("files", (filename, (sample_dir / filename).read_bytes(), mime)))
    uploaded = client.post("/api/candidates/upload", headers=auth, files=uploads)
    assert uploaded.status_code == 200 and uploaded.json()["uploaded"] == 2, uploaded.text
    ids = [x["id"] for x in uploaded.json()["candidates"]]
    assert client.get("/api/candidates/compare", headers=auth, params={"ids": ",".join(map(str, ids))}).status_code == 200
    assert client.post(f"/api/jobs/{job.json()['id']}/match", headers=auth).status_code == 200
    interview = client.post("/api/interviews", headers=auth, json={"candidate_id":ids[0],"job_id":job.json()["id"],"scheduled_at":"2026-12-01T10:00:00+05:30"})
    assert interview.status_code == 200, interview.text
    email_status = client.get("/api/email/status", headers=auth)
    assert email_status.status_code == 200 and not email_status.json()["configured"], email_status.text
    email = client.post(f"/api/interviews/{interview.json()['id']}/email", headers=auth)
    assert email.status_code == 503 and "backend/.env" in email.json()["detail"], email.text
    ai_session = client.post("/api/ai-interviews", headers=auth, json={"candidate_id":ids[0],"job_id":job.json()["id"]})
    assert ai_session.status_code == 200 and ai_session.json()["share_token"], ai_session.text
    public_headers = {"X-Interview-Token": ai_session.json()["share_token"]}
    assert client.get("/api/ai-interviews", headers=other_auth).json() == []
    assert client.get(f"/api/ai-interviews/{ai_session.json()['id']}/report", headers=auth).status_code == 409
    public_session = client.get("/api/public/ai-interviews/session", headers=public_headers)
    assert public_session.status_code == 200 and public_session.json()["question"] is None
    assert client.post("/api/public/ai-interviews/consent", headers=public_headers, json={"consent":False,"modality":"voice"}).status_code == 400
    started = client.post("/api/public/ai-interviews/consent", headers=public_headers, json={"consent":True,"modality":"text"})
    assert started.status_code == 200 and started.json()["question"], started.text
    assert client.post("/api/public/ai-interviews/answer", headers=public_headers, json={}).status_code == 400
    saw_followup = saw_coding = False
    for _ in range(12):
        state = client.get("/api/public/ai-interviews/session", headers=public_headers).json()
        question = state["question"]
        if question["type"] == "coding":
            saw_coding = True
            answer_payload = {"code":"function uniqueSorted(values) { return [...new Set(values)].sort((a, b) => a - b); }","language":"javascript"}
        else:
            if question["is_followup"]:
                saw_followup = True
            skill = question.get("skill") or "Embedded Engineer Python RTOS"
            answer_text = "Brief answer."
            if question["is_followup"]:
                answer_text = ("I worked with " + skill + " on a production project, where I designed and delivered the implementation. " * 4)
            elif question["type"] not in {"technical"}:
                answer_text = ("I worked with " + skill + " on a production project, where I designed and delivered the implementation. " * 4)
            answer_payload = {"answer":answer_text}
        next_question = client.post("/api/public/ai-interviews/answer", headers=public_headers, json=answer_payload)
        assert next_question.status_code == 200, next_question.text
        if next_question.json()["status"] == "Completed":
            break
    assert next_question.json()["status"] == "Completed" and saw_followup and saw_coding, next_question.text
    report_response = client.get(f"/api/ai-interviews/{ai_session.json()['id']}/report", headers=auth)
    assert report_response.status_code == 200 and report_response.json()["report"]["coding_review_required"], report_response.text
    assert "strengths" in report_response.json()["report"] and "improvement_areas" in report_response.json()["report"]
    assert any(turn.get("code") for turn in report_response.json()["transcript"]), "Coding answer was not saved"
    assert client.get(f"/api/ai-interviews/{ai_session.json()['id']}/report", headers=other_auth).status_code == 404
    pending = client.post("/api/ai-interviews", headers=auth, json={"candidate_id":ids[1],"job_id":job.json()["id"]}).json()
    refreshed = client.post(f"/api/ai-interviews/{pending['id']}/invite", headers=auth)
    assert refreshed.status_code == 200, refreshed.text
    assert client.get("/api/public/ai-interviews/session", headers={"X-Interview-Token":pending["share_token"]}).status_code == 404
    assert client.get("/api/analytics", headers=auth).status_code == 200
    assert client.get("/api/audit-logs", headers=auth).status_code == 200
    print("PASS: auth, tenant isolation, resume parsing, matching, AI interview consent/follow-up/coding/transcript/report, SMTP readiness, interviews, analytics and audit logs")
finally:
    client.close()
    try: os.remove(db_path)
    except OSError: pass
