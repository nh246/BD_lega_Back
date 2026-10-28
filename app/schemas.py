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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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
    created_at: Optional[str] = None
    plan: Optional[str] = "user_free"
    is_pro: Optional[bool] = False
    plan_code: Optional[str] = "user_free"
    plan_expires_at: Optional[str] = None
    messages_this_month: Optional[int] = 0

    @field_validator("id", mode="before")
    @classmethod
    def serialize_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_created_at(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else None


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
    presence_status: Optional[str] = "available"
    avg_rating: Optional[float] = None
    review_count: Optional[int] = 0
    verification_checklist: Optional[Dict[str, Optional[str]]] = None
    verification_note: Optional[str] = None
    bio: Optional[str] = None
    description: Optional[str] = None

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


class LawyerPaymentSettingsUpdate(BaseModel):
    payment_methods: List[Dict[str, Any]] = []
    payment_instructions: Optional[str] = None


class LawyerPaymentInfoResponse(BaseModel):
    payment_methods: List[Dict[str, Any]] = []
    payment_instructions: Optional[str] = None


class LawyerMeetingSettingsUpdate(BaseModel):
    meeting_provider: Optional[str] = None
    meeting_link: Optional[str] = None


class LawyerMeetingInfoResponse(BaseModel):
    meeting_provider: Optional[str] = None
    meeting_link: Optional[str] = None


class LawyerResponse(LawyerListResponse):
    phone: Optional[str] = None
    payment_methods: Optional[List[Dict[str, Any]]] = None
    payment_instructions: Optional[str] = None
    meeting_provider: Optional[str] = None
    meeting_link: Optional[str] = None


class LawyerUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    district: Optional[str] = None
    specialization: Optional[str] = None
    phone: Optional[str] = None
    verification_status: Optional[str] = None
    hourly_rate: Optional[int] = None
    years_exp: Optional[int] = None
    languages: Optional[str] = None
    bio: Optional[str] = None
    description: Optional[str] = None
    bar_council_id: Optional[str] = None
    bar_council_no: Optional[str] = None
    verification_checklist: Optional[Dict[str, Optional[str]]] = None
    payment_methods: Optional[List[Dict[str, Any]]] = None
    payment_instructions: Optional[str] = None
    meeting_provider: Optional[str] = None
    meeting_link: Optional[str] = None


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
    schedule_id: Optional[str] = None
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
    trx_id: Optional[str] = None
    screenshot_asset_id: Optional[str] = None
    meeting_link: Optional[str] = None
    meeting_started_at: Optional[str] = None
    meeting_ended_at: Optional[str] = None
    extended_minutes: Optional[int] = 0
    completion_requested_at: Optional[str] = None
    completion_requested_by: Optional[str] = None
    completed_at: Optional[str] = None
    case_brief: Optional[str] = None
    fee: Optional[int] = None
    has_reviewed: Optional[bool] = False
    case_id: Optional[str] = None
    bid_id: Optional[str] = None
    case_title: Optional[str] = None

    @field_validator("id", "user_id", "lawyer_id", mode="before")
    @classmethod
    def serialize_required_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("schedule_id", "case_id", "bid_id", mode="before")
    @classmethod
    def serialize_optional_uuid(cls, v):
        if v is None or v == "":
            return None
        return str(v)

    @field_validator("screenshot_asset_id", mode="before")
    @classmethod
    def serialize_screenshot_asset_id(cls, v):
        if v is None:
            return None
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
            for dt_field in ["completion_requested_at", "completed_at"]:
                v = data.get(dt_field)
                if hasattr(v, "isoformat"):
                    data[dt_field] = v.isoformat()
                elif v is not None:
                    data[dt_field] = str(v)
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

        cb = data.get("case_brief") if isinstance(data, dict) else getattr(data, "case_brief", None)
        extracted_case_id = data.get("case_id") if isinstance(data, dict) else getattr(data, "case_id", None)
        extracted_bid_id = data.get("bid_id") if isinstance(data, dict) else getattr(data, "bid_id", None)
        extracted_case_title = data.get("case_title") if isinstance(data, dict) else getattr(data, "case_title", None)

        if cb and not extracted_case_id:
            import re
            m_c = re.search(r"\[CaseID:\s*([a-f0-9\-]+)\]", str(cb))
            if m_c:
                extracted_case_id = m_c.group(1)
            m_b = re.search(r"\[BidID:\s*([a-f0-9\-]+)\]", str(cb))
            if m_b:
                extracted_bid_id = m_b.group(1)
            m_title = re.search(r"Case Acceptance:\s*(?:\[.*?\]\s*)*([^.]+?)(?:\.\s*Lawyer Pitch:|$)", str(cb))
            if m_title:
                extracted_case_title = m_title.group(1).strip()

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
            "trx_id": getattr(data, "trx_id", None),
            "screenshot_asset_id": (
                str(getattr(data, "screenshot_asset_id"))
                if getattr(data, "screenshot_asset_id", None) is not None
                else None
            ),
            "meeting_link": getattr(data, "meeting_link", None) or getattr(data, "meet_link", None),
            "meeting_started_at": (
                getattr(data, "meeting_started_at").isoformat()
                if getattr(data, "meeting_started_at", None) and hasattr(getattr(data, "meeting_started_at"), "isoformat")
                else (str(getattr(data, "meeting_started_at")) if getattr(data, "meeting_started_at", None) else None)
            ),
            "meeting_ended_at": (
                getattr(data, "meeting_ended_at").isoformat()
                if getattr(data, "meeting_ended_at", None) and hasattr(getattr(data, "meeting_ended_at"), "isoformat")
                else (str(getattr(data, "meeting_ended_at")) if getattr(data, "meeting_ended_at", None) else None)
            ),
            "extended_minutes": getattr(data, "extended_minutes", 0) or 0,
            "completion_requested_at": (
                getattr(data, "completion_requested_at").isoformat()
                if getattr(data, "completion_requested_at", None) and hasattr(getattr(data, "completion_requested_at"), "isoformat")
                else (str(getattr(data, "completion_requested_at")) if getattr(data, "completion_requested_at", None) else None)
            ),
            "completion_requested_by": (
                data.get("completion_requested_by") if isinstance(data, dict) else getattr(data, "completion_requested_by", None)
            ),
            "completed_at": (
                getattr(data, "completed_at").isoformat()
                if getattr(data, "completed_at", None) and hasattr(getattr(data, "completed_at"), "isoformat")
                else (str(getattr(data, "completed_at")) if getattr(data, "completed_at", None) else None)
            ),
            "has_reviewed": bool(
                data.get("has_reviewed", False)
                if isinstance(data, dict)
                else (getattr(data, "review", None) is not None or getattr(data, "has_reviewed", False))
            ),
            "case_brief": (
                data.get("case_brief")
                if isinstance(data, dict)
                else getattr(data, "case_brief", None)
            ),
            "fee": (
                data.get("fee")
                if isinstance(data, dict)
                else (
                    getattr(data, "fee", None)
                    if getattr(data, "fee", None) is not None
                    else (getattr(data.lawyer, "hourly_rate", None) if hasattr(data, "lawyer") and data.lawyer else None)
                )
            ),
            "case_id": extracted_case_id,
            "bid_id": extracted_bid_id,
            "case_title": extracted_case_title,
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


class BookingPaymentSubmit(BaseModel):
    trx_id: str
    screenshot_asset_id: Optional[str] = None


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
            self.model_name = "gemini-2.5-flash"
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
    api_key_status: Optional[Dict[str, bool]] = None
    credential_status: Optional[Dict[str, Any]] = None

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


class LlmTestPromptRequest(BaseModel):
    prompt: str = "Test prompt"


class LlmTestPromptResponse(BaseModel):
    response: str
    reply: Optional[str] = None
    provider: str
    model: str


class ProviderCredentialUpdate(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ProviderCredentialResponse(BaseModel):
    provider: str
    has_key: bool
    source: str  # "db" | "env" | "none"
    masked_key: Optional[str] = None
    base_url: Optional[str] = None
    updated_at: Optional[str] = None


class ProviderCredentialListResponse(BaseModel):
    credentials: List[ProviderCredentialResponse]


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
    is_popular: Optional[bool] = False
    popular: Optional[bool] = False
    sort_order: Optional[int] = 0
    is_active: Optional[bool] = True

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
        if self.is_popular is not None:
            self.popular = self.is_popular
        elif self.popular is not None:
            self.is_popular = self.popular
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
    plan_code: Optional[str] = None
    plan_id: Optional[str] = None
    provider: Optional[str] = None


class CheckoutResponse(BaseModel):
    checkout_url: Optional[str] = None
    status: Optional[str] = "initiated"
    subscription_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount: Optional[float] = None
    checkout_required: Optional[bool] = None
    redirect_url: Optional[str] = None
    session_token: Optional[str] = None


class CheckoutSessionRequest(BaseModel):
    payment_id: str
    provider: Optional[str] = "simulated"


class SimulatedConfirmRequest(BaseModel):
    session_token: str
    card_number: str
    expiry: Optional[str] = None
    cvc: Optional[str] = None


# --- Direct Messaging Schemas ---

class DirectMessageCreate(BaseModel):
    content: Optional[str] = ""
    attachment_asset_ids: Optional[List[str]] = None


class DirectMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sender_user_id: str
    lawyer_profile_id: str
    recipient_user_id: Optional[str] = None
    content: str
    attachments: Optional[List[str]] = []
    is_read: bool = False
    case_id: Optional[str] = None
    bid_id: Optional[str] = None
    created_at: str
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None

    @field_validator("id", "sender_user_id", "lawyer_profile_id", "recipient_user_id", "case_id", "bid_id", mode="before")
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


# --- Module: Reviews Schemas ---

class ReviewCreate(BaseModel):
    booking_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

    @field_validator("booking_id", mode="before")
    @classmethod
    def serialize_booking_id(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return str(v) if v is not None else ""


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_id: str
    reviewer_id: str
    reviewee_id: str
    rating: int
    comment: Optional[str] = None
    created_at: str
    reviewer_name: Optional[str] = None
    reviewer_avatar_asset_id: Optional[str] = None

    @field_validator("id", "booking_id", "reviewer_id", "reviewee_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("reviewer_avatar_asset_id", mode="before")
    @classmethod
    def serialize_avatar_id(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


# --- Module 11: Notification Schemas ---

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: str
    title: str
    message: str
    link: Optional[str] = None
    is_read: bool = False
    created_at: str

    @field_validator("id", "user_id", mode="before")
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


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    unread_count: int


# --- Module 12: Case Board Schemas ---

class CaseBidCreate(BaseModel):
    proposed_fee: Optional[int] = None
    pitch_message: str = Field(..., min_length=1, description="Pitch to the client")

    @field_validator("proposed_fee")
    @classmethod
    def validate_proposed_fee(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Proposed fee must be greater than 0 if provided.")
        return v


class CaseBidResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    lawyer_profile_id: str
    proposed_fee: Optional[int] = None
    pitch_message: str
    status: str = "pending"
    created_at: str
    lawyer_name: Optional[str] = None
    lawyer_avatar_asset_id: Optional[str] = None
    lawyer_avg_rating: Optional[float] = None

    @field_validator("id", "case_id", "lawyer_profile_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("lawyer_avatar_asset_id", mode="before")
    @classmethod
    def serialize_avatar(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


class CasePostCreate(BaseModel):
    title: str = Field(..., max_length=100)
    category: str = Field(..., max_length=100)
    description: str
    attachment_asset_ids: Optional[List[Any]] = Field(default_factory=list)

    @field_validator("attachment_asset_ids", mode="before")
    @classmethod
    def serialize_attachments(cls, v):
        if not v:
            return []
        return [str(item) for item in v]


class CasePostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    category: str
    description: str
    status: str = "open"
    attachment_asset_ids: List[str] = Field(default_factory=list)
    created_at: str
    user_name: Optional[str] = None
    user_avatar_asset_id: Optional[str] = None
    bids: Optional[List[CaseBidResponse]] = None
    bid_count: Optional[int] = 0
    my_bid: Optional[CaseBidResponse] = None
    booking_id: Optional[str] = None
    booking_status: Optional[str] = None
    booking_fee: Optional[int] = None
    booking_lawyer_id: Optional[str] = None
    booking_lawyer_name: Optional[str] = None
    booking_meeting_link: Optional[str] = None

    @field_validator("id", "user_id", "booking_id", "booking_lawyer_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("user_avatar_asset_id", mode="before")
    @classmethod
    def serialize_avatar(cls, v):
        if v is None:
            return None
        return str(v)

    @field_validator("attachment_asset_ids", mode="before")
    @classmethod
    def serialize_attachments(cls, v):
        if not v:
            return []
        return [str(item) for item in v]

    @field_validator("created_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v) if v is not None else ""


class CaseBidAcceptResponse(BaseModel):
    message: str
    booking_id: str
    case_id: str
    bid_id: str
    status: str
    fee: Optional[int] = None


class CaseBidRejectResponse(BaseModel):
    message: str
    case_id: str
    bid_id: str
    status: str


class LawyerBidSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    case_title: str
    case_status: str
    category: Optional[str] = "General"
    client_name: str
    bid_id: str
    proposed_fee: Optional[int] = None
    pitch: str
    bid_status: str
    created_at: str
    booking_id: Optional[str] = None

    @field_validator("case_id", "bid_id", mode="before")
    @classmethod
    def serialize_uuid(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("booking_id", mode="before")
    @classmethod
    def serialize_booking_id(cls, v):
        if v is None:
            return None
        return str(v)


class AdminOverviewResponse(BaseModel):
    total_users: int
    total_lawyers: int
    pending_lawyers: int
    total_bookings: int
    open_cases: int
    total_reviews: int
    monthly_messages: int
    monthly_revenue_est: float
    # Backward compatibility aliases
    active_lawyers: Optional[int] = None
    pending_verifications: Optional[int] = None


class AdminQueryLogResponse(BaseModel):
    id: str
    user_name: str
    plan_code: str
    created_at: str
    char_count: int


class AdminQueryRevealRequest(BaseModel):
    reason: Optional[str] = None


class AdminQueryRevealResponse(BaseModel):
    id: str
    content: str


class AdminLawyerApproveRequest(BaseModel):
    note: Optional[str] = None


class AdminLawyerRejectRequest(BaseModel):
    reason: Optional[str] = None


class AdminLawyerGoldRequest(BaseModel):
    grant: bool


class AdminLawyerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    bar_council_id: Optional[str] = None
    district: Optional[str] = None
    specialization: Optional[str] = None
    years_experience: Optional[int] = 8
    years_exp: Optional[int] = 8
    avg_rating: Optional[float] = 0.0
    review_count: Optional[int] = 0
    booking_count: Optional[int] = 0
    verification_status: str
    verification_paid: bool = False
    verification_note: Optional[str] = None
    verification_asset_ids: List[str] = []
    created_at: Optional[str] = None


class AdminPlanActionRequest(BaseModel):
    action: str  # "grant" | "revoke"
    duration_days: Optional[int] = 30


class AdminUserStatusRequest(BaseModel):
    status: str  # "active" | "restricted" | "blocked"


class AdminUserUsageResponse(BaseModel):
    plan_code: str
    messages_this_month: int
    monthly_limit: Optional[int] = None
    sessions_count: int
    bookings_count: int
    cases_count: int
    reviews_given: int


class ModeratorPromoteRequest(BaseModel):
    user_id: str
    scopes: List[str] = Field(default_factory=list)


class ModeratorEditRequest(BaseModel):
    name: str
    scopes: List[str] = Field(default_factory=list)


class PlanCreateRequest(BaseModel):
    code: str
    name: str
    price_monthly: float
    duration_days: Optional[int] = 30
    is_active: Optional[bool] = True
    role: Optional[str] = "user"
    description: Optional[str] = None
    features: Optional[List[str]] = Field(default_factory=list)
    is_popular: Optional[bool] = False
    sort_order: Optional[int] = 0


class PlanEditRequest(BaseModel):
    name: Optional[str] = None
    price_monthly: Optional[float] = None
    duration_days: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    features: Optional[List[str]] = None
    is_popular: Optional[bool] = None
    sort_order: Optional[int] = None







