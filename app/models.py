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
    date = Column(String(50), nullable=False)
    start_time = Column(String(50), nullable=False)
    end_time = Column(String(50), nullable=False)
    is_booked = Column(Boolean, default=False, nullable=False)

    # Relationships
    lawyer = relationship("LawyerProfile", back_populates="schedules")
    booking = relationship("Booking", back_populates="schedule", uselist=False)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    lawyer_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    schedule_id = Column(Uuid, ForeignKey("schedules.id"), unique=True, nullable=False)
    # status: pending | confirmed | cancelled
    status = Column(String(50), default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="bookings", foreign_keys=[user_id])
    lawyer = relationship("LawyerProfile", back_populates="bookings", foreign_keys=[lawyer_id])
    schedule = relationship("Schedule", back_populates="booking")


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


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # code: user_free | user_pro | lawyer_basic | lawyer_verified
    code = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    price_monthly = Column(Float, default=0.0, nullable=False)
    features = Column(JSON, nullable=True)

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

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    sender_user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    lawyer_profile_id = Column(Uuid, ForeignKey("lawyer_profiles.id"), nullable=False)
    recipient_user_id = Column(Uuid, ForeignKey("users.id"), nullable=True)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_user_id])
    recipient = relationship("User", foreign_keys=[recipient_user_id])
    lawyer_profile = relationship("LawyerProfile", foreign_keys=[lawyer_profile_id])


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


class DailyUsage(Base):
    __tablename__ = "daily_usage"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False)
    day = Column(Date, nullable=False)
    messages_used = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_daily_usage_user_day"),
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])



