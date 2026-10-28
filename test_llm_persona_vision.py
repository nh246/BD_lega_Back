import sys
sys.path.insert(0, 'backend')
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models import User, LlmConfig, Document
from app.core.security import create_access_token

client = TestClient(app)
db = SessionLocal()

admin = db.query(User).filter(User.role == 'admin').first()
admin_token = create_access_token({'sub': admin.email, 'role': admin.role})
headers = {'Authorization': f'Bearer {admin_token}'}

print('=== 1. Test Admin LLM Config Reset ===')
reset_res = client.post('/api/admin/llm-config/reset', headers=headers)
assert reset_res.status_code == 200, f'Expected 200, got {reset_res.status_code}: {reset_res.text}'
reset_data = reset_res.json()
print('Reset model:', reset_data.get('model_name'))
assert reset_data.get('model_name') == 'gemini-2.5-flash'
assert reset_data.get('provider') == 'gemini'
assert reset_data.get('temperature') == 0.7
assert reset_data.get('max_tokens') == 2048
assert 'BD Legal AI' in reset_data.get('system_prompt', '')
assert 'Penal Code 1860' in reset_data.get('system_prompt', '')
assert 'Practical Steps' in reset_data.get('system_prompt', '')
print('[PASS] Admin reset verified!')

print('\n=== 2. Test Admin LLM Config Prompt Execution ===')
test_res = client.post('/api/admin/llm-config/test', headers=headers, json={
    'prompt': 'What is the limitation period to file a suit for recovery of possession of immovable property in Bangladesh?'
})
assert test_res.status_code == 200, f'Expected 200, got {test_res.status_code}: {test_res.text}'
reply = test_res.json().get('reply', '')
print('Reply snippet:\n', reply[:400].encode('ascii', errors='replace').decode('ascii'))
assert 'Legal Analysis' in reply or 'legal analysis' in reply.lower()
assert 'Key Sections' in reply or 'section' in reply.lower()
assert 'Practical Steps' in reply or 'step' in reply.lower()
print('[PASS] LLM test prompt generated structured legal response with specific sections!')

print('\n=== 3. Test Vision Upload via Chat ===')
pro_user = db.query(User).filter(User.email == 'client.pro@bdlegal.ai').first()
if not pro_user:
    pro_user = db.query(User).filter(User.email == 'pro_user@bdlegal.ai').first()
pro_token = create_access_token({'sub': pro_user.email, 'role': pro_user.role})
pro_headers = {'Authorization': f'Bearer {pro_token}'}

with open('frontend/public/store_logo.jpg', 'rb') as f:
    img_bytes = f.read()

# Upload document as pro user
upload_res = client.post(
    '/api/chat/documents',
    headers=pro_headers,
    files={'file': ('store_logo.jpg', img_bytes, 'image/jpeg')}
)
print('Upload status:', upload_res.status_code)
assert upload_res.status_code == 200, f'Upload failed: {upload_res.status_code}: {upload_res.text}'
doc_id = upload_res.json().get('id')
print('Uploaded doc id:', doc_id)

# Send chat message with document attachment
chat_res = client.post(
    '/api/chat',
    headers=pro_headers,
    json={
        'content': 'Analyze the uploaded legal firm emblem image and describe what it represents.',
        'attachment_ids': [doc_id]
    }
)
print('Chat with image status:', chat_res.status_code)
assert chat_res.status_code == 200, f'Chat failed: {chat_res.status_code}: {chat_res.text}'
chat_data = chat_res.json()
print('Chat reply excerpt:\n', chat_data.get('reply', '')[:300].encode('ascii', errors='replace').decode('ascii'))
assert len(chat_data.get('reply', '')) > 20
print('[PASS] Vision upload in chat succeeded without 500 error!')

db.close()
print('\n=== ALL DELIVERABLE ASSERTIONS PASSED SUCCESSFULLY ===')
