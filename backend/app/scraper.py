import anthropic
import os
import json
import re
import httpx
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

BBVA_URLS = [
    {"url": "https://www.bbvadescuentos.mx/categorias/supermercados", "category": "supermarket"},
    {"url": "https://www.bbvadescuentos.mx/categorias/restaurantes", "category": "dining"},
    {"url": "https://www.bbvadescuentos.mx/categorias/comercio-electronico", "category": "online"},
    {"url": "https://www.bbvadescuentos.mx/categorias/viajes", "category": "travel"},
    {"url": "https://www.bbvadescuentos.mx/categorias/tecnologia", "category": "technology"},
    {"url": "https://www.bbvadescuentos.mx/categorias/tiendas-departamentales", "category": "general"},
    {"url": "https://www.bbvadescuentos.mx/categorias/deportes", "category": "sports"},
    {"url": "https://www.bbvadescuentos.mx/categorias/salud", "category": "general"},
]

BANK_SOURCES = [
    {"bank": "Klar", "url": "https://www.klar.mx/promociones", "card_name": "Klar Card", "wait": 3000},
    {"bank": "Nu Mexico", "url": "https://nu.com.mx/promociones/", "card_name": "Nu Card", "wait": 3000},
    {"bank": "Banorte", "url": "https://www.banorte.com/wps/portal/banorte/home/para-ti/tarjetas/credito", "card_name": "Banorte Visa", "wait": 2000},
    {"bank": "HSBC", "url": "https://www.hsbc.com.mx/tarjetas-de-credito/", "card_name": "HSBC 2Now / Advance", "wait": 2000},
    {"bank": "Santander", "url": "https://www.santander.com.mx/personas/tarjetas/credito.html", "card_name": "Santander Zero / LikeU", "wait": 2000},
    {"bank": "American Express", "url": "https://www.americanexpress.com/es-mx/tarjetas-de-credito/", "card_name": "Gold / Platinum / Green", "wait": 2000},
]

def supabase_request(method: str, table: str, data=None, filters=None):
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

def scrape_page_playwright(url: str, wait_ms: int = 2000) -> str:
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

Campos:
- title: string corto descriptivo
- description: string completo
- cashback_percent: número o null
- category: dining/supermarket/gas/online/travel/general/technology/entertainment/sports
- merchant: nombre del comercio o null
- valid_until: YYYY-MM-DD o null

Si no hay promociones: []"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()
        response_text = re.sub(r'```[a-zA-Z]*\s*', '', response_text)
        response_text = response_text.replace('```', '').strip()
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []
    except Exception as e:
        print(f"Claude error for {bank}: {e}")
        return []

def extract_banamex_promos(text: str) -> list:
    """Extract promos from Banamex in chunks to avoid token limits."""
    if not text or len(text) < 100:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_promos = []
    seen = set()

    # Process in 3000 char chunks
    chunk_size = 3000
    chunks = [text[i:i+chunk_size] for i in range(0, min(len(text), 15000), chunk_size)]

    for i, chunk in enumerate(chunks):
        print(f"  Processing Banamex chunk {i+1}/{len(chunks)}...")
        prompt = f"""Del siguiente texto de Banamex extrae TODAS las promociones.
Devuelve SOLO el array JSON sin backticks ni texto extra:
[{{"title":"...","description":"...","cashback_percent":null,"category":"dining","merchant":"...","valid_until":null}}]

Categorías: RESTAURANTES→dining, HOGAR Y OFICINA→general, MODA→general, VIAJES→travel, ENTRETENIMIENTO→entertainment, SERVICIOS→general, SALUD Y BELLEZA→general

Texto:
{chunk}"""

        try:
            message = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = message.content[0].text.strip()
            response_text = re.sub(r'```[a-zA-Z]*\s*', '', response_text)
            response_text = response_text.replace('```', '').strip()
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                promos = json.loads(json_match.group())
                for promo in promos:
                    key = str(promo.get("merchant", "")).lower()
                    if key and key not in seen:
                        seen.add(key)
                        all_promos.append(promo)
        except Exception as e:
            print(f"  Chunk {i+1} error: {e}")
            continue

    return all_promos

def get_existing_promos(bank: str) -> list:
    r = supabase_request("GET", "promotions", filters={
        "bank": f"eq.{bank}",
        "is_active": "eq.true",
        "select": "title,merchant,cashback_percent,category"
    })
    return r.json() if r.status_code == 200 else []

def promos_changed(new_promos: list, existing_promos: list) -> bool:
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
    existing = get_existing_promos(bank)
    if not promos:
        if existing:
            supabase_request("PATCH", "promotions", {"is_active": False}, {"bank": f"eq.{bank}"})
            print(f"Deactivated {len(existing)} promos for {bank}")
        else:
            print(f"No promos for {bank} — skipping")
        return
    if not promos_changed(promos, existing):
        print(f"No changes for {bank} — skipping to save tokens")
        return
    print(f"Changes detected for {bank} — updating {len(promos)} promos")
    supabase_request("PATCH", "promotions", {"is_active": False}, {"bank": f"eq.{bank}"})
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

