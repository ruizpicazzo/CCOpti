import anthropic
import os
import json
import re
import hashlib
import httpx
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # anon key — reads
# service_role key — writes (bypasses RLS). Falls back to anon if unset so the
# scraper keeps working before RLS is enabled.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or SUPABASE_KEY
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Token optimization ---------------------------------------------------------
# Extraction is a simple structured-output task → use cheap Haiku, not Sonnet.
# (The user-facing /recommend endpoint keeps a smarter model.)
EXTRACTION_MODEL = "claude-haiku-4-5"

# Content-hash cache: if a bank's raw page text is identical to the last
# successful run, skip the Claude extraction entirely (0 tokens spent).
CACHE_FILE = Path(__file__).parent / "scrape_cache.json"
# Set FORCE_REFRESH=1 to bypass the cache and re-extract everything.
FORCE_REFRESH = os.getenv("FORCE_REFRESH") == "1"

def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_cache(cache: dict):
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Cache save error: {e}")

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

def is_unchanged(bank: str, raw_text: str) -> bool:
    """True if raw page text matches the last successful run (→ skip Claude)."""
    if FORCE_REFRESH or not raw_text:
        return False
    return _load_cache().get(bank) == content_hash(raw_text)

def mark_scraped(bank: str, raw_text: str):
    """Record the hash of successfully-processed page text."""
    if not raw_text:
        return
    cache = _load_cache()
    cache[bank] = content_hash(raw_text)
    _save_cache(cache)

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

HSBC_CATEGORIES = [
    {"slug": "compras",              "category": "general"},
    {"slug": "entretenimiento",      "category": "entertainment"},
    {"slug": "fast-food",            "category": "dining"},
    {"slug": "viajes",               "category": "travel"},
    {"slug": "visa",                 "category": "general"},
    {"slug": "servicios",            "category": "general"},
    {"slug": "meses-sin-intereses",  "category": "general"},
]

BANK_SOURCES = [
    {"bank": "Klar", "url": "https://www.klar.mx/promociones", "card_name": "Klar Card", "wait": 3000},
    {"bank": "Nu Mexico", "url": "https://nu.com.mx/promociones/", "card_name": "Nu Card", "wait": 3000},
    {"bank": "Banorte", "url": "https://www.banorte.com/wps/portal/banorte/home/para-ti/tarjetas/credito", "card_name": "Banorte Visa", "wait": 2000},
    {"bank": "HSBC", "url": "https://www.hsbc.com.mx/tarjetas-de-credito/", "card_name": "HSBC 2Now / Advance", "wait": 2000},
    {"bank": "Mercado Pago", "url": "https://www.mercadopago.com.mx/credit-card", "card_name": "Mercado Pago Card", "wait": 3000},
    {"bank": "Santander", "url": "https://www.santander.com.mx/personas/tarjetas/credito.html", "card_name": "Santander Zero / LikeU", "wait": 2000},
    {"bank": "American Express", "url": "https://www.americanexpress.com/es-mx/tarjetas-de-credito/", "card_name": "Gold / Platinum / Green", "wait": 2000},
]

