import { useState } from "react"

const SAMPLE_CARDS = [
  { name: "Azul", bank: "BBVA", cashback_general: 0.5, cashback_supermarket: 1.5, cashback_gas: 1.0, cashback_dining: 1.0, cashback_online: 1.5, active_promo: "3 MSI en Liverpool y Palacio de Hierro" },
  { name: "Nu Card", bank: "Nu Mexico", cashback_general: 1.0, cashback_supermarket: 1.0, cashback_gas: 1.0, cashback_dining: 1.0, cashback_online: 1.0, active_promo: null },
  { name: "Simplicity", bank: "Citibanamex", cashback_general: 0.0, cashback_supermarket: 3.0, cashback_gas: 0.0, cashback_dining: 2.0, cashback_online: 2.0, active_promo: "5% de bonificacion en Walmart y Superama" },
  { name: "Rappi Card", bank: "Rappi x Banorte", cashback_general: 1.5, cashback_supermarket: 2.0, cashback_gas: 1.0, cashback_dining: 3.0, cashback_online: 2.0, active_promo: "10% en pedidos Rappi los viernes" },
]

const BANK_COLORS = {
  "BBVA": "#004A97",
  "Nu Mexico": "#820AD1",
  "Citibanamex": "#D22630",
  "Rappi x Banorte": "#FF441F",
}

