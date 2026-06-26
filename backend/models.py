import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.sqlite import DATETIME as SQLiteDateTime

from database import Base


DB_DATETIME = DateTime().with_variant(
    SQLiteDateTime(storage_format="%(year)04d-%(month)02d-%(day)02d %(hour)02d:%(minute)02d:%(second)02d"),
    "sqlite",
)


def _uuid() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


EMPLOYEE_STATUSES = ("active", "disabled")
APP_STATUSES = ("creating", "editing", "active", "failed", "edit_failed")
APP_PROJECT_TYPES = ("html", "project")
APP_VISIBILITIES = ("private", "public", "token")
CONVERSATION_ROLES = ("user", "assistant")
USAGE_ACTIONS = ("name", "generate", "edit")
USAGE_STATUSES = ("success", "failed")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, digest = password_hash.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
    return secrets.compare_digest(candidate, digest)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("status in ('active', 'disabled')", name="ck_employees_status"),
    )

    employee_no = Column(String(32), primary_key=True)
    name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_employee_no", "employee_no"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    employee_no = Column(String(32), ForeignKey("employees.employee_no", ondelete="RESTRICT"), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class SessionToken(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)
    expires_at = Column(DB_DATETIME, nullable=False)


class Style(Base):
    __tablename__ = "styles"
    __table_args__ = (
        Index("ix_styles_active_sort", "is_active", "sort_order"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class App(Base):
    __tablename__ = "apps"
    __table_args__ = (
        CheckConstraint("status in ('creating', 'editing', 'active', 'failed', 'edit_failed')", name="ck_apps_status"),
        CheckConstraint("project_type in ('html', 'project')", name="ck_apps_project_type"),
        CheckConstraint("visibility in ('private', 'public', 'token')", name="ck_apps_visibility"),
        Index("ix_apps_user_updated", "user_id", "updated_at"),
        Index("ix_apps_style_id", "style_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    style_id = Column(String(36), ForeignKey("styles.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False, default="新应用")
    description = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="creating")
    progress = Column(String(100), nullable=True)
    entry_path = Column(String(255), nullable=False, default="index.html")
    project_type = Column(String(20), nullable=False, default="project")
    visibility = Column(String(20), nullable=False, default="private")
    preview_token = Column(String(64), nullable=True, unique=True)
    opencode_session_id = Column(String(100), nullable=True)
    opencode_workspace = Column(String(500), nullable=True)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)
    version = Column(Integer, nullable=False, default=0)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="ck_conversations_role"),
        Index("ix_conversations_app_created", "app_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    app_id = Column(String(36), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class OpenCodeEvent(Base):
    __tablename__ = "opencode_events"
    __table_args__ = (
        Index("ix_opencode_events_app_sequence", "app_id", "sequence"),
        Index("ix_opencode_events_app_created", "app_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    app_id = Column(String(36), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)


class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        CheckConstraint("action in ('name', 'generate', 'edit')", name="ck_usage_records_action"),
        CheckConstraint("status in ('success', 'failed')", name="ck_usage_records_status"),
        CheckConstraint("prompt_tokens >= 0", name="ck_usage_records_prompt_tokens"),
        CheckConstraint("completion_tokens >= 0", name="ck_usage_records_completion_tokens"),
        CheckConstraint("total_tokens >= 0", name="ck_usage_records_total_tokens"),
        CheckConstraint("cost >= 0", name="ck_usage_records_cost"),
        Index("ix_usage_records_user_created", "user_id", "created_at"),
        Index("ix_usage_records_app_id", "app_id"),
        Index("ix_usage_records_model", "model"),
        Index("ix_usage_records_provider", "provider"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    app_id = Column(String(36), ForeignKey("apps.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(20), nullable=False)
    provider = Column(String(50), nullable=False, default="unknown")
    model = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost = Column(Numeric(12, 6), nullable=False, default=0)
    is_estimated = Column(Boolean, nullable=False, default=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class AppDataRecord(Base):
    __tablename__ = "app_data_records"
    __table_args__ = (
        Index("ix_app_data_records_app_collection_created", "app_id", "collection", "created_at"),
        Index("ix_app_data_records_app_collection", "app_id", "collection"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    app_id = Column(String(36), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    collection = Column(String(64), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class LLMSetting(Base):
    __tablename__ = "llm_settings"

    id = Column(String(36), primary_key=True, default=_uuid)
    base_url = Column(String(500), nullable=False)
    model = Column(String(100), nullable=False)
    api_key = Column(Text, nullable=True)
    created_at = Column(DB_DATETIME, nullable=False, default=now_utc)
    updated_at = Column(DB_DATETIME, nullable=False, default=now_utc, onupdate=now_utc)


class UserResponse(BaseModel):
    employee_no: str
    is_admin: bool


class EmployeeResponse(BaseModel):
    employee_no: str
    name: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AppResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    progress: Optional[str]
    style_id: Optional[str]
    entry_path: str
    project_type: str
    visibility: str
    preview_token: Optional[str]
    opencode_session_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


class StyleResponse(BaseModel):
    id: str
    name: str
    prompt: str
    sort_order: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    id: str
    app_id: str
    role: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AppDataCreateRequest(BaseModel):
    data: dict


class AppDataUpdateRequest(BaseModel):
    data: dict


class AppDataRecordResponse(BaseModel):
    id: str
    app_id: str
    collection: str
    data: dict
    created_at: datetime
    updated_at: datetime


class UsageSummaryResponse(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    record_count: int
    estimated_record_count: int
    successful_record_count: int
    failed_record_count: int
    first_record_at: Optional[datetime]
    last_record_at: Optional[datetime]


class UsageRecordResponse(BaseModel):
    id: str
    app_id: Optional[str]
    app_name: Optional[str]
    action: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    is_estimated: bool
    status: str
    created_at: datetime
    updated_at: datetime
