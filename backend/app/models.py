from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON, UniqueConstraint, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    full_name = Column(String(160), nullable=False)
    email = Column(String(254), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="recruiter", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    company = relationship("Company", back_populates="users")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    department = Column(String(120), default="")
    description = Column(Text, nullable=False)
    required_skills = Column(JSON, default=list)
    min_experience = Column(Float, default=0)
    min_10th = Column(Float, nullable=True)
    min_12th = Column(Float, nullable=True)
    min_cgpa = Column(Float, nullable=True)
    location = Column(String(160), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    full_name = Column(String(180), default="Unknown candidate")
    email = Column(String(254), default="")
    phone = Column(String(40), default="")
    location = Column(String(160), default="")
    education = Column(Text, default="")
    graduation_year = Column(Integer, nullable=True)
    tenth_percentage = Column(Float, nullable=True)
    twelfth_percentage = Column(Float, nullable=True)
    cgpa = Column(Float, nullable=True)
    experience_years = Column(Float, default=0)
    skills = Column(JSON, default=list)
    skill_evidence = Column(JSON, default=dict)
    sections = Column(JSON, default=dict)
    resume_filename = Column(String(255), default="")
    resume_text = Column(Text, default="")
    status = Column(String(40), default="Applied", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    matches = relationship("CandidateMatch", back_populates="candidate", cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="candidate", cascade="all, delete-orphan")

class CandidateMatch(Base):
    __tablename__ = "candidate_matches"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),)
    id = Column(Integer, primary_key=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    breakdown = Column(JSON, default=dict)
    matched_skills = Column(JSON, default=list)
    missing_skills = Column(JSON, default=list)
    candidate = relationship("Candidate", back_populates="matches")

class Interview(Base):
    __tablename__ = "interviews"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True, index=True)
    interviewer = Column(String(160), default="")
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=45)
    meeting_url = Column(String(500), default="")
    notes = Column(Text, default="")
    status = Column(String(30), default="Scheduled")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    candidate = relationship("Candidate", back_populates="interviews")

class AIInterview(Base):
    __tablename__ = "ai_interviews"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(30), default="Invited", nullable=False, index=True)
    consented_at = Column(DateTime(timezone=True), nullable=True)
    modality = Column(String(20), default="text", nullable=False)
    questions = Column(JSON, default=list, nullable=False)
    question_index = Column(Integer, default=0, nullable=False)
    followup_pending = Column(Boolean, default=False, nullable=False)
    transcript = Column(JSON, default=list, nullable=False)
    report = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    candidate = relationship("Candidate")
    job = relationship("Job")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(80), nullable=False)
    entity_id = Column(String(80), default="")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

Index("ix_candidates_company_email", Candidate.company_id, Candidate.email)