export default function App() {
  const [cards, setCards] = useState(SAMPLE_CARDS)
  const [purchase, setPurchase] = useState("")
  const [amount, setAmount] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeCards, setActiveCards] = useState(SAMPLE_CARDS.map((_, i) => i))

  const toggleCard = (i) => {
    setActiveCards(prev =>
      prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i]
    )
  }

  const handleRecommend = async () => {
    if (!purchase || !amount) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const selectedCards = cards.filter((_, i) => activeCards.includes(i))
      const res = await fetch("https://cardmax-backend.onrender.com/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cards: selectedCards,
          purchase_description: purchase,
          amount: parseFloat(amount)
        })
      })
      if (!res.ok) throw new Error("Error del servidor")
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError("No se pudo conectar con el servidor. Asegurate de que el backend este corriendo.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f5f5f5", fontFamily: "system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ background: "#1a1a2e", padding: "20px 32px", display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 28 }}>💳</span>
        <div>
          <div style={{ color: "#fff", fontSize: 22, fontWeight: 700, letterSpacing: -0.5 }}>CardMax MX</div>
          <div style={{ color: "#aaa", fontSize: 13 }}>Optimizador de tarjetas de credito</div>
        </div>
      </div>

      <div style={{ maxWidth: 780, margin: "0 auto", padding: "32px 16px" }}>

        {/* Ask Section */}
        <div style={{ background: "#fff", borderRadius: 16, padding: 28, marginBottom: 24, boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>¿Que vas a comprar?</div>
          <div style={{ fontSize: 14, color: "#888", marginBottom: 20 }}>Describe tu compra y te decimos que tarjeta usar</div>

          <input
            value={purchase}
            onChange={e => setPurchase(e.target.value)}
            placeholder="ej. cena en restaurante, gasolina, compras en Walmart..."
            style={{ width: "100%", padding: "12px 16px", borderRadius: 10, border: "1.5px solid #e0e0e0", fontSize: 15, marginBottom: 12, outline: "none", boxSizing: "border-box" }}
            onKeyDown={e => e.key === "Enter" && handleRecommend()}
          />

          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ position: "relative", flex: 1 }}>
              <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#888", fontSize: 15 }}>$</span>
              <input
                value={amount}
                onChange={e => setAmount(e.target.value)}
                placeholder="Monto en MXN"
                type="number"
                style={{ width: "100%", padding: "12px 16px 12px 28px", borderRadius: 10, border: "1.5px solid #e0e0e0", fontSize: 15, outline: "none", boxSizing: "border-box" }}
              />
            </div>
            <button
              onClick={handleRecommend}
              disabled={loading || !purchase || !amount}
              style={{ padding: "12px 28px", background: loading ? "#ccc" : "#1a1a2e", color: "#fff", border: "none", borderRadius: 10, fontSize: 15, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", whiteSpace: "nowrap" }}
            >
              {loading ? "Analizando..." : "¿Que tarjeta uso?"}
            </button>
          </div>
        </div>

        {/* Result */}
        {result && (
          <div style={{ background: "#fff", borderRadius: 16, padding: 28, marginBottom: 24, boxShadow: "0 2px 12px rgba(0,0,0,0.06)", borderLeft: `5px solid ${BANK_COLORS[result.bank] || "#1a1a2e"}` }}>
            <div style={{ fontSize: 13, color: "#888", marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>Recomendacion de CardMax</div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
              <span style={{ fontSize: 32 }}>🏆</span>
              <div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>{result.best_card}</div>
                <div style={{ fontSize: 14, color: "#888" }}>{result.bank}</div>
              </div>
              <div style={{ marginLeft: "auto", textAlign: "right" }}>
                <div style={{ fontSize: 28, fontWeight: 700, color: "#16a34a" }}>${result.estimated_cashback}</div>
                <div style={{ fontSize: 13, color: "#888" }}>cashback estimado</div>
              </div>
            </div>
            <div style={{ background: "#f9f9f9", borderRadius: 10, padding: "12px 16px", fontSize: 14, color: "#444", marginBottom: result.promo_alert ? 12 : 0 }}>
              {result.reason}
            </div>
            {result.promo_alert && (
              <div style={{ background: "#fef9c3", borderRadius: 10, padding: "10px 16px", fontSize: 13, color: "#854d0e", marginTop: 10 }}>
                🔥 <strong>Promo activa:</strong> {result.promo_alert}
              </div>
            )}
          </div>
        )}

        {error && (
          <div style={{ background: "#fee2e2", borderRadius: 12, padding: "14px 18px", color: "#b91c1c", marginBottom: 24, fontSize: 14 }}>
            {error}
          </div>
        )}

        {/* My Cards */}
        <div style={{ background: "#fff", borderRadius: 16, padding: 28, boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}>
          <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>Mis tarjetas</div>
          <div style={{ fontSize: 14, color: "#888", marginBottom: 20 }}>Selecciona las tarjetas que quieres comparar</div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
            {cards.map((card, i) => {
              const active = activeCards.includes(i)
              const color = BANK_COLORS[card.bank] || "#555"
              return (
                <div
                  key={i}
                  onClick={() => toggleCard(i)}
                  style={{ border: `2px solid ${active ? color : "#e0e0e0"}`, borderRadius: 14, padding: 18, cursor: "pointer", transition: "all 0.15s", background: active ? "#fafafa" : "#fff", opacity: active ? 1 : 0.5 }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 16 }}>{card.name}</div>
                      <div style={{ fontSize: 13, color: "#888" }}>{card.bank}</div>
                    </div>
                    <div style={{ width: 22, height: 22, borderRadius: "50%", background: active ? color : "#e0e0e0", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {active && <span style={{ color: "#fff", fontSize: 13 }}>✓</span>}
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 12 }}>
                    {[
                      ["🛒 Supermercado", card.cashback_supermarket],
                      ["🍽️ Restaurantes", card.cashback_dining],
                      ["⛽ Gasolina", card.cashback_gas],
                      ["🌐 Online", card.cashback_online],
                    ].map(([label, val]) => (
                      <div key={label} style={{ background: "#f5f5f5", borderRadius: 8, padding: "6px 10px", display: "flex", justifyContent: "space-between" }}>
                        <span style={{ color: "#666" }}>{label}</span>
                        <span style={{ fontWeight: 600, color: val > 1.5 ? "#16a34a" : "#333" }}>{val}%</span>
                      </div>
                    ))}
                  </div>

                  {card.active_promo && (
                    <div style={{ marginTop: 10, background: "#fef9c3", borderRadius: 8, padding: "6px 10px", fontSize: 12, color: "#854d0e" }}>
                      🔥 {card.active_promo}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}