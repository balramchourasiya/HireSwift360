import os, jwt
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from . import models

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if len(SECRET_KEY) < 32:
    # Development-only fallback. Production must provide a random secret via environment.
    SECRET_KEY = "DEV-ONLY-change-this-secret-before-deployment-2026-hs360"
ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "8"))
hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return hasher.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try: return hasher.verify(hashed, password)
    except VerifyMismatchError: return False

def create_token(user: models.User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "company_id": user.company_id, "role": user.role,
                       "iat": now, "exp": now + timedelta(hours=TOKEN_HOURS)}, SECRET_KEY, algorithm=ALGORITHM)

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials: raise HTTPException(401, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(models.User).filter(models.User.id == int(payload["sub"]), models.User.is_active.is_(True)).first()
    except Exception:
        user = None
    if not user: raise HTTPException(401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    return user

def require_admin(user: models.User = Depends(current_user)):
    if user.role != "admin": raise HTTPException(403, "Workspace admin permission required")
    return user

def audit(db: Session, user: models.User, action: str, entity_type: str, entity_id="", details=None):
    db.add(models.AuditLog(company_id=user.company_id, user_id=user.id, action=action,
                           entity_type=entity_type, entity_id=str(entity_id), details=details or {}))
