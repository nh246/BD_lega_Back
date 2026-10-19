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

app = FastAPI(title="BD Legal Guide AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


@app.on_event("startup")
def on_startup():
    """Create all core database tables on application startup."""
    Base.metadata.create_all(bind=engine)


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
