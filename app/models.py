"""
SQLAlchemy models for BD Legal Guide AI.
Contains the 12 core tables with String-based enums and UUID primary keys.
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Float,
    Integer,
    DateTime,
    Date,
    ForeignKey,
    JSON,
    LargeBinary,
    UniqueConstraint,
    Index,
)
from sqlalchemy.types import Uuid
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    # role: admin | moderator | lawyer | user
    role = Column(String(50), default="user", nullable=False)
    # status: active | blocked | restricted
    status = Column(String(50), default="active", nullable=False)
    scopes = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    lawyer_profile = relationship("LawyerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="user", foreign_keys="Booking.user_id", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id")


class LawyerProfile(Base):
    __tablename__ = "lawyer_profiles"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    bar_council_id = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    specialization = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    # verification_status: pending | approved | rejected
    verification_status = Column(String(50), default="pending", nullable=False)
    verification_paid = Column(Boolean, default=False, nullable=False)
    verification_note = Column(Text, nullable=True)
    hourly_rate = Column(Integer, default=2000, nullable=True)
    years_exp = Column(Integer, default=8, nullable=True)
    languages = Column(String(255), default="Bangla, English", nullable=True)
    payment_methods = Column(JSON, nullable=True, default=list)
    payment_instructions = Column(Text, nullable=True)
    meeting_provider = Column(String(100), nullable=True)
    meeting_link = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="lawyer_profile")
    schedules = relationship("Schedule", back_populates="lawyer", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="lawyer", foreign_keys="Booking.lawyer_id")
    payments = relationship("Payment", back_populates="lawyer_profile")


class LawFirm(Base):
    __tablename__ = "law_firms"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    contact_person = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    # status: pending | approved | rejected
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    lawyer_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(String(50), nullable=False)
    end_time = Column(String(50), nullable=False)
    is_booked = Column(Boolean, default=False, nullable=False)

    # Relationships
    lawyer = relationship("LawyerProfile", back_populates="schedules")
    booking = relationship("Booking", back_populates="schedule", uselist=False)


class LawyerWeeklyAvailability(Base):
    __tablename__ = "lawyer_weekly_availabilities"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    lawyer_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), unique=True, nullable=False)
    schedule = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    lawyer = relationship("LawyerProfile", foreign_keys=[lawyer_id])


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    lawyer_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    schedule_id = Column(Uuid, ForeignKey("schedules.id"), unique=True, nullable=False)
    # status: pending | awaiting_payment | payment_submitted | confirmed | completion_requested | completed | cancelled | expired | refund_due
    status = Column(String(50), default="pending", nullable=False)
    trx_id = Column(String(255), nullable=True)
    screenshot_asset_id = Column(Uuid, ForeignKey("profile_assets.id", ondelete="SET NULL"), nullable=True)
    meeting_link = Column(String(500), nullable=True)
    meeting_started_at = Column(DateTime, nullable=True)
    meeting_ended_at = Column(DateTime, nullable=True)
    extended_minutes = Column(Integer, default=0, nullable=False)
    completion_requested_at = Column(DateTime(timezone=True), nullable=True)
    completion_requested_by = Column(String(50), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    case_brief = Column(Text, nullable=True)
    fee = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="bookings", foreign_keys=[user_id])
    lawyer = relationship("LawyerProfile", back_populates="bookings", foreign_keys=[lawyer_id])
    schedule = relationship("Schedule", back_populates="booking")
    screenshot_asset = relationship("ProfileAsset", foreign_keys=[screenshot_asset_id])
    review = relationship("Review", back_populates="booking", uselist=False, cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id = Column(Uuid, ForeignKey("chat_sessions.id"), nullable=False)
    # role: user | assistant
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    provider = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    confidence_score = Column(Integer, nullable=True)
    confidence_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")


class LlmConfig(Base):
    __tablename__ = "llm_configs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # provider: gemini | openai | anthropic | openrouter
    provider = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7, nullable=False)
    max_tokens = Column(Integer, default=2048, nullable=False)
    system_prompt = Column(Text, nullable=True)
    disclaimer = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # provider: gemini | openai | anthropic | openrouter | mock
    provider = Column(String(50), unique=True, index=True, nullable=False)
    api_key = Column(Text, nullable=True)
    base_url = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # code: user_free | user_pro_monthly | user_pro_6m | user_pro_1y | lawyer_basic | lawyer_verified
    code = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    price_monthly = Column(Float, default=0.0, nullable=False)
    duration_days = Column(Integer, default=30, nullable=True)
    features = Column(JSON, default=list, nullable=True)
    description = Column(Text, nullable=True)
    is_popular = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    @property
    def target_role(self) -> str:
        return "lawyer" if "lawyer" in (self.code or "").lower() else "user"

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Uuid, ForeignKey("plans.id"), nullable=False)
    # status: pending | active | expired
    status = Column(String(50), default="pending", nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    subscription_id = Column(Uuid, ForeignKey("subscriptions.id"), nullable=True)
    lawyer_profile_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=True)
    # type: subscription | verification_one_time
    type = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    # provider: stripe | paddle
    provider = Column(String(50), nullable=False)
    external_ref = Column(String(255), nullable=True)
    # status: pending | paid | failed
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    subscription = relationship("Subscription", back_populates="payments")
    lawyer_profile = relationship("LawyerProfile", back_populates="payments")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    target_type = Column(String(100), nullable=True)
    target_id = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    actor = relationship("User", back_populates="audit_logs", foreign_keys=[actor_id])


class DirectMessage(Base):
    __tablename__ = "direct_messages"
    __table_args__ = (
        Index("ix_direct_messages_lawyer_created", "lawyer_profile_id", "created_at"),
        Index("ix_direct_messages_sender_created", "sender_user_id", "created_at"),
        Index("ix_direct_messages_case_bid", "case_id", "bid_id", "created_at"),
    )

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    sender_user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    lawyer_profile_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    recipient_user_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    attachments = Column(JSON, nullable=True, default=[])
    is_read = Column(Boolean, default=False, nullable=False)
    case_id = Column(Uuid, ForeignKey("case_posts.id", ondelete="CASCADE"), nullable=True)
    bid_id = Column(Uuid, ForeignKey("case_bids.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_user_id])
    recipient = relationship("User", foreign_keys=[recipient_user_id])
    lawyer_profile = relationship("LawyerProfile", foreign_keys=[lawyer_profile_id])
    case = relationship("CasePost", foreign_keys=[case_id])
    bid = relationship("CaseBid", foreign_keys=[bid_id])


class Document(Base):
    __tablename__ = "documents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)
    extracted_text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    kind = Column(String(50), default="text", nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_bytes = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_user_id])


class MonthlyUsage(Base):
    __tablename__ = "monthly_usages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    messages_used = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "year", "month", name="uq_monthly_usage_user_year_month"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])


# Backward-compatibility alias
DailyUsage = MonthlyUsage


class ProfileAsset(Base):
    __tablename__ = "profile_assets"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    kind = Column(String(50), nullable=False)  # 'avatar' or 'verification'
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_bytes = Column(LargeBinary, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_user_id])


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    booking_id = Column(Uuid, ForeignKey("bookings.id"), unique=True, nullable=False)
    reviewer_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    reviewee_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    booking = relationship("Booking", back_populates="review")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    reviewee = relationship("User", foreign_keys=[reviewee_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("ix_notifications_user_is_read_created_at", "user_id", "is_read", "created_at"),
    )


class CasePost(Base):
    __tablename__ = "case_posts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default="open", nullable=False)  # "open", "assigned", "closed"
    attachment_asset_ids = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    bids = relationship("CaseBid", back_populates="case_post", cascade="all, delete-orphan", order_by="CaseBid.created_at.desc()")


class CaseBid(Base):
    __tablename__ = "case_bids"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    case_id = Column(Uuid, ForeignKey("case_posts.id"), nullable=False)
    lawyer_profile_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    proposed_fee = Column(Integer, nullable=True)
    pitch_message = Column(Text, nullable=False)
    status = Column(String(50), default="pending", nullable=False)  # "pending", "accepted", "rejected"
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("case_id", "lawyer_profile_id", name="uq_case_lawyer_bid"),
    )

    # Relationships
    case_post = relationship("CasePost", back_populates="bids")
    lawyer_profile = relationship("LawyerProfile", foreign_keys=[lawyer_profile_id])

