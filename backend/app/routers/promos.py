from fastapi import APIRouter, HTTPException, Header
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional
import httpx
import os

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent.parent / ".env", override=True)

router = APIRouter(prefix="/promos", tags=["promotions"])

def supabase_get(table: str, params: dict = {}):
    """GET rows from Supabase. Always returns a list ([] on any error)."""
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
    }
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(url, headers=headers, params=params)
            if r.status_code != 200:
                print(f"Supabase GET {table} -> {r.status_code}: {r.text[:200]}")
                return []
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Supabase GET {table} error: {e}")
        return []

@router.get("/")
def get_all_promos():
    data = supabase_get("promotions", {"is_active": "eq.true", "order": "scraped_at.desc"})
    return {"promos": data, "total": len(data)}

@router.get("/bank/{bank_name}")
def get_promos_by_bank(bank_name: str):
    data = supabase_get("promotions", {"bank": f"eq.{bank_name}", "is_active": "eq.true"})
    return {"promos": data, "bank": bank_name}

@router.get("/category/{category}")
def get_promos_by_category(category: str):
    data = supabase_get("promotions", {"category": f"eq.{category}", "is_active": "eq.true"})
    return {"promos": data, "category": category}

@router.post("/scrape")
def trigger_scrape(x_admin_token: Optional[str] = Header(default=None)):
    """Manually trigger a full scrape. Protected by a shared admin token so it
    can't be triggered anonymously (it burns API tokens and hammers bank sites)."""
    expected = os.getenv("ADMIN_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        from app.scraper import run_scraper
        run_scraper()
        return {"status": "success", "message": "Scraper completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))