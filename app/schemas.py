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


# --- Module 6: Chat & LLM Config Schemas ---

class ChatMessageCreate(BaseModel):
    session_id: Optional[str] = None
    content: Optional[str] = None
    message: Optional[str] = None
    mode: Optional[str] = "standard"

    @model_validator(mode="after")
    def populate_content(self):
        if not self.content and self.message:
            self.content = self.message
        if not self.content:
            raise ValueError("Message content is required")
        return self


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str
    disclaimer: str
    session_id: Optional[str] = None
    id: Optional[str] = None
    content: Optional[str] = None
    response: Optional[str] = None
    message: Optional[str] = None

    @model_validator(mode="after")
    def populate_aliases(self):
        if not self.content:
            self.content = self.reply
        if not self.response:
            self.response = self.reply
        if not self.message:
            self.message = self.reply
        return self


class LlmConfigUpdate(BaseModel):
    provider: str = "gemini"
    model_name: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: Optional[str] = ""
    disclaimer: Optional[str] = ""
    is_active: bool = True

    @model_validator(mode="after")
    def populate_model_name(self):
        if not self.model_name and self.model:
            self.model_name = self.model
        if not self.model_name:
            self.model_name = "gemini-1.5-flash"
        return self


class LlmConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    model_name: str
    model: Optional[str] = None
    temperature: float
    max_tokens: int
    system_prompt: Optional[str] = None
    disclaimer: Optional[str] = None
    is_active: bool
    created_at: str

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""

    @model_validator(mode="after")
    def set_model_alias(self):
        if not self.model:
            self.model = self.model_name
        return self


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: Optional[str] = "Legal Consultation"
    created_at: str

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: str
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    created_at: str

    @field_validator("id", "session_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


# --- Module 7: Payments & Subscriptions Schemas ---

class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    price_monthly: float
    features: List[str]
    price: Optional[Any] = None

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @model_validator(mode="after")
    def populate_price(self):
        if self.price is None:
            self.price = self.price_monthly
        return self


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    plan_code: str
    status: str
    started_at: str
    expires_at: Optional[str] = None

    @field_validator("id", "user_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("started_at", "expires_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else None

    @model_validator(mode="before")
    @classmethod
    def extract_plan_code(cls, data: Any):
        if isinstance(data, dict):
            return data
        plan_code = getattr(data, "plan_code", None)
        if not plan_code and hasattr(data, "plan") and data.plan:
            plan_code = getattr(data.plan, "code", None)
        started_at = getattr(data, "started_at", None)
        expires_at = getattr(data, "expires_at", None)
        return {
            "id": str(getattr(data, "id", "")),
            "user_id": str(getattr(data, "user_id", "")),
            "plan_code": plan_code or "",
            "status": getattr(data, "status", "pending"),
            "started_at": started_at.isoformat() if hasattr(started_at, "isoformat") else str(started_at or ""),
            "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else (str(expires_at) if expires_at else None),
        }


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    amount: float
    provider: str
    status: str
    created_at: str
    user_email: Optional[str] = None
    client_name: Optional[str] = None
    user_name: Optional[str] = None
    transaction_id: Optional[str] = None
    method: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""

    @model_validator(mode="after")
    def populate_aliases(self):
        if not self.transaction_id:
            self.transaction_id = self.id
        if not self.method:
            self.method = self.provider
        return self


class CheckoutRequest(BaseModel):
    plan_code: str
    provider: Optional[str] = None


class CheckoutResponse(BaseModel):
    checkout_url: str
    status: str
    subscription_id: Optional[str] = None
    payment_id: Optional[str] = None



