"""
Scrapes ballpark public prices for IT products to compare against vendor quotes.
Uses DuckDuckGo search + targeted scraping of CDW, SHI, Insight, Microsoft.
"""
import re
import time
from typing import Optional, Dict
from functools import lru_cache

@lru_cache(maxsize=500)
def search_web_price(product_query: str) -> Optional[Dict]:
    """
    Returns {'price': float, 'source': str, 'ref': str} or None.
    Cached so repeat queries don't hit the network.
    """
    try:
        from duckduckgo_search import DDGS
        
        # Search for retail price
        query = f'"{product_query}" price USD site:cdw.com OR site:shi.com OR site:insight.com OR site:microsoft.com'
        
        results = []
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        if not results:
            return None
        
        # Try to extract a price from snippets
        for r in results[:5]:
            snippet = r.get('body', '') + ' ' + r.get('title', '')
            # Match $123.45 or $1,234 patterns
            prices = re.findall(r'\$\s*([\d,]+(?:\.\d{2})?)', snippet)
            for p in prices:
                try:
                    val = float(p.replace(',', ''))
                    if 1 <= val <= 1_000_000:
                        return {
                            'price': val,
                            'source': r.get('href', ''),
                            'ref': snippet[:120]
                        }
                except ValueError:
                    continue
        
        return None
    except Exception as e:
        print(f'  ⚠️ Web search failed for "{product_query}": {e}')
        return None

def enrich_with_web_prices(record: Dict) -> Dict:
    """Add webPrice and webRef to each service line."""
    if 'services' not in record or not isinstance(record['services'], list):
        return record
    
    for svc in record['services']:
        if isinstance(svc, dict) and svc.get('name'):
            # Build query: prefer SKU, fallback to name
            query = svc.get('sku') if svc.get('sku') and svc['sku'] != '—' else svc['name']
            web = search_web_price(query)
            if web:
                svc['webPrice'] = web['price']
                svc['webRef'] = web['source'] or 'Public listing'
            time.sleep(0.5)  # rate limit
    
    return record
