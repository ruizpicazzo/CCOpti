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
# "2x1", "3x2", "2X1", "2 x 1" — pay M for N units. Estimated saving = 1 - M/N.
_NXM_RE = re.compile(r"(\d)\s*[x×]\s*(\d)", re.IGNORECASE)


def promo_value(promo: dict) -> dict:
    """Amount-independent value of a promo.

    Returns {"kind", "pct", "fixed", "label"}:
      kind  ∈ cashback | descuento | 2x1 | msi | info | none
      pct   = percentage benefit (cashback%, discount%, 2x1→50, 3x2→33) or None
      fixed = fixed peso discount or None
      label = human-readable label
    This lets us compute exact pesos when an amount is given, or show the % as a
    suggestion when the user is just browsing (no amount).
    """
    title = str(promo.get("title") or "")
    desc = str(promo.get("description") or "")
    text = f"{title} {desc}"
    low = text.lower()

    # 1. Explicit cashback percentage field (most reliable)
    cb = promo.get("cashback_percent")
    if isinstance(cb, (int, float)) and cb > 0:
        pct = min(float(cb), 100.0)
        return {"kind": "cashback", "pct": pct, "fixed": None, "label": f"{pct:g}% cashback"}

    # 2. Percentage discount in text (requires a literal %)
    pm = _PERCENT_RE.search(text)
    if pm:
        pct = min(float(pm.group(1)), 100.0)
        if pct > 0:
            return {"kind": "descuento", "pct": pct, "fixed": None, "label": f"{pct:g}% de descuento"}

    # 3. Fixed peso discount — only when clearly a discount, not a price
    if any(w in low for w in _DISCOUNT_WORDS) and not _PRICE_RE.search(low):
        fm = _FIXED_RE.search(text)
        if fm:
            fixed = float(fm.group(1).replace(",", ""))
            return {"kind": "descuento", "pct": None, "fixed": fixed, "label": f"${fixed:g} de descuento"}

    # 4. NxM offers (2x1, 3x2): estimated saving = 1 - m/n
    nm = _NXM_RE.search(low)
    if nm and "mes" not in low:
        n, m = int(nm.group(1)), int(nm.group(2))
        if 1 <= m < n <= 5:
            pct = (1 - m / n) * 100
            return {"kind": "2x1", "pct": pct, "fixed": None,
                    "label": f"{n}x{m} (ahorro ≈{pct:.0f}% al comprar {n})"}

    # 5. Meses sin intereses — financing value, no direct cashback
    if _MSI_RE.search(low):
        return {"kind": "msi", "pct": None, "fixed": None, "label": "Meses sin intereses"}

    # 6. Applicable promo we couldn't quantify (e.g. a combo price)
    if title:
        return {"kind": "info", "pct": None, "fixed": None, "label": title.strip()}

    return {"kind": "none", "pct": None, "fixed": None, "label": None}


def value_to_pesos(v: dict, amount: float) -> float:
    """Exact peso benefit of a promo value for a given amount."""
    if v["pct"] is not None:
        return round(amount * v["pct"] / 100, 2)
    if v["fixed"] is not None:
        return round(min(v["fixed"], amount), 2)
    return 0.0


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


def _score(v: dict, amount: Optional[float]) -> float:
    """Ranking score: exact pesos when an amount is given, else the % benefit."""
    if amount is not None:
        return value_to_pesos(v, amount)
    return v["pct"] if v["pct"] is not None else -1.0


def recommend(cards: list, description: str, amount: Optional[float] = None) -> list:
    """Rank the user's cards for a purchase.

    With `amount`: ranks by exact peso benefit.
    Without `amount` (browse mode): ranks by % benefit and returns the
    percentages as suggestions — useful before deciding to buy.

    `cards` is a list of dicts (CreditCard.dict()). Returns dicts matching the
    RankedOption schema, best first.
    """
    cls = classify_purchase(description)
    category, merchant = cls["category"], cls["merchant"]

    all_promos = fetch_active_promos()
    results = []

    for card in cards:
        bank = card.get("bank")
        name = card.get("name")

        base_rate = _base_rate(card, category)
        base_v = ({"kind": "cashback", "pct": base_rate, "fixed": None,
                   "label": f"{base_rate:g}% cashback", "is_base": True}
                  if base_rate > 0 else None)

        # All matching promos for this card's bank
        promo_vals = []
        for p in all_promos:
            if p.get("bank") != bank or not _promo_matches(p, merchant):
                continue
            v = promo_value(p)
            v["is_base"] = False
            promo_vals.append(v)

        # Best matching promo (for display), ranked by score
        best_promo = max(promo_vals, key=lambda v: _score(v, amount), default=None)

        # Winner = best of {base cashback, best promo}
        candidates = [v for v in (base_v, best_promo) if v]
        winner = max(candidates, key=lambda v: _score(v, amount), default=None)

        if winner is None:
            benefit_type, benefit_label, benefit_pct = "none", None, None
            reason = f"Tu {name} no ofrece beneficio para esta compra."
            pesos = 0.0 if amount is not None else None
        else:
            benefit_type = winner["kind"]
            benefit_label = winner["label"]
            benefit_pct = winner["pct"]
            pesos = value_to_pesos(winner, amount) if amount is not None else None
            where = merchant or "este comercio"
            if winner.get("is_base"):
                reason = f"{winner['label']} de tu {name} para esta compra."
            else:
                reason = f"{winner['label']} en {where} con tu {name}."

        matched = best_promo["label"] if best_promo else None

        results.append({
            "card_name": name,
            "bank": bank,
            "reason": reason,
            "estimated_cashback": pesos,          # None in browse mode
            "benefit_pct": benefit_pct,           # % suggestion
            "benefit_label": benefit_label,       # e.g. "15% cashback"
            "benefit_type": benefit_type,
            "matched_promo": matched,
            "merchant": merchant,
            "category": category,
            "promo_alert": matched,
            "is_best": False,
        })

    results.sort(key=lambda r: (
        r["estimated_cashback"] if amount is not None else
        (r["benefit_pct"] if r["benefit_pct"] is not None else -1)
    ) or -1, reverse=True)
    if results:
        results[0]["is_best"] = True
    return results
