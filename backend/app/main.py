from fastapi import FastAPI, HTTPException
from app.routers import promos
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import os
import json
import re

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

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
    cards: List[CreditCard]
    purchase_description: str
    amount: float

class RecommendResponse(BaseModel):
    best_card: str
    bank: str
    reason: str
    estimated_cashback: float
    promo_alert: Optional[str] = None

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
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key not configured")

    client = anthropic.Anthropic(api_key=api_key)

    cards_summary = ""
    for card in request.cards:
        cards_summary += f"""
- {card.name} ({card.bank}):
  General: {card.cashback_general}% | Supermarket: {card.cashback_supermarket}% |
  Gas: {card.cashback_gas}% | Dining: {card.cashback_dining}% | Online: {card.cashback_online}%
  Active promo: {card.active_promo or 'None'}
"""

    prompt = f"""You are CardMax, a credit card optimization assistant for Mexican consumers.

The user wants to make this purchase: "{request.purchase_description}" for ${request.amount} MXN.

Their available credit cards are:
{cards_summary}

Analyze which card gives the best benefit for this specific purchase. Consider:
1. The cashback percentage for the relevant category
2. Any active promotions that apply
3. The estimated cashback in MXN pesos

Respond in this exact JSON format with no extra text, no markdown, no backticks:
{{
  "best_card": "card name",
  "bank": "bank name",
  "reason": "brief explanation in Spanish (1-2 sentences)",
  "estimated_cashback": numeric_value,
  "promo_alert": "promo text if applicable, otherwise null"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not json_match:
        raise HTTPException(status_code=500, detail="Could not parse AI response")
    result = json.loads(json_match.group())

    return RecommendResponse(**result)