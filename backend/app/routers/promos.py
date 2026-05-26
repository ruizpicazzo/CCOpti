from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv
from pathlib import Path
import httpx
import os

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent.parent / ".env")

router = APIRouter(prefix="/promos", tags=["promotions"])

def supabase_get(table: str, params: dict = {}):
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY"),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}",
    }
    with httpx.Client(timeout=15) as client:
        r = client.get(url, headers=headers, params=params)
        return r.json()

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
def trigger_scrape():
    try:
        from app.scraper import run_scraper
        run_scraper()
        return {"status": "success", "message": "Scraper completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))