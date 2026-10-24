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
    plan: Optional[str] = "user_free"
    is_pro: Optional[bool] = False

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    """Combined auth response for login/register — includes JWT and user profile."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


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

class LawyerListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    district: Optional[str] = None
    specialization: Optional[str] = None
    verification_status: str
    bar_council_id: Optional[str] = None
    verification_paid: Optional[bool] = False
    avatar_asset_id: Optional[str] = None
    next_available: Optional[Dict[str, Any]] = None
    hourly_rate: Optional[int] = 2000
    years_exp: Optional[int] = 8
    languages: Optional[str] = "Bangla, English"

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("avatar_asset_id", mode="before")
    @classmethod
    def serialize_avatar_asset_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else None


class LawyerResponse(LawyerListResponse):
    phone: Optional[str] = None


class LawyerUpdate(BaseModel):
    name: Optional[str] = None
    district: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    verification_status: Optional[str] = None
    hourly_rate: Optional[int] = None
    years_exp: Optional[int] = None
    languages: Optional[str] = None


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

    @field_validator("date", mode="before")
    @classmethod
    def serialize_date(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


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
    schedule_date: Optional[str] = None
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
            s_date = data.get("schedule_date") or data.get("date")
            if hasattr(s_date, "isoformat"):
                s_date = s_date.isoformat()
            elif s_date is not None:
                s_date = str(s_date)
            data["schedule_date"] = s_date
            data["date"] = s_date
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
            raw_sched_date = getattr(data.schedule, "date", None)
            if hasattr(raw_sched_date, "isoformat"):
                date_val = raw_sched_date.isoformat()
            else:
                date_val = str(raw_sched_date) if raw_sched_date is not None else None
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
            "schedule_date": date_val,
            "date": date_val,
            "start_time": start_time_val,
            "end_time": end_time_val,
        }


class BookingCreate(BaseModel):
    schedule_id: Optional[str] = None
    lawyer_id: Optional[str] = None
    slot: Optional[Any] = None
    case_brief: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None

    @model_validator(mode="after")
    def validate_reference(self):
        if not self.schedule_id and not self.lawyer_id:
            raise ValueError("Either schedule_id or lawyer_id must be provided to create a booking.")
        return self


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
    confidence: Optional[int] = None
    confidence_reason: Optional[str] = None
    context_window: Optional[int] = None

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
    confidence_score: Optional[int] = None
    confidence_reason: Optional[str] = None
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
    duration_days: Optional[int] = None
    price: Optional[Any] = None
    target_role: Optional[str] = "user"
    description: Optional[str] = None
    popular: Optional[bool] = False

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @model_validator(mode="after")
    def populate_fields(self):
        if self.price is None:
            self.price = self.price_monthly
        if not self.target_role:
            if "lawyer" in self.code.lower():
                self.target_role = "lawyer"
            else:
                self.target_role = "user"
        if not self.description:
            if self.code == "user_free":
                self.description = "Essential legal AI guidance and lawyer search for everyday citizens."
            elif self.code in ["user_pro", "user_pro_monthly"]:
                self.description = "Deep legal intelligence with BD Penal Code citations & document review."
            elif self.code == "user_pro_6m":
                self.description = "Pro features with 6-month continuous access and savings."
            elif self.code == "user_pro_1y":
                self.description = "Full Pro access for 1 year with maximum savings."
            elif self.code == "lawyer_basic":
                self.description = "Standard listing in the Bangladesh lawyer directory & consultation requests."
            elif self.code == "lawyer_verified":
                self.description = "Verified Bar Council badge, priority placement & video meeting suite."
        if not self.popular:
            if self.code in ["user_pro", "user_pro_monthly", "lawyer_verified"]:
                self.popular = True
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


# --- Direct Messaging Schemas ---

class DirectMessageCreate(BaseModel):
    content: str = Field(..., min_length=1)


class DirectMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender_user_id: str
    lawyer_profile_id: str
    recipient_user_id: Optional[str] = None
    content: str
    is_read: bool = False
    created_at: str
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None

    @field_validator("id", "sender_user_id", "lawyer_profile_id", "recipient_user_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else None

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


class LawyerInboxItem(BaseModel):
    user_id: str
    name: str
    last_message: str
    last_time: str
    unread_count: int = 0




