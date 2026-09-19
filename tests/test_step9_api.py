"""
Step 9 Test — Verify the FastAPI backend endpoint.

Run: python tests/test_step9_api.py
"""

import sys
import time
import requests
from multiprocessing import Process
import uvicorn
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def flush_print(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def run_server():
    """Run the FastAPI server on port 8000."""
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="error")


def test_api():
    """Test the /query endpoint."""
    flush_print("Starting FastAPI server in background...")
    server_process = Process(target=run_server)
    server_process.start()
    
    try:
        # Wait for server to boot and load FAISS index
        flush_print("Waiting 8 seconds for server to load AI models...")
        time.sleep(8)
        
        # Test 1: Health check
        flush_print("\nTesting /health endpoint...")
        resp = requests.get("http://127.0.0.1:8000/health")
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            flush_print("  [PASS] Server is healthy")
        else:
            flush_print(f"  [FAIL] Server unhealthy: {resp.text}")
            return False
            
        # Test 2: Ask a legal question (must be in the first 10 sections of Penal Code)
        query = "Does the provisions of this Code apply to any offence committed outside Bangladesh?"
        flush_print(f"\nTesting /query endpoint with: '{query}'")
        
        start = time.time()
        resp = requests.post(
            "http://127.0.0.1:8000/query",
            json={"query": query},
            timeout=60
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            flush_print(f"  [PASS] API returned 200 OK (took {elapsed:.2f}s)")
            flush_print(f"\n[FINAL ANSWER]\n{data['answer']}")
            
            flush_print(f"\n[SOURCES]")
            for s in data["sources"]:
                flush_print(f"  - {s['act_title']} Sec.{s['section_number']} (Score: {s['score']})")
                
            return True
        else:
            flush_print(f"  [FAIL] API returned {resp.status_code}: {resp.text}")
            return False
            
    finally:
        flush_print("\nShutting down test server...")
        server_process.terminate()
        server_process.join()


if __name__ == "__main__":
    flush_print("=" * 50)
    flush_print("BD Legal Guide AI - Step 9 Test (FastAPI)")
    flush_print("=" * 50)

    # Note: Requires running under __main__ for multiprocessing in Windows
    success = test_api()
    
    flush_print("\n" + "=" * 50)
    if success:
        flush_print("Step 9 PASSED - Backend API is fully operational!")
    else:
        flush_print("Some checks failed - fix before proceeding.")
    flush_print("=" * 50)