def scrape_banamex() -> list:
    """Scrape Banamex clicking 'Ver más' repeatedly to load all promos."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            page.goto('https://www.banamex.com/sitios/promociones/filtro.html',
                     wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(5000)
            clicks = 0
            while clicks < 40:
                try:
                    ver_mas = page.locator('text=Ver más').last
                    if ver_mas.is_visible(timeout=2000):
                        ver_mas.scroll_into_view_if_needed()
                        ver_mas.click()
                        page.wait_for_timeout(1500)
                        clicks += 1
                        print(f"  Clicked 'Ver más' {clicks} times...")
                    else:
                        break
                except Exception:
                    break
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(2000)
            text = page.inner_text('body')
            browser.close()
            print(f"  Banamex total chars: {len(text)}")
            start = text.find('Resultados de Todo')
            promos_text = text[start:start+15000] if start > 0 else text[:15000]
            return extract_banamex_promos(promos_text)
    except Exception as e:
        print(f"Banamex scraper error: {e}")
        return []

def scrape_banorte() -> list:
    """Scrape Banorte promo iframe. Dismiss overlays, then navigate iframe to full promo page."""
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
            })
            page.goto('https://www.banorte.com/Personal/Tarjeta-Favorita.html',
                     wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(5000)

            # Dismiss overlays that block iframe clicks
            for sel in ['#b-cookie-banner button', '#banorteWelcomeModal button']:
                try:
                    page.locator(sel).first.click(timeout=2000)
                except Exception:
                    pass
            page.evaluate("document.querySelectorAll('#banorteWelcomeModal, #b-cookie-banner').forEach(el => el.style.display='none')")
            page.wait_for_timeout(1000)

            promo_frame = next((f for f in page.frames if 'promocionbanorte.com.mx' in f.url), None)
            if not promo_frame:
                print("  Banorte: promo iframe not found")
                browser.close()
                return []

            # Navigate iframe to the full promo listing page via JS
            promo_frame.evaluate("window.location.href = '../../../home/v2/s4/promociones-adicionales.php'")
            page.wait_for_timeout(4000)

            promo_frame = next((f for f in page.frames if 'promocionbanorte.com.mx' in f.url), None)
            text = promo_frame.inner_text('body') if promo_frame else ''
            browser.close()
            print(f"  Banorte iframe total chars: {len(text)}")
            return extract_banamex_promos(text)  # chunk-based extraction, same pattern
    except Exception as e:
        print(f"Banorte scraper error: {type(e).__name__}")
        return []

def scrape_bbva() -> list:
    """Scrape BBVA across multiple category pages and combine results."""
    all_promos = []
    seen = set()
    for source in BBVA_URLS:
        print(f"  Scraping BBVA {source['category']}...")
        text = scrape_page_playwright(source["url"], 3000)
        if not text or len(text) < 200:
            continue
        promos = extract_promos_with_claude(text, "BBVA", "Azul / Oro / Platinum")
        for promo in promos:
            key = (promo.get("title", "").lower(), promo.get("merchant", ""))
            if key not in seen:
                seen.add(key)
                promo["category"] = source["category"]
                all_promos.append(promo)
    return all_promos

def run_scraper():
    print(f"Starting scraper at {datetime.now()}")

    # BBVA — multi-URL scraper
    print("Scraping BBVA (multi-category)...")
    bbva_promos = scrape_bbva()
    save_promos(bbva_promos, "BBVA", "Azul / Oro / Platinum", "https://www.bbvadescuentos.mx")
    print(f"BBVA total: {len(bbva_promos)} promos")

    # Citibanamex — clicks "Ver más" to load all promos
    print("Scraping Citibanamex...")
    banamex_promos = scrape_banamex()
    save_promos(banamex_promos, "Citibanamex", "Simplicity / Costco", "https://www.banamex.com/sitios/promociones/filtro.html")
    print(f"Citibanamex total: {len(banamex_promos)} promos")

    # Banorte — clicks "Cargar más.." to load all promos
    print("Scraping Banorte...")
    banorte_promos = scrape_banorte()
    save_promos(banorte_promos, "Banorte", "Visa Cashback / Banorte", "https://www.banorte.com/Personal/Tarjeta-Favorita.html")
    print(f"Banorte total: {len(banorte_promos)} promos")

    # All other banks
    for source in BANK_SOURCES:
        if source["bank"] == "Banorte":
            continue
        print(f"Scraping {source['bank']}...")
        text = scrape_page_playwright(source["url"], source.get("wait", 2000))
        print(f"Got {len(text)} chars from {source['bank']}")
        promos = extract_promos_with_claude(text, source["bank"], source["card_name"])
        save_promos(promos, source["bank"], source["card_name"], source["url"])

    print("Scraper complete!")

if __name__ == "__main__":
    run_scraper()