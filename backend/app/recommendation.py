"""Deterministic credit-card recommendation engine.

The product promise is to find the *mathematically* best card for a purchase.
So the money math lives here in Python (exact, auditable). The LLM is used only
to classify the purchase (category + merchant) — never to do arithmetic.
"""
import os
import re
import json
import unicodedata
from typing import Optional

import anthropic

from app.routers.promos import supabase_get

# Cheap model: classification only, no arithmetic.
CLASSIFY_MODEL = "claude-haiku-4-5"

ALLOWED_CATEGORIES = {
    "dining", "supermarket", "gas", "online", "travel",
    "general", "technology", "entertainment", "sports",
}

# Map any detected category to one of the 5 rates a CreditCard actually defines.
_CATEGORY_TO_RATE = {
    "dining": "cashback_dining",
    "supermarket": "cashback_supermarket",
    "gas": "cashback_gas",
    "online": "cashback_online",
    # everything else falls back to the general rate
}


def _normalize(text: str) -> str:
    """Lowercase, strip accents and non-alphanumerics for fuzzy matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", text.lower())


# --------------------------------------------------------------------------- #
# 1. Purchase classification (the only LLM call)
# --------------------------------------------------------------------------- #
def classify_purchase(description: str) -> dict:
    """Return {"category": <enum>, "merchant": <str|None>} for a purchase.

    Output is strictly validated so user free-text can't steer anything except
    these two constrained fields (prompt-injection mitigation).
    """
    safe = (description or "")[:200]
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or not safe.strip():
        return {"category": "general", "merchant": None}

    prompt = f"""Clasifica esta compra de un consumidor mexicano.

Compra: "{safe}"

Devuelve SOLO un objeto JSON, sin texto extra ni backticks:
{{"category": "<una de: dining, supermarket, gas, online, travel, general, technology, entertainment, sports>", "merchant": "<nombre del comercio si se menciona, o null>"}}

Reglas:
- category: elige la más apropiada; si no es claro, usa "general".
- merchant: solo el nombre de la marca/comercio (ej. "KFC", "Amazon"); null si no se menciona."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=CLASSIFY_MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"```[a-zA-Z]*\s*", "", raw).replace("```", "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group()) if m else {}
    except Exception as e:
        print(f"classify_purchase error: {e}")
        data = {}

    category = str(data.get("category", "general")).lower().strip()
    if category not in ALLOWED_CATEGORIES:
        category = "general"
    merchant = data.get("merchant")
    if merchant in ("null", "", None):
        merchant = None
    elif isinstance(merchant, str):
        merchant = merchant.strip()[:60]
    else:
        merchant = None
    return {"category": category, "merchant": merchant}


# --------------------------------------------------------------------------- #
# 2. Deterministic promo benefit parsing
# --------------------------------------------------------------------------- #
_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")
_FIXED_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_DISCOUNT_WORDS = ("descuento", "off", "de regalo", "bonific")
# A price (not a discount): "combo", "paquete", or "<por|desde|a> $...".
# Uses word boundaries so "hasta $120" does NOT count as a price.
_PRICE_RE = re.compile(r"\b(combo|paquete)\b|\b(por|desde|a)\s+\$", re.IGNORECASE)
_MSI_RE = re.compile(r"meses?\s+sin\s+inter", re.IGNORECASE)


def parse_promo_benefit(promo: dict, amount: float) -> tuple:
    """Return (benefit_pesos, label, kind) for a promo applied to `amount`.

    kind ∈ {"cashback", "descuento", "msi", "info", "none"}.
    Math is exact; ambiguous prices ("combo $269") yield 0 pesos (informational).
    """
    title = str(promo.get("title") or "")
    desc = str(promo.get("description") or "")
    text = f"{title} {desc}"
    low = text.lower()

    # 1. Explicit cashback percentage field (most reliable)
    cb = promo.get("cashback_percent")
    if isinstance(cb, (int, float)) and cb > 0:
        pct = min(float(cb), 100.0)
        return round(amount * pct / 100, 2), f"{pct:g}% cashback", "cashback"

    # 2. Percentage discount in text (requires a literal %)
    pm = _PERCENT_RE.search(text)
    if pm:
        pct = min(float(pm.group(1)), 100.0)
        if pct > 0:
            return round(amount * pct / 100, 2), f"{pct:g}% de descuento", "descuento"

    # 3. Fixed peso discount — only when clearly a discount, not a price
    if any(w in low for w in _DISCOUNT_WORDS) and not _PRICE_RE.search(low):
        fm = _FIXED_RE.search(text)
        if fm:
            fixed = float(fm.group(1).replace(",", ""))
            benefit = min(fixed, amount)
            return round(benefit, 2), f"${fixed:g} de descuento", "descuento"

    # 4. Meses sin intereses — real financing value but no direct cashback
    if _MSI_RE.search(low):
        return 0.0, "Meses sin intereses", "msi"

    # 5. Applicable promo we couldn't quantify (e.g. a combo price)
    if title:
        return 0.0, title.strip(), "info"

    return 0.0, None, "none"


