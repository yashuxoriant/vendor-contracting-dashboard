"""Quick test to verify Azure AI Foundry connectivity. Delete after use."""
import anthropic
import os
from dotenv import load_dotenv

load_dotenv(".env")

ep    = os.getenv("AZURE_OPENAI_CHAT_ENDPOINT", "")
key   = os.getenv("AZURE_OPENAI_API_KEY", "")
model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")

print(f"endpoint : {ep}")
print(f"model    : {model}")
print(f"key set  : {'yes' if key and 'dummy' not in key else 'NO'}")
print()

if not ep or not key:
    print("ERROR: credentials not loaded")
    raise SystemExit(1)

try:
    c = anthropic.Anthropic(
        base_url=ep.rstrip("/"),
        api_key=key,
        default_headers={"x-ms-useragent": "anthropic-azure/1.0"},
        max_retries=0,
    )
    r = c.messages.create(
        model=model,
        max_tokens=50,
        system="You are helpful.",
        messages=[{"role": "user", "content": "Say hi in one sentence."}],
    )
    print("SUCCESS:", r.content[0].text)
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")