from fastapi import FastAPI, HTTPException
from app.routers import promos
from app import recommendation
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=True)

app = FastAPI(
    title="CardMax MX API",
    description="Credit card optimization engine for Mexico/LATAM",
    version="0.2.0"
)

app.include_router(promos.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---

class CreditCard(BaseModel):
    name: str
    bank: str
    cashback_general: float
    cashback_supermarket: float
    cashback_gas: float
    cashback_dining: float
    cashback_online: float
    active_promo: Optional[str] = None

class RecommendRequest(BaseModel):
    cards: List[CreditCard] = Field(..., min_length=1, max_length=50)
    purchase_description: str = Field(..., min_length=1, max_length=200)
    amount: float = Field(..., gt=0, le=1_000_000)

class RankedOption(BaseModel):
    card_name: str
    bank: str
    reason: str
    estimated_cashback: float
    benefit_type: str = "none"          # cashback | descuento | msi | info | none
    matched_promo: Optional[str] = None
    merchant: Optional[str] = None
    category: Optional[str] = None
    promo_alert: Optional[str] = None
    is_best: bool = False

class RecommendResponse(BaseModel):
    recommendations: List[RankedOption]

# --- Sample card data (Mexico market) ---

SAMPLE_CARDS = [
    CreditCard(
        name="Azul",
        bank="BBVA",
        cashback_general=0.5,
        cashback_supermarket=1.5,
        cashback_gas=1.0,
        cashback_dining=1.0,
        cashback_online=1.5,
        active_promo="3 MSI en Liverpool y Palacio de Hierro"
    ),
    CreditCard(
        name="Nu Card",
        bank="Nu Mexico",
        cashback_general=1.0,
        cashback_supermarket=1.0,
        cashback_gas=1.0,
        cashback_dining=1.0,
        cashback_online=1.0,
        active_promo=None
    ),
    CreditCard(
        name="Simplicity",
        bank="Citibanamex",
        cashback_general=0.0,
        cashback_supermarket=3.0,
        cashback_gas=0.0,
        cashback_dining=2.0,
        cashback_online=2.0,
        active_promo="5% de bonificacion en Walmart y Superama"
    ),
    CreditCard(
        name="Rappi Card",
        bank="Rappi x Banorte",
        cashback_general=1.5,
        cashback_supermarket=2.0,
        cashback_gas=1.0,
        cashback_dining=3.0,
        cashback_online=2.0,
        active_promo="10% en pedidos Rappi los viernes"
    ),
]

# --- Endpoints ---

@app.get("/")
def root():
    return {
        "app": "CardMax MX",
        "status": "running",
        "version": "0.2.0"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/cards/sample")
def get_sample_cards():
    return {"cards": SAMPLE_CARDS}

@app.post("/recommend", response_model=RecommendResponse)
def recommend_card(request: RecommendRequest):
    """Rank the user's cards by the EXACT monetary benefit for this purchase.

    The LLM only classifies the purchase (category + merchant). All money math
    is computed deterministically in app.recommendation against live promos.
    """
    try:
        cards = [c.model_dump() for c in request.cards]
        ranked = recommendation.recommend(
            cards, request.purchase_description, request.amount
        )
        return RecommendResponse(
            recommendations=[RankedOption(**r) for r in ranked]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {e}")