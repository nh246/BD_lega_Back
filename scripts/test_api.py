import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={api_key}"
data = {
    "model": "models/text-embedding-004",
    "content": {
        "parts": [{"text": "Hello world"}]
    }
}
headers = {'Content-Type': 'application/json'}

try:
    print(f"Testing API key: {api_key[:10]}...")
    response = requests.post(url, headers=headers, json=data, timeout=10)
    print("Status:", response.status_code)
    print("Response:", response.text)
except Exception as e:
    print("Error:", str(e))