# --------------------------------------------------------------------------- #
# 3. Matching + scoring
# --------------------------------------------------------------------------- #
def _base_rate(card: dict, category: str) -> float:
    field = _CATEGORY_TO_RATE.get(category, "cashback_general")
    try:
        return float(card.get(field) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _promo_matches(promo: dict, merchant: Optional[str]) -> bool:
    """Scraped promos are merchant-specific, so they only apply when the
    purchase merchant matches the promo's merchant/title. Category is NOT used
    for matching (the card's per-category cashback rate already covers that);
    matching unrelated 'general' promos to any purchase would over-credit wildly.
    """
    if not merchant:
        return False
    nm = _normalize(merchant)
    if not nm or len(nm) < 3:
        return False
    pm = _normalize(promo.get("merchant") or "")
    if pm and (nm in pm or pm in nm):
        return True
    return nm in _normalize(promo.get("title") or "")


def fetch_active_promos() -> list:
    """All active promos (the table is small; filter by bank in Python)."""
    data = supabase_get("promotions", {"is_active": "eq.true", "select":
                        "bank,merchant,title,description,cashback_percent,category"})
    return data if isinstance(data, list) else []


def recommend(cards: list, description: str, amount: float) -> list:
    """Rank the user's cards by the exact monetary benefit for this purchase.

    `cards` is a list of dicts (CreditCard.dict()). Returns a list of dicts
    matching the RankedOption schema, best first.
    """
    cls = classify_purchase(description)
    category, merchant = cls["category"], cls["merchant"]

    all_promos = fetch_active_promos()
    results = []

    for card in cards:
        bank = card.get("bank")
        name = card.get("name")

        base_rate = _base_rate(card, category)
        base_benefit = round(amount * base_rate / 100, 2)

        # Best matching promo for this card's bank
        best_promo_pesos = 0.0
        best_promo_label = None
        best_promo_kind = None
        matched_promo_title = None

        for p in all_promos:
            if p.get("bank") != bank:
                continue
            if not _promo_matches(p, merchant):
                continue
            pesos, label, kind = parse_promo_benefit(p, amount)
            # Track the most valuable matching promo; remember an applicable one
            # even if 0 pesos (msi/info) so the user still sees it.
            if pesos > best_promo_pesos or (matched_promo_title is None and kind in ("msi", "info")):
                if pesos >= best_promo_pesos:
                    best_promo_pesos = pesos
                    best_promo_label = label
                    best_promo_kind = kind
                matched_promo_title = label

        # Pick the better of base cashback vs promo
        if best_promo_pesos > base_benefit:
            benefit = best_promo_pesos
            benefit_type = best_promo_kind or "descuento"
            reason = f"{best_promo_label} en {merchant or 'este comercio'} con tu {name}."
        elif base_benefit > 0:
            benefit = base_benefit
            benefit_type = "cashback"
            reason = f"{base_rate:g}% de cashback de tu {name} para esta compra."
        else:
            benefit = 0.0
            benefit_type = best_promo_kind or "none"
            if best_promo_kind == "msi":
                reason = f"Sin cashback directo, pero ofrece {best_promo_label}."
            elif matched_promo_title:
                reason = f"Promo aplicable: {matched_promo_title}."
            else:
                reason = f"Tu {name} no ofrece beneficio para esta compra."

        results.append({
            "card_name": name,
            "bank": bank,
            "reason": reason,
            "estimated_cashback": round(benefit, 2),
            "benefit_type": benefit_type,
            "matched_promo": matched_promo_title,
            "merchant": merchant,
            "category": category,
            "promo_alert": best_promo_label if best_promo_pesos > 0 else None,
            "is_best": False,
        })

    # Rank by exact pesos, then flag the winner
    results.sort(key=lambda r: r["estimated_cashback"], reverse=True)
    if results:
        results[0]["is_best"] = True
    return results
