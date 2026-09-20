"""
FastAPI Backend for BD Legal Guide AI.

Complete REST API with:
- Auth (register/login/logout/me)
- AI Query (RAG pipeline)
- Chat Sessions (CRUD)
- Health check

Run with: uvicorn app.main:app --reload
"""

import time
import json
import sys
import os
import platform
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db, init_db
from app.models import User, ChatSession, ChatMessage, QueryLog, SystemSetting
from app.auth import hash_password, verify_password, create_access_token, decode_access_token
from app.pipeline.embedder import load_index
from app.pipeline.retriever import build_hybrid_retriever
from app.pipeline.reranker import get_reranker
from app.pipeline.generator import generate_answer
from app.config import INDEX_DIR

app = FastAPI(title="BD Legal Guide AI API")
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://bd-legal-guide.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Global AI Pipeline ---
retriever = None
reranker = None


# ============================================================
# AUTH HELPERS
# ============================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User | None:
    """Extract user from JWT token. Returns None if no/invalid token."""
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    return user


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Like get_current_user but raises 401 if not authenticated."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(
    user: User = Depends(require_user)
) -> User:
    """Strictly verify that the user has admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Administrator privileges required.")
    return user


# ============================================================
# SYSTEM SETTINGS HELPERS
# ============================================================

DEFAULT_SETTINGS = {
    "maintenance_mode": "false",
    "allow_registrations": "true",
    "allow_free_tier": "true",
    "hybrid_search_enabled": "true",
    "reranker_enabled": "true",
    "ai_model": "gemini-2.5-flash",
    "rate_limit_per_min": "30",
    "rag_top_k": "15",
    "rag_rerank_top_n": "3"
}

def get_setting_value(db: Session, key: str, default: str) -> str:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return setting.value if setting else default

def get_all_settings(db: Session) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    rows = db.query(SystemSetting).all()
    for row in rows:
        settings[row.key] = row.value
    result = {}
    for k, v in settings.items():
        if v.lower() in ("true", "false"):
            result[k] = v.lower() == "true"
        elif v.isdigit():
            result[k] = int(v)
        else:
            result[k] = v
    return result

def set_setting_value(db: Session, key: str, value) -> None:
    val_str = str(value).lower() if isinstance(value, bool) else str(value)
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = val_str
    else:
        setting = SystemSetting(key=key, value=val_str)
        db.add(setting)
    db.commit()


# ============================================================
# SCHEMAS
# ============================================================

class AdminCreateUserRequest(BaseModel):
    name: str
    email: str
    password: str
    plan: Optional[str] = "Free"
    role: Optional[str] = "user"

class AdminUpdateUserRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    plan: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None

class AdminUserResponse(BaseModel):
    id: int
    name: str
    email: str
    plan: str
    role: str
    created_at: str
    sessions_count: int
    queries_count: int

class UpdateFeaturesRequest(BaseModel):
    maintenance_mode: Optional[bool] = None
    allow_registrations: Optional[bool] = None
    allow_free_tier: Optional[bool] = None
    hybrid_search_enabled: Optional[bool] = None
    reranker_enabled: Optional[bool] = None
    ai_model: Optional[str] = None
    rate_limit_per_min: Optional[int] = None
    rag_top_k: Optional[int] = None
    rag_rerank_top_n: Optional[int] = None

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    token: str
    user: dict

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    plan: str
    role: str

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[int] = None

class SourceSchema(BaseModel):
    act_title: str
    section_number: str
    year: str
    score: int

class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceSchema]
    processing_time_ms: int
    session_id: Optional[int] = None

class SessionResponse(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: list
    processing_time_ms: Optional[int]
    created_at: str


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():
    global retriever, reranker

    # Create database tables
    init_db()
    print("Database initialized (SQLite).")

    # Seed admin account if it doesn't exist
    db = next(get_db())
    admin = db.query(User).filter(User.email == "admin1@gmail.com").first()
    if not admin:
        admin = User(
            name="System Admin",
            email="admin1@gmail.com",
            password_hash=hash_password("admin1"),
            plan="Enterprise",
            role="admin"
        )
        db.add(admin)
        db.commit()
        print("Admin account created: admin1@gmail.com / admin1")
    else:
        # Ensure role is admin
        if admin.role != "admin":
            admin.role = "admin"
            db.commit()

    # Seed default system settings
    for k, v in DEFAULT_SETTINGS.items():
        exist = db.query(SystemSetting).filter(SystemSetting.key == k).first()
        if not exist:
            db.add(SystemSetting(key=k, value=v))
    db.commit()
    db.close()

    # Load AI pipeline
    print("Initializing AI Pipeline...")
    try:
        test_path = str(INDEX_DIR / "test_mini")
        faiss_index, chunks = load_index(test_path)
        print(f"Loaded index with {faiss_index.ntotal} vectors.")
        retriever = build_hybrid_retriever(faiss_index, chunks, top_k=15)
        reranker = get_reranker(top_n=3)
        print("Pipeline initialized successfully!")
    except FileNotFoundError:
        print("WARNING: Index not found! AI queries will fail.")
    except Exception as e:
        print(f"ERROR initializing pipeline: {e}")


# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new user account."""
    if get_setting_value(db, "allow_registrations", "true") == "false":
        raise HTTPException(status_code=403, detail="New user registration is currently disabled by system administrator.")

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    user = User(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        plan="Free",
        role="user"
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        token=token,
        user={"id": user.id, "name": user.name, "email": user.email, "plan": user.plan, "role": user.role}
    )


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate an existing user."""
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="No account found with this email.")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    token = create_access_token(user.id, user.email)
    return AuthResponse(
        token=token,
        user={"id": user.id, "name": user.name, "email": user.email, "plan": user.plan, "role": user.role}
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(user: User = Depends(require_user)):
    """Get the current logged-in user's profile."""
    return UserResponse(id=user.id, name=user.name, email=user.email, plan=user.plan, role=user.role)


