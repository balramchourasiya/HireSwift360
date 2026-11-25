# HireSwift 360

HireSwift 360 is a recruiter-facing talent intelligence platform. This iteration upgrades the original MVP with workspace authentication, company-scoped access, evidence-aware resume extraction, semantic relevance scoring, candidate comparison, interview scheduling, email invitations, analytics and audit events.

> **Important:** This is a development foundation, not a production-certified HR system. Validate your legal basis/consent, retention and deletion workflows, security controls, model quality and accessibility before processing real candidate data. Scores are decision-support only; never automatically reject candidates.

## What's implemented

1. **Login and company isolation** — workspace registration, login, Argon2 password hashes, signed expiring JWTs, role checks and company scoping on all recruiter data endpoints. Cross-workspace object access returns 404. The first registrant for a workspace is its admin.
2. **Richer resume parsing** — PDF and DOCX extraction (including DOCX tables), contact/education/experience heuristics, skill taxonomy, section extraction and text snippets showing where skills were found. Scanned PDFs need OCR and currently return a reviewable error.
3. **Explainable matching** — explicit skill/experience/education criteria plus text relevance. Default local relevance uses a standard-library TF-IDF implementation; optional sentence-transformer embeddings can be enabled. If embeddings cannot load, matching logs the failure and reports its local TF-IDF fallback in the result. Match results show matched/missing skills, evidence snippets, weights and the scoring method. This is not a probability of success.
4. **Candidate comparison** — compare 2–5 profiles side by side, with tenant-scoped API and recruiter UI.
5. **Interview workflow** — schedule interviews, link candidates/jobs, record status/notes and send an invitation using configured SMTP.
6. **Analytics and audit trail** — pipeline counts, basic conversion indicators and admin-only event history for key changes.
7. **AI-assisted interviews** — private candidate links, required transcript consent, browser speech input/output, role-based questions and follow-ups, saved coding submissions, and company-scoped recruiter reports.

## Requirements

- Python 3.11 or 3.12
- Node.js 20+
- SQLite for local development; PostgreSQL recommended for shared environments

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows; edit JWT_SECRET_KEY and DATABASE_URL
# macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload
```

The backend automatically loads `backend/.env`. For a quick local SQLite run, `DATABASE_URL` may be omitted. The database file is `backend/hireswift.db`. Existing v0.1 databases receive a small automatic column migration for the new candidate evidence fields. Back up your database before upgrading; use a formal Alembic migration workflow before production.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Create your company workspace on the registration screen. API documentation is at http://localhost:8000/docs. The health endpoint is available at `/health` and `/api/health`.

### PostgreSQL

Set `DATABASE_URL` to a SQLAlchemy URL, for example:

```text
postgresql+psycopg://hireswift:your-password@localhost:5432/hireswift
```

Install the included `psycopg[binary]` driver (already in requirements).

## Optional transformer embeddings

Default relevance scoring is local TF-IDF similarity and does not require NumPy or scikit-learn. For transformer-based sentence embeddings:

```bash
pip install -r requirements-ai.txt
```

Set `USE_SENTENCE_TRANSFORMERS=true` and optionally `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` in the backend environment. The first run downloads the model; review the model licence, hosting and data-processing implications before using it with candidate information. If the package/model cannot load, matching logs the error and falls back to local TF-IDF; the result's scoring method identifies the fallback.

## SMTP interview invitations

Copy `backend/.env.example` to `backend/.env` and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM`. The API sends a plain-text invitation to the candidate's parsed email address. Port 587 uses STARTTLS by default; set `SMTP_USE_SSL=true` for implicit TLS on port 465.

For Gmail, enable 2-Step Verification and create an App Password in your Google Account. Use `smtp.gmail.com`, port `587`, your Gmail address for `SMTP_USER` and `MAIL_FROM`, and the App Password for `SMTP_PASSWORD` (not your regular account password). Restart the backend after editing `.env`. Never commit `.env` or share the app password. The authenticated `GET /api/email/status` endpoint and Settings page show whether SMTP is configured and which required settings are missing. Test with a controlled mailbox before enabling this in a live workspace.

## AI-assisted interviews

Recruiters can create an interview from the **AI Interviewer** workspace page and share the generated private link with the selected candidate. The candidate must consent before the session starts and can choose text or browser voice transcription. The browser's speech recognition may process audio under the browser provider's policies; this application does not record or store audio. Only submitted text answers and coding source are retained.

Sessions and reports are scoped to the recruiter’s company. The share token is stored as a hash, delivered once, and placed in the URL fragment so it is not sent in normal HTTP requests or referrer headers. An unstarted invitation can be reissued, which revokes the previous link.

Question generation and evaluation currently use a deterministic local role/skill rubric, not an external language model. Short technical answers can receive one clarification follow-up. Report scores indicate keyword coverage only; they do not measure candidate quality, communication ability, or hiring suitability. Coding sample cases are shown beside the in-browser editor, but submitted code is not executed; recruiters review it manually. Reports and transcripts are available only to authenticated users in the owning workspace. Recruiters must review all evidence and make hiring decisions.

## Main API routes

| Capability | Route |
|---|---|
| Register / login / current user | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Jobs | `GET /api/jobs`, `POST /api/jobs` |
| Resume intake / candidates | `POST /api/candidates/upload`, `GET /api/candidates`, `GET /api/candidates/{id}` |
| Matching | `POST /api/jobs/{id}/match`, `GET /api/jobs/{id}/matches` |
| AI interviews | `POST /api/ai-interviews`, `GET /api/ai-interviews`, `GET /api/ai-interviews/{id}/report` |
| Comparison | `GET /api/candidates/compare?ids=1,2` |
| Interviews | `POST /api/interviews`, `GET /api/interviews`, `PATCH /api/interviews/{id}`, `POST /api/interviews/{id}/email` |
| Analytics / audit | `GET /api/analytics`, `GET /api/audit-logs` (admin only) |

Every route that returns or changes workspace data requires `Authorization: Bearer <token>`. Company IDs are never accepted from the browser as an authorization boundary; they are derived from the signed-in user.

## Security and responsible-use checklist before production

- Set a unique high-entropy `JWT_SECRET_KEY` (at least 32 characters) and never use the development fallback.
- Serve only over HTTPS; restrict `CORS_ORIGINS` to the actual frontend origin.
- Disable open public registration or add verified invitations/domain controls before onboarding multiple customers.
- Add rate limiting, login lockout, MFA/SSO, password reset and user invitation/role administration.
- Use managed PostgreSQL, encrypted backups, secret management, monitoring and a tested restore plan.
- Add formal schema migrations, retention/deletion/export workflows, candidate consent tracking and access/deletion request handling.
- Add malware scanning, OCR for scanned resumes, encrypted object storage and asynchronous upload processing for large-scale intake.
- Review model bias and job-related validity with representative data; keep protected characteristics out of scoring; show evidence and allow human review.
- Do not treat missing resume data as proof that a candidate lacks a qualification. The parser is heuristic and needs recruiter verification.

## Verification performed for this upgrade

Backend smoke/integration checks passed for registration, authenticated profile, job creation, cross-company isolation (including cross-tenant 404), PDF/DOCX parsing, candidate comparison, matching, interview scheduling, analytics and admin audit-log access. Frontend production build was not verified in this environment because npm dependency installation did not complete; run `npm install && npm run build` locally before demo/deployment.
