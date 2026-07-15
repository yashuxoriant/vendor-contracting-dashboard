"""Process A: LLM does the entire extraction in one shot."""
import json
from typing import Dict, Any, Optional
from config import CFG
from heuristic_extractor import load_text

AI_EXTRACT_PROMPT = """You are an IT-procurement data extraction expert.

Extract a structured quote record from this document text. Return ONLY strict JSON.

DOCUMENT FILENAME: {filename}

DOCUMENT TEXT (first 8000 chars):
{text}

Return this exact schema:
{{
  "file": "{filename}",
  "vendor": "string (e.g. NTT Data, CDW, SHI, Microsoft)",
  "project": "Panasonic|Idemia|Tenneco|Unknown",
  "cat": "Cybersecurity|Network & Telecom|Hosting|M365 & Power Platform|Service Management (SNow)|IdAM",
  "subcat": "string (specific subcategory)",
  "country": "string (e.g. Germany, United States, Japan)",
  "region": "EMEA|APAC|Americas|Global",
  "price": number (grand total in USD),
  "year": number,
  "quarter": "Q1|Q2|Q3|Q4 or null",
  "quoteDate": "YYYY-MM-DD or null",
  "services": [
    {{"name": "string", "sku": "string", "qty": number, "unitPrice": number}}
  ]
}}

Rules:
- If price is in EUR/GBP, convert to USD using 1 EUR = 1.08 USD, 1 GBP = 1.27 USD
- Extract ALL line items, not just the first few
- If a value is unknown, use null (not 0 or empty string)
- SKU should be the manufacturer part number if shown
"""

def ai_extract_full(filepath: str) -> Optional[Dict]:
    """One-shot LLM extraction (Process A)."""
    import os
    filename = os.path.basename(filepath)
    text = load_text(filepath)
    
    if not text or len(text) < 50:
        return None
    
    prompt = AI_EXTRACT_PROMPT.format(filename=filename, text=text[:8000])
    
    if CFG.has_openai():
        try:
            from openai import OpenAI
            client = OpenAI(api_key=CFG.openai_key)
            r = client.chat.completions.create(
                model=CFG.openai_model_strong,
                messages=[
                    {'role': 'system', 'content': 'You are a JSON extraction engine. Return only valid JSON.'},
                    {'role': 'user', 'content': prompt}
                ],
                response_format={'type': 'json_object'},
                temperature=0.0,
                max_tokens=4000,
            )
            return json.loads(r.choices[0].message.content)
        except Exception as e:
            print(f'  ⚠️ OpenAI extraction failed: {e}')
    
    if CFG.has_groq():
        try:
            from groq import Groq
            client = Groq(api_key=CFG.groq_key)
            r = client.chat.completions.create(
                model=CFG.groq_model,
                messages=[
                    {'role': 'system', 'content': 'You are a JSON extraction engine. Return only valid JSON.'},
                    {'role': 'user', 'content': prompt}
                ],
                response_format={'type': 'json_object'},
                temperature=0.0,
                max_tokens=4000,
            )
            return json.loads(r.choices[0].message.content)
        except Exception as e:
            print(f'  ⚠️ Groq extraction failed: {e}')
    
    return None
