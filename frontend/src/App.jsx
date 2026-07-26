import { useState, useEffect } from "react"

const API = "http://localhost:8000"

const BANK_COLORS = {
  "BBVA": "#004A97",
  "Nu Mexico": "#820AD1",
  "Citibanamex": "#D22630",
  "Rappi x Banorte": "#FF441F",
  "Banorte": "#E4032E",
  "HSBC": "#DB0011",
  "Santander": "#EC0000",
  "American Express": "#016FD0",
  "Klar": "#6C1FFF",
  "Mercado Pago": "#009EE3",
  "Santander": "#EC0000",
}

const CATEGORY_ICONS = {
  dining: "🍽️", supermarket: "🛒", gas: "⛽", online: "🌐",
  travel: "✈️", general: "💳", technology: "💻", entertainment: "🎬",
  sports: "👟", beauty: "💄", default: "🏷️"
}

const SAMPLE_CARDS = [
  { name: "Azul", bank: "BBVA", cashback_general: 0.5, cashback_supermarket: 1.5, cashback_gas: 1.0, cashback_dining: 1.0, cashback_online: 1.5, active_promo: "3 MSI en Liverpool y Palacio de Hierro" },
  { name: "Nu Card", bank: "Nu Mexico", cashback_general: 1.0, cashback_supermarket: 1.0, cashback_gas: 1.0, cashback_dining: 1.0, cashback_online: 1.0, active_promo: null },
  { name: "Simplicity", bank: "Citibanamex", cashback_general: 0.0, cashback_supermarket: 3.0, cashback_gas: 0.0, cashback_dining: 2.0, cashback_online: 2.0, active_promo: "5% de bonificacion en Walmart y Superama" },
  { name: "Rappi Card", bank: "Rappi x Banorte", cashback_general: 1.5, cashback_supermarket: 2.0, cashback_gas: 1.0, cashback_dining: 3.0, cashback_online: 2.0, active_promo: "10% en pedidos Rappi los viernes" },
  { name: "Klar Card", bank: "Klar", cashback_general: 1.0, cashback_supermarket: 1.5, cashback_gas: 1.0, cashback_dining: 1.5, cashback_online: 2.0, active_promo: "15% cashback en Amazon y Mercado Libre" },
  { name: "Mercado Pago Card", bank: "Mercado Pago", cashback_general: 1.0, cashback_supermarket: 1.0, cashback_gas: 1.0, cashback_dining: 1.0, cashback_online: 3.0, active_promo: "3% cashback en compras en Mercado Libre" },
]

