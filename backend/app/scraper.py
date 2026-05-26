import anthropic
import os
import json
import re
import httpx
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

BANK_SOURCES = [
    {"bank": "Klar", "url": "https://www.klar.mx/promociones", "card_name": "Klar Card", "wait": 3000},
    {"bank": "Nu Mexico", "url": "https://nu.com.mx/tarjeta-de-credito/", "card_name": "Nu Card", "wait": 2000},
    {"bank": "BBVA", "url": "https://www.bbva.mx/personas/productos/tarjetas-de-credito.html", "card_name": "Azul / Oro / Platinum", "wait": 2000},
    {"bank": "Citibanamex", "url": "https://www.banamex.com/es/personas/productos-financieros/tarjetas-de-credito.html", "card_name": "Simplicity / Costco", "wait": 2000},
    {"bank": "Banorte", "url": "https://www.banorte.com/wps/portal/banorte/home/para-ti/tarjetas/credito", "card_name": "Banorte Visa", "wait": 2000},
    {"bank": "HSBC", "url": "https://www.hsbc.com.mx/tarjetas-de-credito/", "card_name": "HSBC 2Now / Advance", "wait": 2000},
    {"bank": "Santander", "url": "https://www.santander.com.mx/personas/tarjetas/credito.html", "card_name": "Santander Zero / LikeU", "wait": 2000},
    {"bank": "American Express", "url": "https://www.americanexpress.com/es-mx/tarjetas-de-credito/", "card_name": "Gold / Platinum / Green", "wait": 2000},
]

def scrape_page_playwright(url: str, wait_ms: int = 2000) -> str:
    """Scrape a JS-rendered page using Playwright."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(wait_ms)
            content = page.inner_text("body")
            browser.close()
            return content[:15000]
    except Exception as e:
        print(f"Playwright error for {url}: {e}")
        return ""

def extract_promos_with_claude(text: str, bank: str, card_name: str) -> list:
    """Use Claude to extract promotions from page text."""
    if not text or len(text) < 100:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Analiza este texto de la página de promociones de {bank} (tarjeta: {card_name}) y extrae TODAS las promociones.

Texto:
{text}

IMPORTANTE: Devuelve ÚNICAMENTE el array JSON, sin texto antes ni después, sin backticks, sin ```json.
Usa EXACTAMENTE estos campos:
[
  {{
    "title": "ej: 15% cashback en Amazon",
    "description": "descripción completa",
    "cashback_percent": 15,
    "category": "online",
    "merchant": "Amazon",
    "valid_until": "2026-06-02"
  }}
]

Campos requeridos:
- title: string corto descriptivo
- description: string completo
- cashback_percent: número (ej: 15) o null si es descuento fijo
- category: dining/supermarket/gas/online/travel/general/technology/entertainment/sports
- merchant: nombre del comercio o null
- valid_until: formato YYYY-MM-DD o null

Si no hay promociones: []"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        # Remove markdown code blocks if present
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*', '', response_text)
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []
    except Exception as e:
        print(f"Claude error for {bank}: {e}")
        return []

def supabase_request(method: str, table: str, data=None, filters=None):
    """Generic Supabase REST API call."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    params = filters or {}
    with httpx.Client(timeout=15) as client:
        if method == "GET":
            r = client.get(url, headers=headers, params=params)
        elif method == "POST":
            r = client.post(url, headers=headers, json=data)
        elif method == "PATCH":
            r = client.patch(url, headers=headers, json=data, params=params)
        return r

def get_existing_promos(bank: str) -> list:
    """Get currently active promos for a bank from Supabase."""
    r = supabase_request("GET", "promotions", filters={
        "bank": f"eq.{bank}",
        "is_active": "eq.true",
        "select": "title,merchant,cashback_percent,category"
    })
    return r.json() if r.status_code == 200 else []

def promos_changed(new_promos: list, existing_promos: list) -> bool:
    """Check if promos changed — compare by merchant+cashback+category only."""
    def promo_key(p):
        return (
            str(p.get("merchant") or "").strip().lower(),
            str(p.get("cashback_percent") or ""),
            str(p.get("category") or "").strip().lower()
        )
    new_keys = set(promo_key(p) for p in new_promos)
    existing_keys = set(promo_key(p) for p in existing_promos)
    return new_keys != existing_keys

def save_promos(promos: list, bank: str, card_name: str, promo_url: str):
    """Save promos — skip if unchanged, deactivate missing ones."""
    existing = get_existing_promos(bank)

    if not promos:
        # Scraper ran but found nothing — deactivate all existing
        if existing:
            supabase_request("PATCH", "promotions", {"is_active": False}, {"bank": f"eq.{bank}"})
            print(f"Deactivated {len(existing)} promos for {bank} — none found on site")
        else:
            print(f"No promos found or existing for {bank} — skipping")
        return

    if not promos_changed(promos, existing):
        print(f"No changes detected for {bank} — skipping to save tokens")
        return

    print(f"Changes detected for {bank} — updating {len(promos)} promos")

    # Deactivate all current promos for this bank
    supabase_request("PATCH", "promotions", {"is_active": False}, {"bank": f"eq.{bank}"})

    # Insert fresh promos
    for promo in promos:
        record = {
            "bank": bank,
            "card_name": card_name,
            "title": promo.get("title", ""),
            "description": promo.get("description", ""),
            "cashback_percent": promo.get("cashback_percent"),
            "category": promo.get("category", "general"),
            "merchant": promo.get("merchant"),
            "valid_until": promo.get("valid_until"),
            "promo_url": promo_url,
            "scraped_at": datetime.now().isoformat(),
            "is_active": True
        }
        supabase_request("POST", "promotions", record)
    print(f"Saved {len(promos)} promos for {bank}")

def run_scraper():
    print(f"Starting scraper at {datetime.now()}")
    for source in BANK_SOURCES:
        print(f"Scraping {source['bank']}...")
        text = scrape_page_playwright(source["url"], source.get("wait", 2000))
        print(f"Got {len(text)} chars from {source['bank']}")
        promos = extract_promos_with_claude(text, source["bank"], source["card_name"])
        save_promos(promos, source["bank"], source["card_name"], source["url"])
    print("Scraper complete!")

if __name__ == "__main__":
    run_scraper()