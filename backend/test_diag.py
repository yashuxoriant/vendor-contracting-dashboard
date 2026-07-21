"""Diagnostic: verify AI credentials load inside uvicorn's Python process."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=== CONFIG ===")
from config import get_settings
s = get_settings()
print(f"endpoint : {repr(s.azure_openai_chat_endpoint)}")
print(f"key set  : {bool(s.azure_openai_api_key and 'dummy' not in s.azure_openai_api_key)}")
print(f"model    : {repr(s.azure_openai_chat_deployment)}")

print("\n=== AI CLIENT ===")
from ai.client import get_ai_client
client, model = get_ai_client()
print(f"client   : {type(client).__name__ if client else 'None'}")
print(f"model    : {model}")

if not client:
    print("\nFAIL: client is None — credentials not loading")
    sys.exit(1)

print("\n=== LIVE CALL ===")
try:
    r = client.messages.create(
        model=model,
        max_tokens=20,
        system="You are helpful.",
        messages=[{"role": "user", "content": "Say hi."}],
    )
    print(f"SUCCESS: {r.content[0].text}")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