def supabase_request(method: str, table: str, data=None, filters=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    # Reads use the anon key; writes use the service_role key (bypasses RLS).
    key = SUPABASE_KEY if method == "GET" else SUPABASE_SERVICE_KEY
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
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
            model=EXTRACTION_MODEL,
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
                model=EXTRACTION_MODEL,
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
            if is_unchanged("Citibanamex", promos_text):
                print("  Citibanamex page unchanged — skipping extraction (0 tokens)")
                return None
            promos = extract_banamex_promos(promos_text)
            mark_scraped("Citibanamex", promos_text)
            return promos
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
            if is_unchanged("Banorte", text):
                print("  Banorte page unchanged — skipping extraction (0 tokens)")
                return None
            promos = extract_banamex_promos(text)  # chunk-based extraction, same pattern
            mark_scraped("Banorte", text)
            return promos
    except Exception as e:
        print(f"Banorte scraper error: {type(e).__name__}")
        return []

def scrape_amex() -> list:
    """Scrape American Express public promo page, cycling through carousel slides."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            page.goto("https://www.americanexpress.com/es-mx/beneficios/promociones/",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            seen_slides = set()
            all_text = ""

            # Cycle through carousel slides
            for _ in range(12):
                text = page.inner_text("body")
                idx = text.find("Offers Carousel")
                if idx > 0:
                    chunk = text[idx:idx+600]
                    if chunk not in seen_slides:
                        seen_slides.add(chunk)
                        all_text += chunk + "\n"
                try:
                    next_btn = page.locator("[aria-label='Next'], button:has-text('Next')").first
                    if next_btn.is_visible(timeout=1000):
                        next_btn.click()
                        page.wait_for_timeout(1500)
                    else:
                        break
                except Exception:
                    break

            # Also grab Multi-Card Carousel section
            full_text = page.inner_text("body")
            idx2 = full_text.find("Multi-Card Carousel")
            if idx2 > 0:
                all_text += full_text[idx2:idx2+1000]

            browser.close()
            print(f"  Amex collected {len(all_text)} chars, {len(seen_slides)} unique slides")
            if is_unchanged("American Express", all_text):
                print("  Amex page unchanged — skipping extraction (0 tokens)")
                return None
            promos = extract_promos_with_claude(all_text, "American Express", "Gold / Platinum / Green")
            mark_scraped("American Express", all_text)
            return promos
    except Exception as e:
        print(f"Amex scraper error: {type(e).__name__}")
        return []


def fetch_hsbc_category(page, slug: str) -> str:
    """Fetch raw promo text for one HSBC category, paginating all pages (no tokens)."""
    base_url = f"https://promociones.programa-mas.com.mx/busqueda/{slug}"
    page.goto(base_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    all_text = ""
    page_num = 1
    while True:
        text = page.inner_text("body")
        # Strip nav/footer noise — promos start after the category filter block
        start = text.find("Limpiar")
        chunk = text[start:start + 4000] if start > 0 else text[:4000]
        all_text += f"\n--- Página {page_num} ---\n{chunk}"

        # Check for a non-disabled Next button
        next_btn = page.locator("ngb-pagination li.page-item:not(.disabled) a[aria-label='Next']")
        if next_btn.count() == 0:
            break
        next_btn.click()
        page.wait_for_timeout(2000)
        page_num += 1
        if page_num > 10:   # safety cap
            break

    print(f"    [{slug}] {page_num} page(s), {len(all_text)} chars")
    return all_text


def scrape_hsbc() -> list:
    """Scrape all HSBC promo categories, paginating each one.

    Returns None if every category is unchanged since the last run (skip save).
    """
    # Phase 1 — fetch all category texts (no Claude/tokens)
    category_texts = []
    combined = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            for source in HSBC_CATEGORIES:
                print(f"  Fetching HSBC [{source['slug']}]...")
                raw = fetch_hsbc_category(page, source["slug"])
                category_texts.append((source["category"], raw))
                combined += raw
            browser.close()
    except Exception as e:
        print(f"HSBC scraper error: {type(e).__name__} — {e}")
        return []

    # Phase 2 — skip extraction entirely if nothing changed
    if is_unchanged("HSBC", combined):
        print("  HSBC pages unchanged — skipping extraction (0 tokens)")
        return None

    # Phase 3 — extract per category
    all_promos = []
    seen = set()
    for category, raw in category_texts:
        promos = extract_promos_with_claude(raw[:15000], "HSBC", "2Now / Advance / Débito")
        for promo in promos:
            promo["category"] = category
            key = str(promo.get("merchant", "")).strip().lower()
            if key and key not in seen:
                seen.add(key)
                all_promos.append(promo)
    mark_scraped("HSBC", combined)
    return all_promos


def scrape_bbva() -> list:
    """Scrape BBVA across multiple category pages and combine results.

    Returns None if all pages are unchanged since the last run (skip save).
    """
    # Phase 1 — fetch all category texts (no Claude/tokens)
    category_texts = []
    combined = ""
    for source in BBVA_URLS:
        print(f"  Fetching BBVA {source['category']}...")
        text = scrape_page_playwright(source["url"], 3000)
        if not text or len(text) < 200:
            continue
        category_texts.append((source["category"], text))
        combined += text

    # Phase 2 — skip extraction entirely if nothing changed
    if is_unchanged("BBVA", combined):
        print("  BBVA pages unchanged — skipping extraction (0 tokens)")
        return None

    # Phase 3 — extract per category
    all_promos = []
    seen = set()
    for category, text in category_texts:
        promos = extract_promos_with_claude(text, "BBVA", "Azul / Oro / Platinum")
        for promo in promos:
            key = (promo.get("title", "").lower(), promo.get("merchant", ""))
            if key not in seen:
                seen.add(key)
                promo["category"] = category
                all_promos.append(promo)
    mark_scraped("BBVA", combined)
    return all_promos

# Banks NOT handled by the generic loop:
#   Mercado Pago — promos are app-only, seeded manually (scraping would wipe them)
#   Santander    — blocks scraping at the network level
SKIP_BANKS = {"Mercado Pago", "Santander"}
# Banks with their own dedicated scraper (run before the generic loop).
# The generic card-listing URLs for these would overwrite good data.
DEDICATED_BANKS = {"BBVA", "Citibanamex", "American Express", "HSBC", "Banorte"}

def process(promos, bank: str, card_name: str, url: str):
    """Save promos unless the page was unchanged (promos is None → leave DB alone)."""
    if promos is None:
        print(f"{bank}: sin cambios — base de datos intacta, 0 tokens")
        return
    save_promos(promos, bank, card_name, url)
    print(f"{bank} total: {len(promos)} promos")

def run_scraper():
    print(f"Starting scraper at {datetime.now()}")
    if FORCE_REFRESH:
        print("FORCE_REFRESH=1 — cache bypassed, re-extracting everything")

    # BBVA — multi-URL scraper
    print("Scraping BBVA (multi-category)...")
    process(scrape_bbva(), "BBVA", "Azul / Oro / Platinum", "https://www.bbvadescuentos.mx")

    # Citibanamex — clicks "Ver más" to load all promos
    print("Scraping Citibanamex...")
    process(scrape_banamex(), "Citibanamex", "Simplicity / Costco", "https://www.banamex.com/sitios/promociones/filtro.html")

    # American Express — carousel scraper (public promos only)
    print("Scraping American Express...")
    process(scrape_amex(), "American Express", "Gold / Platinum / Green", "https://www.americanexpress.com/es-mx/beneficios/promociones/")

    # HSBC — multi-category + pagination scraper
    print("Scraping HSBC...")
    process(scrape_hsbc(), "HSBC", "2Now / Advance / Débito", "https://promociones.programa-mas.com.mx/")

    # Banorte — clicks "Cargar más.." to load all promos
    print("Scraping Banorte...")
    process(scrape_banorte(), "Banorte", "Visa Cashback / Banorte", "https://www.banorte.com/Personal/Tarjeta-Favorita.html")

    # All other banks (Klar, Nu Mexico) — skip dedicated/manual/blocked banks
    for source in BANK_SOURCES:
        if source["bank"] in SKIP_BANKS or source["bank"] in DEDICATED_BANKS:
            continue
        print(f"Scraping {source['bank']}...")
        text = scrape_page_playwright(source["url"], source.get("wait", 2000))
        print(f"Got {len(text)} chars from {source['bank']}")
        if is_unchanged(source["bank"], text):
            print(f"  {source['bank']}: sin cambios — 0 tokens")
            continue
        promos = extract_promos_with_claude(text, source["bank"], source["card_name"])
        save_promos(promos, source["bank"], source["card_name"], source["url"])
        mark_scraped(source["bank"], text)

    print("Scraper complete!")

if __name__ == "__main__":
    run_scraper()