export default function App() {
  const [tab, setTab] = useState("recommend")
  const [cards] = useState(SAMPLE_CARDS)
  const [activeCards, setActiveCards] = useState(SAMPLE_CARDS.map((_, i) => i))
  const [purchase, setPurchase] = useState("")
  const [amount, setAmount] = useState("")
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [promos, setPromos] = useState([])
  const [promosLoading, setPromosLoading] = useState(false)
  const [expandedBanks, setExpandedBanks] = useState({})

  useEffect(() => {
    if (tab === "promos" && promos.length === 0) fetchPromos()
  }, [tab])

  const fetchPromos = async () => {
    setPromosLoading(true)
    try {
      const res = await fetch(`${API}/promos/`)
      const data = await res.json()
      setPromos(data.promos || [])
    } catch (e) {
      console.error("Error fetching promos", e)
    } finally {
      setPromosLoading(false)
    }
  }

  const toggleCard = (i) => {
    setActiveCards(prev => prev.includes(i) ? prev.filter(x => x !== i) : [...prev, i])
  }

  const toggleBank = (bank) => {
    setExpandedBanks(prev => ({ ...prev, [bank]: !prev[bank] }))
  }

  const handleRecommend = async () => {
    if (!purchase || !amount) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const selectedCards = cards.filter((_, i) => activeCards.includes(i))
      const res = await fetch(`${API}/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cards: selectedCards, purchase_description: purchase, amount: parseFloat(amount) })
      })
      if (!res.ok) throw new Error("Error del servidor")
      setResult(await res.json())
    } catch (e) {
      setError("No se pudo conectar con el servidor.")
    } finally {
      setLoading(false)
    }
  }

  // Group promos by bank
  const promosByBank = promos.reduce((acc, p) => {
    if (!acc[p.bank]) acc[p.bank] = []
    acc[p.bank].push(p)
    return acc
  }, {})

  return (
    <div style={{ minHeight: "100vh", background: "#f5f5f5", fontFamily: "system-ui, sans-serif" }}>

      {/* Header */}
      <div style={{ background: "#1a1a2e", padding: "16px 32px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 26 }}>💳</span>
          <div>
            <div style={{ color: "#fff", fontSize: 20, fontWeight: 700 }}>CardMax MX</div>
            <div style={{ color: "#aaa", fontSize: 12 }}>Optimizador de tarjetas de crédito</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {[["recommend", "🔍 Recomendar"], ["promos", "🔥 Promociones"], ["cards", "💳 Mis Tarjetas"]].map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)} style={{
              padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13, fontWeight: 500,
              background: tab === key ? "#fff" : "transparent", color: tab === key ? "#1a1a2e" : "#aaa"
            }}>{label}</button>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 800, margin: "0 auto", padding: "28px 16px" }}>

        {/* TAB: RECOMMEND */}
        {tab === "recommend" && (
          <>
            <div style={{ background: "#fff", borderRadius: 16, padding: 28, marginBottom: 20, boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}>
              <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>¿Qué vas a comprar?</div>
              <div style={{ fontSize: 14, color: "#888", marginBottom: 20 }}>Describe tu compra y te decimos qué tarjeta usar</div>
              <input value={purchase} onChange={e => setPurchase(e.target.value)}
                placeholder="ej. cena en restaurante, gasolina, compras en Walmart..."
                style={{ width: "100%", padding: "12px 16px", borderRadius: 10, border: "1.5px solid #e0e0e0", fontSize: 15, marginBottom: 12, outline: "none", boxSizing: "border-box" }}
                onKeyDown={e => e.key === "Enter" && handleRecommend()} />
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ position: "relative", flex: 1 }}>
                  <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#888" }}>$</span>
                  <input value={amount} onChange={e => setAmount(e.target.value)} placeholder="Monto en MXN" type="number"
                    style={{ width: "100%", padding: "12px 16px 12px 28px", borderRadius: 10, border: "1.5px solid #e0e0e0", fontSize: 15, outline: "none", boxSizing: "border-box" }} />
                </div>
                <button onClick={handleRecommend} disabled={loading || !purchase || !amount}
                  style={{ padding: "12px 24px", background: loading ? "#ccc" : "#1a1a2e", color: "#fff", border: "none", borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", whiteSpace: "nowrap" }}>
                  {loading ? "Analizando..." : "¿Qué tarjeta uso?"}
                </button>
              </div>
            </div>

            {result && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 13, color: "#888", marginBottom: 6, textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
                  Resultados — {result.recommendations.length} tarjetas comparadas
                </div>
                {result.recommendations[0]?.merchant || result.recommendations[0]?.category ? (
                  <div style={{ fontSize: 12, color: "#888", marginBottom: 14 }}>
                    Compra detectada:{" "}
                    <strong>{result.recommendations[0].merchant || "—"}</strong>
                    {result.recommendations[0].category ? ` · ${result.recommendations[0].category}` : ""}
                  </div>
                ) : null}
                {result.recommendations.map((r, i) => {
                  const color = BANK_COLORS[r.bank] || "#1a1a2e"
                  const benefit = Number(r.estimated_cashback || 0)
                  const BENEFIT_BADGE = {
                    cashback: { label: "Cashback", bg: "#dcfce7", fg: "#16a34a" },
                    descuento: { label: "Descuento", bg: "#dbeafe", fg: "#1d4ed8" },
                    "2x1": { label: "2x1", bg: "#ffe4e6", fg: "#be123c" },
                    msi: { label: "Meses sin intereses", bg: "#fef9c3", fg: "#854d0e" },
                    info: { label: "Promo aplicable", bg: "#f3e8ff", fg: "#7e22ce" },
                  }
                  const badge = BENEFIT_BADGE[r.benefit_type]
                  return (
                    <div key={i} style={{
                      background: r.is_best ? "#fff" : "#fafafa",
                      borderRadius: 16,
                      padding: 24,
                      marginBottom: 10,
                      boxShadow: r.is_best ? "0 4px 20px rgba(0,0,0,0.10)" : "0 2px 8px rgba(0,0,0,0.04)",
                      borderLeft: `5px solid ${r.is_best ? color : "#e0e0e0"}`,
                      opacity: r.is_best ? 1 : 0.75,
                      position: "relative"
                    }}>
                      {r.is_best && (
                        <div style={{
                          position: "absolute", top: -10, right: 16,
                          background: "#1a1a2e", color: "#fff",
                          fontSize: 11, fontWeight: 700, padding: "3px 12px",
                          borderRadius: 99, letterSpacing: 0.5
                        }}>
                          ★ MEJOR OPCIÓN
                        </div>
                      )}
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                        <span style={{ fontSize: r.is_best ? 28 : 20 }}>{r.is_best ? "🏆" : `#${i + 1}`}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: r.is_best ? 18 : 15, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                            {r.card_name}
                            {badge && benefit > 0 && (
                              <span style={{ background: badge.bg, color: badge.fg, fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99 }}>
                                {badge.label}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: 13, color: "#888" }}>{r.bank}</div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: r.is_best ? 24 : 18, fontWeight: 700, color: benefit > 0 ? (r.is_best ? "#16a34a" : "#555") : "#bbb" }}>
                            ${benefit.toFixed(2)}
                          </div>
                          <div style={{ fontSize: 11, color: "#aaa" }}>beneficio est.</div>
                        </div>
                      </div>
                      <div style={{ fontSize: 13, color: "#555", lineHeight: 1.5, marginBottom: r.matched_promo ? 8 : 0 }}>
                        {r.reason}
                      </div>
                      {r.matched_promo && (
                        <div style={{ background: "#fef9c3", borderRadius: 8, padding: "8px 12px", fontSize: 12, color: "#854d0e", marginTop: 8 }}>
                          🔥 <strong>Promo:</strong> {r.matched_promo}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {error && <div style={{ background: "#fee2e2", borderRadius: 12, padding: "14px 18px", color: "#b91c1c", marginBottom: 20, fontSize: 14 }}>{error}</div>}
          </>
        )}

        {/* TAB: PROMOS */}
        {tab === "promos" && (
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>Promociones vigentes</div>
            <div style={{ fontSize: 14, color: "#888", marginBottom: 20 }}>Actualizadas diariamente de los sitios oficiales de cada banco</div>

            {promosLoading && (
              <div style={{ textAlign: "center", padding: 40, color: "#888" }}>Cargando promociones...</div>
            )}

            {!promosLoading && promos.length === 0 && (
              <div style={{ background: "#fff", borderRadius: 16, padding: 32, textAlign: "center", color: "#888", boxShadow: "0 2px 12px rgba(0,0,0,0.06)" }}>
                <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Sin promociones disponibles</div>
                <div style={{ fontSize: 13 }}>El scraper corre diariamente. Vuelve mañana o actívalo manualmente desde GitHub Actions.</div>
              </div>
            )}

            {Object.entries(promosByBank).map(([bank, bankPromos]) => {
              const color = BANK_COLORS[bank] || "#555"
              const isExpanded = expandedBanks[bank]
              return (
                <div key={bank} style={{ background: "#fff", borderRadius: 16, marginBottom: 12, boxShadow: "0 2px 12px rgba(0,0,0,0.06)", overflow: "hidden" }}>
                  <div onClick={() => toggleBank(bank)}
                    style={{ padding: "18px 24px", display: "flex", alignItems: "center", gap: 12, cursor: "pointer", borderLeft: `5px solid ${color}` }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: 16 }}>{bank}</div>
                      <div style={{ fontSize: 13, color: "#888" }}>{bankPromos.length} promociones activas</div>
                    </div>
                    <span style={{ fontSize: 20, color: "#aaa" }}>{isExpanded ? "▲" : "▼"}</span>
                  </div>

                  {isExpanded && (
                    <div style={{ borderTop: "1px solid #f0f0f0" }}>
                      {bankPromos.map((promo, i) => (
                        <div key={i} style={{ padding: "16px 24px", borderBottom: i < bankPromos.length - 1 ? "1px solid #f5f5f5" : "none", display: "flex", gap: 16, alignItems: "flex-start" }}>
                          <div style={{ fontSize: 24, marginTop: 2 }}>{CATEGORY_ICONS[promo.category] || CATEGORY_ICONS.default}</div>
                          <div style={{ flex: 1 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                              <span style={{ fontWeight: 600, fontSize: 15 }}>{promo.title}</span>
                              {promo.cashback_percent && (
                                <span style={{ background: "#dcfce7", color: "#16a34a", fontSize: 12, fontWeight: 700, padding: "2px 8px", borderRadius: 99 }}>
                                  {promo.cashback_percent}% cashback
                                </span>
                              )}
                            </div>
                            {promo.description && <div style={{ fontSize: 13, color: "#666", lineHeight: 1.5 }}>{promo.description}</div>}
                            <div style={{ display: "flex", gap: 12, marginTop: 6, flexWrap: "wrap" }}>
                              {promo.merchant && <span style={{ fontSize: 12, color: "#888" }}>🏪 {promo.merchant}</span>}
                              {promo.valid_until && <span style={{ fontSize: 12, color: "#888" }}>📅 Válido hasta: {promo.valid_until}</span>}
                              {promo.category && <span style={{ fontSize: 12, color: "#888", textTransform: "capitalize" }}>📂 {promo.category}</span>}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* TAB: MY CARDS */}
        {tab === "cards" && (
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>Mis tarjetas</div>
            <div style={{ fontSize: 14, color: "#888", marginBottom: 20 }}>Selecciona las tarjetas que quieres comparar al hacer una recomendación</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
              {cards.map((card, i) => {
                const active = activeCards.includes(i)
                const color = BANK_COLORS[card.bank] || "#555"
                return (
                  <div key={i} onClick={() => toggleCard(i)}
                    style={{ border: `2px solid ${active ? color : "#e0e0e0"}`, borderRadius: 14, padding: 18, cursor: "pointer", background: active ? "#fafafa" : "#fff", opacity: active ? 1 : 0.5 }}>
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
                      {[["🛒 Supermercado", card.cashback_supermarket], ["🍽️ Restaurantes", card.cashback_dining], ["⛽ Gasolina", card.cashback_gas], ["🌐 Online", card.cashback_online]].map(([label, val]) => (
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
        )}
      </div>
    </div>
  )
}