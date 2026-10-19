"""
Pydantic V2 schemas for BD Legal Guide AI:
Authentication, Users, Moderators, Audit Logs, Lawyers & Law Firms.
"""

from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=6)
    role: str = "user"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None


class ModeratorCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=6)
    scopes: List[str] = Field(default_factory=list)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    status: str
    scopes: Optional[List[str]] = None

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: Optional[str] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: str

    @field_validator("id", "actor_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


# --- Module 4: Lawyer & Law Firm Schemas ---

class LawyerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    district: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    verification_status: str
    bar_council_id: Optional[str] = None
    verification_paid: Optional[bool] = False

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""


class LawyerUpdate(BaseModel):
    name: Optional[str] = None
    district: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    verification_status: Optional[str] = None


class FirmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: str

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""


class FirmUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