# ============================================================
# CHAT SESSION ENDPOINTS
# ============================================================

@app.get("/api/sessions", response_model=List[SessionResponse])
def list_sessions(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """List all chat sessions for the current user (newest first)."""
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).all()
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
            message_count=len(s.messages)
        ) for s in sessions
    ]


@app.post("/api/sessions", response_model=SessionResponse)
def create_session(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Create a new chat session."""
    session = ChatSession(user_id=user.id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse(
        id=session.id, title=session.title,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        message_count=0
    )


@app.get("/api/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_session_messages(session_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Get all messages in a chat session."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    return [
        MessageResponse(
            id=m.id, role=m.role, content=m.content,
            sources=json.loads(m.sources_json) if m.sources_json else [],
            processing_time_ms=m.processing_time_ms,
            created_at=m.created_at.isoformat()
        ) for m in session.messages
    ]


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Delete a chat session and all its messages."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    db.delete(session)
    db.commit()
    return {"status": "deleted"}


# ============================================================
# AI QUERY ENDPOINT
# ============================================================

@app.post("/api/query", response_model=QueryResponse)
def query_legal_ai(
    request: QueryRequest,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Main AI query endpoint. Runs the full RAG pipeline."""
    if not retriever or not reranker:
        raise HTTPException(status_code=503, detail="AI Pipeline not initialized. Check server logs.")

    # Check maintenance mode
    if get_setting_value(db, "maintenance_mode", "false") == "true" and user.role != "admin":
        raise HTTPException(status_code=503, detail="System is currently in maintenance mode. Please try again later.")

    # Check free tier access
    if get_setting_value(db, "allow_free_tier", "true") == "false" and user.plan == "Free" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Free tier queries are temporarily suspended by administrator. Please upgrade your plan.")

    start_time = time.time()

    try:
        # 1. Retrieve
        retrieved_docs = retriever.invoke(request.query)

        # 2. Rerank (if enabled)
        if get_setting_value(db, "reranker_enabled", "true") == "true":
            reranked_docs = reranker.compress_documents(retrieved_docs, request.query)
        else:
            reranked_docs = retrieved_docs[:3]

        # 3. Generate
        result = generate_answer(request.query, reranked_docs)
        processing_time_ms = int((time.time() - start_time) * 1000)

        sources = result["sources"]
        sources_json_str = json.dumps(sources)

        # --- Save to DB ---
        # Ensure session exists
        session_id = request.session_id
        if session_id:
            session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user.id).first()
            if not session:
                session_id = None

        if not session_id:
            session = ChatSession(user_id=user.id, title=request.query[:50])
            db.add(session)
            db.commit()
            db.refresh(session)
            session_id = session.id
        else:
            # Update title if it's still "New Chat"
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session and session.title == "New Chat":
                session.title = request.query[:50]

        # Save user message
        user_msg = ChatMessage(session_id=session_id, role="user", content=request.query)
        db.add(user_msg)

        # Save AI response
        ai_msg = ChatMessage(
            session_id=session_id, role="assistant",
            content=result["answer"],
            sources_json=sources_json_str,
            processing_time_ms=processing_time_ms
        )
        db.add(ai_msg)

        # Save to query log
        log = QueryLog(
            user_id=user.id,
            query_text=request.query,
            answer_text=result["answer"],
            sources_json=sources_json_str,
            processing_time_ms=processing_time_ms
        )
        db.add(log)
        db.commit()

        return QueryResponse(
            answer=result["answer"],
            sources=sources,
            processing_time_ms=processing_time_ms,
            session_id=session_id
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# LEGACY QUERY (no auth, for backward compat during dev)
# ============================================================

@app.post("/query", response_model=QueryResponse)
def query_legacy(request: QueryRequest):
    """Legacy endpoint without auth — for quick testing."""
    if not retriever or not reranker:
        raise HTTPException(status_code=503, detail="AI Pipeline not initialized.")

    start_time = time.time()
    try:
        retrieved_docs = retriever.invoke(request.query)
        reranked_docs = reranker.compress_documents(retrieved_docs, request.query)
        result = generate_answer(request.query, reranked_docs)
        processing_time_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            answer=result["answer"],
            sources=result["sources"],
            processing_time_ms=processing_time_ms
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# ADMIN ENDPOINTS (Strict Admin Security)
# ============================================================

@app.get("/api/admin/stats")
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Get system statistics and metrics (admin only)."""
    total_users = db.query(User).count()
    total_queries = db.query(QueryLog).count()
    total_sessions = db.query(ChatSession).count()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_queries = db.query(QueryLog).filter(QueryLog.created_at >= today_start).count()

    active_users = db.query(QueryLog.user_id).filter(QueryLog.user_id.isnot(None)).distinct().count()

    avg_latency = db.query(func.avg(QueryLog.processing_time_ms)).scalar() or 0

    free_users = db.query(User).filter(User.plan == "Free").count()
    pro_users = db.query(User).filter(User.plan == "Pro").count()
    ent_users = db.query(User).filter(User.plan == "Enterprise").count()

    return {
        "total_users": total_users,
        "total_queries": total_queries,
        "total_sessions": total_sessions,
        "today_queries": today_queries,
        "active_users": active_users,
        "avg_latency_ms": round(float(avg_latency), 1),
        "index_loaded": retriever is not None,
        "plans": {
            "Free": free_users,
            "Pro": pro_users,
            "Enterprise": ent_users
        }
    }


@app.get("/api/admin/users", response_model=List[AdminUserResponse])
def admin_list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all registered users with usage stats."""
    users = db.query(User).order_by(User.id.desc()).all()
    result = []
    for u in users:
        sess_count = len(u.sessions) if u.sessions else 0
        q_count = db.query(QueryLog).filter(QueryLog.user_id == u.id).count()
        result.append(
            AdminUserResponse(
                id=u.id,
                name=u.name,
                email=u.email,
                plan=u.plan or "Free",
                role=u.role or "user",
                created_at=u.created_at.isoformat() if u.created_at else "",
                sessions_count=sess_count,
                queries_count=q_count
            )
        )
    return result


@app.post("/api/admin/users", response_model=AdminUserResponse)
def admin_create_user(
    req: AdminCreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin can create new user or new admin."""
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    new_user = User(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        plan=req.plan or "Free",
        role=req.role or "user"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return AdminUserResponse(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        plan=new_user.plan,
        role=new_user.role,
        created_at=new_user.created_at.isoformat() if new_user.created_at else "",
        sessions_count=0,
        queries_count=0
    )


@app.put("/api/admin/users/{user_id}", response_model=AdminUserResponse)
def admin_update_user(
    user_id: int,
    req: AdminUpdateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update user's plan, role, name, or password."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Safeguard: prevent demoting master admin (admin1@gmail.com) away from admin role
    if target_user.email == "admin1@gmail.com" and req.role and req.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot revoke admin role from master admin (admin1@gmail.com).")

    if req.name is not None:
        target_user.name = req.name
    if req.email is not None:
        exist = db.query(User).filter(User.email == req.email, User.id != user_id).first()
        if exist:
            raise HTTPException(status_code=400, detail="Email is already taken by another account.")
        target_user.email = req.email
    if req.plan is not None:
        target_user.plan = req.plan
    if req.role is not None:
        target_user.role = req.role
    if req.password:
        target_user.password_hash = hash_password(req.password)

    db.commit()
    db.refresh(target_user)

    sess_count = len(target_user.sessions) if target_user.sessions else 0
    q_count = db.query(QueryLog).filter(QueryLog.user_id == target_user.id).count()

    return AdminUserResponse(
        id=target_user.id,
        name=target_user.name,
        email=target_user.email,
        plan=target_user.plan,
        role=target_user.role,
        created_at=target_user.created_at.isoformat() if target_user.created_at else "",
        sessions_count=sess_count,
        queries_count=q_count
    )


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a user, cascade cleaning their sessions, messages, and query logs."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")

    if target_user.email == "admin1@gmail.com":
        raise HTTPException(status_code=400, detail="Cannot delete master administrator (admin1@gmail.com).")

    if target_user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own active admin account.")

    # Delete associated query logs explicitly
    db.query(QueryLog).filter(QueryLog.user_id == user_id).delete()
    # Delete user (sessions and messages cascade via relationship)
    db.delete(target_user)
    db.commit()

    return {"status": "success", "message": f"User {target_user.email} successfully deleted."}


@app.get("/api/admin/queries")
def admin_query_logs(
    limit: int = 50,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """View recent query audit logs with latency, answer snippets, and user info."""
    logs = (
        db.query(QueryLog, User.email, User.name)
        .outerjoin(User, QueryLog.user_id == User.id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .all()
    )

    results = []
    for log, email, name in logs:
        sources = json.loads(log.sources_json) if log.sources_json else []
        results.append({
            "id": log.id,
            "user_id": log.user_id,
            "user_email": email or "Guest/Unassigned",
            "user_name": name or "Anonymous",
            "query_text": log.query_text,
            "answer_snippet": (log.answer_text[:140] + "...") if log.answer_text and len(log.answer_text) > 140 else (log.answer_text or ""),
            "processing_time_ms": log.processing_time_ms or 0,
            "sources_count": len(sources),
            "sources": sources,
            "created_at": log.created_at.isoformat() if log.created_at else ""
        })
    return results


@app.get("/api/admin/features")
def admin_get_features(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Get all feature flags and monitor settings."""
    return get_all_settings(db)


@app.put("/api/admin/features")
def admin_update_features(
    req: UpdateFeaturesRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update feature flags and system settings."""
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            set_setting_value(db, k, v)
    return get_all_settings(db)


@app.get("/api/admin/system")
def admin_system_diagnostics(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """System health, diagnostics, database and index stats."""
    db_file = os.path.join(os.path.dirname(__file__), "..", "legal_ai.db")
    db_size_kb = 0
    if os.path.exists(db_file):
        db_size_kb = round(os.path.getsize(db_file) / 1024, 2)
    elif os.path.exists("legal_ai.db"):
        db_size_kb = round(os.path.getsize("legal_ai.db") / 1024, 2)

    vectors_count = 0
    try:
        test_path = str(INDEX_DIR / "test_mini.faiss")
        if os.path.exists(test_path):
            import faiss
            idx = faiss.read_index(test_path)
            vectors_count = idx.ntotal
    except Exception:
        pass

    return {
        "status": "healthy",
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "database": {
            "engine": "SQLite",
            "size_kb": db_size_kb,
            "users_count": db.query(User).count(),
            "sessions_count": db.query(ChatSession).count(),
            "messages_count": db.query(ChatMessage).count(),
            "logs_count": db.query(QueryLog).count()
        },
        "rag_pipeline": {
            "index_loaded": retriever is not None,
            "vector_store": "FAISS",
            "vectors_indexed": vectors_count,
            "total_acts_corpus": 1484,
            "total_sections_corpus": 35420,
            "embedding_model": "models/text-embedding-004",
            "llm_model": "gemini-2.5-flash"
        }
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
def health_check():
    return {"status": "ok", "index_loaded": retriever is not None, "database": "sqlite"}
