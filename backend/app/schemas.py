from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class RegisterInput(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class JobCreate(BaseModel):
    title: str
    department: str = ""
    description: str
    required_skills: List[str] = Field(default_factory=list)
    min_experience: float = 0
    min_10th: Optional[float] = None
    min_12th: Optional[float] = None
    min_cgpa: Optional[float] = None
    location: str = ""

class StatusUpdate(BaseModel):
    status: str

class InterviewCreate(BaseModel):
    candidate_id: int
    job_id: Optional[int] = None
    interviewer: str = ""
    scheduled_at: datetime
    duration_minutes: int = Field(default=45, ge=15, le=240)
    meeting_url: str = ""
    notes: str = ""

class InterviewUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
