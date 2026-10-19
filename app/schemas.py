"""
Pydantic V2 schemas for BD Legal Guide AI:
Authentication, Users, Moderators, Audit Logs, Lawyers & Law Firms.
"""

from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


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


# --- Module 5: Schedules & Bookings Schemas ---

class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lawyer_id: str
    date: str
    start_time: str
    end_time: str
    is_booked: bool

    @field_validator("id", "lawyer_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)


class ScheduleCreate(BaseModel):
    date: str
    start_time: str
    end_time: str


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    lawyer_id: str
    schedule_id: str
    status: str
    created_at: str
    lawyer_name: Optional[str] = None
    user_name: Optional[str] = None
    meet_link: Optional[str] = None
    scheduled_time: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    @field_validator("id", "user_id", "lawyer_id", "schedule_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""

    @model_validator(mode="before")
    @classmethod
    def extract_relations(cls, data: Any):
        if isinstance(data, dict):
            return data

        lawyer_name = None
        user_name = None
        date_val = getattr(data, "date", None)
        start_time_val = getattr(data, "start_time", None)
        end_time_val = getattr(data, "end_time", None)

        if hasattr(data, "lawyer") and data.lawyer:
            lawyer_name = getattr(data.lawyer, "name", None)
        if hasattr(data, "user") and data.user:
            user_name = getattr(data.user, "full_name", None)
        if hasattr(data, "schedule") and data.schedule:
            date_val = getattr(data.schedule, "date", None)
            start_time_val = getattr(data.schedule, "start_time", None)
            end_time_val = getattr(data.schedule, "end_time", None)

        created_at_val = getattr(data, "created_at", "")
        if hasattr(created_at_val, "isoformat"):
            created_at_val = created_at_val.isoformat()
        else:
            created_at_val = str(created_at_val) if created_at_val is not None else ""

        scheduled_time = (
            f"{date_val} {start_time_val}".strip()
            if (date_val or start_time_val)
            else None
        )

        return {
            "id": str(getattr(data, "id", "")),
            "user_id": str(getattr(data, "user_id", "")),
            "lawyer_id": str(getattr(data, "lawyer_id", "")),
            "schedule_id": str(getattr(data, "schedule_id", "")),
            "status": str(getattr(data, "status", "pending")),
            "created_at": created_at_val,
            "lawyer_name": lawyer_name or getattr(data, "lawyer_name", None),
            "user_name": user_name or getattr(data, "user_name", None),
            "meet_link": getattr(data, "meet_link", None),
            "scheduled_time": scheduled_time,
            "date": date_val,
            "start_time": start_time_val,
            "end_time": end_time_val,
        }


class BookingCreate(BaseModel):
    schedule_id: str


class BookingUpdate(BaseModel):
    status: str
    meet_link: Optional[str] = None

