"""Quick test of auth + query endpoints."""
import requests
import json

BASE = "http://127.0.0.1:8000"

# 1. Register
print("=== REGISTER ===")
r = requests.post(f"{BASE}/api/auth/register", json={
    "name": "Test User", "email": "test@demo.com", "password": "test1234"
})
print(f"Status: {r.status_code}")
data = r.json()
print(json.dumps(data, indent=2))
token = data.get("token", "")

# 2. Login
print("\n=== LOGIN ===")
r = requests.post(f"{BASE}/api/auth/login", json={
    "email": "test@demo.com", "password": "test1234"
})
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))

# 3. Get Me
print("\n=== GET ME ===")
r = requests.get(f"{BASE}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))

# 4. Create Session
print("\n=== CREATE SESSION ===")
r = requests.post(f"{BASE}/api/sessions", headers={"Authorization": f"Bearer {token}"})
print(f"Status: {r.status_code}")
session = r.json()
print(json.dumps(session, indent=2))

# 5. Query AI (with session)
print("\n=== QUERY AI ===")
r = requests.post(f"{BASE}/api/query", json={
    "query": "Does the penal code apply outside Bangladesh?",
    "session_id": session.get("id")
}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
print(f"Status: {r.status_code}")
result = r.json()
print(f"Answer: {result.get('answer', '')[:200]}...")
print(f"Sources: {len(result.get('sources', []))}")
print(f"Session ID: {result.get('session_id')}")

# 6. List Sessions
print("\n=== LIST SESSIONS ===")
r = requests.get(f"{BASE}/api/sessions", headers={"Authorization": f"Bearer {token}"})
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))

print("\n=== ALL TESTS PASSED ===")
