"""
BD Legal Guide AI — Backend API
Entrypoint with database initialization and health check.
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import Base, engine, get_db
import app.models  # Ensure all 12 models are registered with Base.metadata
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.lawyers import router as lawyer_router
from app.routers.firms import router as firm_router
from app.routers.schedules import router as schedule_router
from app.routers.bookings import router as booking_router
from app.routers.chat import router as chat_router
from app.routers.llm_config import router as llm_config_router
from app.routers.payments import router as payment_router
from app.routers.messages import router as messages_router, compat_router as messages_compat_router
from app.routers.documents import router as documents_router
from app.routers.assets import router as assets_router
from app.routers.reviews import router as reviews_router
from app.routers.notifications import router as notifications_router, compat_router as notifications_compat_router
from app.routers.cases import router as cases_router

app = FastAPI(title="BD Legal Guide AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(lawyer_router)
app.include_router(firm_router)
app.include_router(schedule_router)
app.include_router(booking_router)
app.include_router(chat_router)
app.include_router(llm_config_router)
app.include_router(payment_router)
app.include_router(messages_router)
app.include_router(messages_compat_router)
app.include_router(documents_router)
app.include_router(assets_router)
app.include_router(reviews_router)
app.include_router(notifications_router)
app.include_router(notifications_compat_router)
app.include_router(cases_router)




@app.on_event("startup")
def on_startup():
    """Create all core database tables on application startup and ensure schema migrations."""
    # 1. Drop old daily usage tables if present
    try:
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS daily_usages CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS daily_usage CASCADE"))
            conn.commit()
    except Exception:
        pass

    # 2. Create newly registered models (including monthly_usages)
    Base.metadata.create_all(bind=engine)

    # 3. Column migrations
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if inspector.has_table('lawyer_profiles'):
            cols = [c['name'] for c in inspector.get_columns('lawyer_profiles')]
            with engine.connect() as conn:
                if 'hourly_rate' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN hourly_rate INTEGER DEFAULT 2000"))
                if 'years_exp' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN years_exp INTEGER DEFAULT 8"))
                if 'languages' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN languages VARCHAR(255) DEFAULT 'Bangla, English'"))
                if 'payment_methods' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN payment_methods JSON DEFAULT '[]'::json"))
                if 'payment_instructions' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN payment_instructions TEXT"))
                if 'meeting_provider' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN meeting_provider VARCHAR(100)"))
                if 'meeting_link' not in cols:
                    conn.execute(text("ALTER TABLE lawyer_profiles ADD COLUMN meeting_link VARCHAR(500)"))
                conn.commit()

        if inspector.has_table('bookings'):
            booking_cols = [c['name'] for c in inspector.get_columns('bookings')]
            with engine.connect() as conn:
                if 'trx_id' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN trx_id VARCHAR(255)"))
                if 'screenshot_asset_id' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN screenshot_asset_id UUID REFERENCES profile_assets(id) ON DELETE SET NULL"))
                if 'meeting_link' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_link VARCHAR(500)"))
                if 'meeting_started_at' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_started_at TIMESTAMP WITH TIME ZONE"))
                if 'meeting_ended_at' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN meeting_ended_at TIMESTAMP WITH TIME ZONE"))
                if 'extended_minutes' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN extended_minutes INTEGER DEFAULT 0"))
                if 'completion_requested_at' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN completion_requested_at TIMESTAMP WITH TIME ZONE"))
                if 'completion_requested_by' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN completion_requested_by VARCHAR(50)"))
                if 'completed_at' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE"))
                if 'case_brief' not in booking_cols:
                    conn.execute(text("ALTER TABLE bookings ADD COLUMN case_brief TEXT"))
                conn.commit()

        if inspector.has_table('plans'):
            plan_cols = [c['name'] for c in inspector.get_columns('plans')]
            with engine.connect() as conn:
                if 'duration_days' not in plan_cols:
                    conn.execute(text("ALTER TABLE plans ADD COLUMN duration_days INTEGER DEFAULT 30"))
                conn.commit()

        if inspector.has_table('direct_messages'):
            dm_cols = [c['name'] for c in inspector.get_columns('direct_messages')]
            with engine.connect() as conn:
                if 'attachments' not in dm_cols:
                    conn.execute(text("ALTER TABLE direct_messages ADD COLUMN attachments JSON DEFAULT '[]'::json"))
                conn.commit()
    except Exception:
        pass

    # 4. Ensure exact plans exist
    try:
        from app.core.database import SessionLocal
        from app.core.plans import ensure_plans_exist
        db = SessionLocal()
        try:
            ensure_plans_exist(db)
        finally:
            db.close()
    except Exception:
        pass

    # 5. One-time schedule slot data fix (ensure end_time != start_time)
    try:
        from app.core.database import SessionLocal
        from app.models import Schedule
        from datetime import datetime, timedelta
        db = SessionLocal()
        try:
            schedules = db.query(Schedule).all()
            changed = False
            for s in schedules:
                st = (s.start_time or "").strip()
                et = (s.end_time or "").strip()
                if st and (not et or et == st or "(30m)" in et or (et.startswith(st) and len(et) > len(st))):
                    clean_st = st.replace(".", "").strip()
                    for fmt in ["%I:%M %p", "%I:%M%p", "%H:%M"]:
                        try:
                            parsed_dt = datetime.strptime(clean_st, fmt)
                            s.start_time = parsed_dt.strftime("%I:%M %p")
                            s.end_time = (parsed_dt + timedelta(minutes=30)).strftime("%I:%M %p")
                            changed = True
                            break
                        except ValueError:
                            continue
            if changed:
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok",
        "service": "BD Legal Guide AI API",
        "db": db_status,
    }
