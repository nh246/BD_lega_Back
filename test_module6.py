"""
Integration test suite for Module 6: LLM Config and AI Chat.
Tests admin LLM config management, chat access restrictions,
conversation history preservation, session listing, message history,
mock and gemini provider handling, and 502 error fallback.
"""

import sys
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.database import SessionLocal
from app.core.security import get_password_hash, create_access_token
from app.models import User, LlmConfig, ChatSession, ChatMessage, AuditLog


def run_tests():
    print("--- Starting Module 6 Integration Tests ---")
    client = TestClient(app)
    db: Session = SessionLocal()

    try:
        # 1. Verify health check
        health_resp = client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json()["db"] == "connected"
        print("[PASS] Database and health check connected")

        # 2. Setup Test Fixtures
        test_emails = [
            "m6_admin@example.com",
            "m6_user@example.com",
            "m6_restricted@example.com",
            "m6_other_user@example.com",
        ]
        users = db.query(User).filter(User.email.in_(test_emails)).all()
        user_ids = [u.id for u in users]
        if user_ids:
            sessions = db.query(ChatSession).filter(ChatSession.user_id.in_(user_ids)).all()
            session_ids = [s.id for s in sessions]
            if session_ids:
                db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)
            for u in users:
                db.delete(u)
            db.commit()

        admin_user = User(
            email="m6_admin@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M6 Admin",
            role="admin",
            status="active",
        )
        regular_user = User(
            email="m6_user@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M6 Regular User",
            role="user",
            status="active",
        )
        restricted_user = User(
            email="m6_restricted@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M6 Restricted User",
            role="user",
            status="restricted",
        )
        other_user = User(
            email="m6_other_user@example.com",
            password_hash=get_password_hash("password123"),
            full_name="M6 Other User",
            role="user",
            status="active",
        )

        db.add_all([admin_user, regular_user, restricted_user, other_user])
        db.commit()

        admin_token = create_access_token({"sub": admin_user.email, "role": "admin"})
        user_token = create_access_token({"sub": regular_user.email, "role": "user"})
        restricted_token = create_access_token({"sub": restricted_user.email, "role": "user"})
        other_user_token = create_access_token({"sub": other_user.email, "role": "user"})

        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_headers = {"Authorization": f"Bearer {user_token}"}
        restricted_headers = {"Authorization": f"Bearer {restricted_token}"}
        other_headers = {"Authorization": f"Bearer {other_user_token}"}

        print("[PASS] Test fixtures created (Admin, Regular, Restricted, Other)")

        # 3. LLM Config Endpoints
        # Non-admin user tries to access llm-config -> 403
        resp = client.get("/api/admin/llm-config", headers=user_headers)
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("[PASS] Non-admin denied from accessing LLM config (403)")

        # Admin gets active llm-config -> 200
        resp = client.get("/api/admin/llm-config", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        active_config = resp.json()
        assert "provider" in active_config
        assert "model_name" in active_config
        print(f"[PASS] Admin retrieved active LLM config (provider={active_config['provider']})")

        # Admin updates LLM config to mock provider -> 200
        mock_config_payload = {
            "provider": "mock",
            "model_name": "mock-legal-v1",
            "temperature": 0.3,
            "max_tokens": 1024,
            "system_prompt": "You are a Bangladesh legal AI testing assistant.",
            "disclaimer": "Test disclaimer for legal advice.",
            "is_active": True,
        }
        resp = client.put("/api/admin/llm-config", json=mock_config_payload, headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200 on config update, got {resp.status_code}: {resp.text}"
        updated_config = resp.json()
        assert updated_config["provider"] == "mock"
        assert updated_config["model_name"] == "mock-legal-v1"
        assert updated_config["is_active"] is True
        config_id = updated_config["id"]
        print("[PASS] Admin updated LLM config to mock provider")

        # Verify audit log for llm_config_updated
        db.expire_all()
        audit_entry = (
            db.query(AuditLog)
            .filter(AuditLog.action == "llm_config_updated", AuditLog.target_id == config_id)
            .first()
        )
        assert audit_entry is not None, "Audit log for llm_config_updated was not recorded"
        assert audit_entry.actor_id == admin_user.id
        print("[PASS] Audit log entry verified: llm_config_updated")

        # 4. Chat Access Restrictions
        # Restricted user attempts to send message -> 403 "Chat access restricted"
        resp = client.post(
            "/api/chat",
            json={"content": "Can I seek bail?"},
            headers=restricted_headers,
        )
        assert resp.status_code == 403, f"Expected 403 for restricted user, got {resp.status_code}"
        assert "Chat access restricted" in resp.json().get("detail", "")
        print("[PASS] Restricted user denied chat access (403: Chat access restricted)")

        # 5. Chat Messaging & Session Creation
        # Regular user initiates chat without session_id -> creates new session
        resp = client.post(
            "/api/chat",
            json={"content": "What are the essential elements of a valid contract under Contract Act 1872?"},
            headers=user_headers,
        )
        assert resp.status_code == 200, f"Expected 200 on chat, got {resp.status_code}: {resp.text}"
        chat_data = resp.json()
        assert "reply" in chat_data
        assert "mock response" in chat_data["reply"].lower()
        assert chat_data["provider"] == "mock"
        assert chat_data["model"] == "mock-legal-v1"
        assert chat_data["disclaimer"] == "Test disclaimer for legal advice."
        session_id = chat_data["session_id"]
        assert session_id is not None
        print(f"[PASS] Chat message processed and new session created ({session_id})")

        # Send follow-up message in the same session
        resp = client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "content": "What happens if consideration is unlawful?",
            },
            headers=user_headers,
        )
        assert resp.status_code == 200
        chat_data2 = resp.json()
        assert chat_data2["session_id"] == session_id
        print("[PASS] Follow-up chat message processed in existing session with history")

        # Verify chat messages in database
        db.expire_all()
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == uuid.UUID(session_id))
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        assert len(msgs) == 4, f"Expected 4 messages (2 user, 2 assistant), got {len(msgs)}"
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        assert msgs[2].role == "user"
        assert msgs[3].role == "assistant"
        print("[PASS] 4 conversation turns persisted correctly in chat_messages table")

        # 6. Chat Sessions Listing & Detail
        # GET /api/chat/sessions for regular user
        resp = client.get("/api/chat/sessions", headers=user_headers)
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) >= 1
        assert any(s["id"] == session_id for s in sessions)
        print("[PASS] GET /api/chat/sessions returned active user's session list")

        # GET /api/chat/sessions/{session_id}
        resp = client.get(f"/api/chat/sessions/{session_id}", headers=user_headers)
        assert resp.status_code == 200
        session_msgs = resp.json()
        assert len(session_msgs) == 4
        print("[PASS] GET /api/chat/sessions/{id} returned all messages for the session")

        # Other user tries to access this session -> 403
        resp = client.get(f"/api/chat/sessions/{session_id}", headers=other_headers)
        assert resp.status_code == 403
        print("[PASS] Other user forbidden from accessing private chat session (403)")

        # 7. LLM Failure Handling (502 Bad Gateway)
        # Update config to an unsupported provider to force exception in adapter
        invalid_config_payload = {
            "provider": "unsupported_fail_provider",
            "model_name": "broken-model",
            "temperature": 0.7,
            "max_tokens": 1024,
            "system_prompt": "broken",
            "disclaimer": "broken",
            "is_active": True,
        }
        client.put("/api/admin/llm-config", json=invalid_config_payload, headers=admin_headers)

        # Attempt chat
        resp = client.post(
            "/api/chat",
            json={"content": "This should fail with 502"},
            headers=user_headers,
        )
        assert resp.status_code == 502, f"Expected 502 Bad Gateway on LLM failure, got {resp.status_code}"
        err_json = resp.json()
        assert err_json.get("error") == "AI service temporarily unavailable. Please try again."
        print("[PASS] 502 Bad Gateway returned on LLM failure with specified error payload")

        # Restore active config to mock or gemini
        client.put("/api/admin/llm-config", json=mock_config_payload, headers=admin_headers)

        # 8. Clean up test records
        db.query(ChatMessage).filter(ChatMessage.session_id == uuid.UUID(session_id)).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.id == uuid.UUID(session_id)).delete(synchronize_session=False)
        for u in [admin_user, regular_user, restricted_user, other_user]:
            db.delete(u)
        db.commit()
        print("[PASS] Test cleanup completed")

        print("\n==========================================")
        print(" ALL MODULE 6 TESTS PASSED SUCCESSFULLY! ")
        print("==========================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_tests()
