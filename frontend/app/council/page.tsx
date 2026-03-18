"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

// ── Types ──────────────────────────────────────────────────────────────────────

interface BudgetStatus {
  provider: string;
  balance_eur: number;
  total_spent_eur: number;
  total_calls: number;
  status: string;
}

interface MarketRegime {
  regime: string;
  vix_level: number | null;
  sp500_trend: string | null;
  macro_events: string[];
  date: string | null;
}

interface CircuitBreakerStatus {
  level: string;
  trigger_type: string | null;
  description: string;
  position_multiplier: number;
}

interface StatusData {
  circuit_breaker: CircuitBreakerStatus;
  market_regime: MarketRegime;
  budgets: BudgetStatus[];
}

interface AgentResponse {
  agent_slot: string;
  agent_name: string;
  model_used: string;
  decision: string;
  confidence: number;
  ticker: string;
  based_on: string[];
  ignored_signals: string[];
  factor_weights: Record<string, number>;
  alternatives_considered: string[];
  why_this_asset: string;
  information_sufficiency: number;
  vote_valid: boolean;
  duration_s: number;
}

interface CouncilResult {
  trade_id: string;
  ticker: string;
  decision: string;
  vote_score: string;
  average_confidence: number;
  unanimity: boolean;
  dissenting_agents: string[];
  master_called: boolean;
  master_decision: string | null;
  agent_responses: AgentResponse[];
  deliberation_ms: number;
  agent_weights_used: Record<string, number>;
  information_sufficiency_scores: Record<string, number>;
  trade_held_for_data: boolean;
  hold_duration_minutes: number;
  error: string | null;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const CB_COLORS: Record<string, string> = {
  GREEN:  "var(--green)",
  YELLOW: "var(--yellow)",
  ORANGE: "#ff8800",
  RED:    "var(--red)",
};

const DECISION_COLORS: Record<string, string> = {
  BUY:     "var(--green)",
  SELL:    "var(--red)",
  HOLD:    "var(--yellow)",
  WAITING: "var(--blue)",
  BLOCKED: "var(--red)",
};

const AGENT_ICONS: Record<string, string> = {
  slot_1_fundamentalist: "📊",
  slot_2_quant:          "🔢",
  slot_3_news:           "📰",
  slot_4_contrarian:     "🔄",
  slot_5_finance:        "💰",
};

function confColor(conf: number): string {
  if (conf >= 75) return "var(--green)";
  if (conf >= 55) return "var(--yellow)";
  return "var(--red)";
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusBar({ data }: { data: StatusData }) {
  const cb = data.circuit_breaker;
  const regime = data.market_regime;
  const cbColor = CB_COLORS[cb.level] ?? "#888";

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
      {/* Circuit Breaker */}
      <div className="card" style={{ flex: "1 1 220px" }}>
        <div className="card-label">Circuit Breaker</div>
        <div style={{ fontSize: 22, fontWeight: 700, color: cbColor }}>
          {cb.level}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
          {cb.description}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>
          Position × {cb.position_multiplier}
        </div>
      </div>

      {/* Market Regime */}
      <div className="card" style={{ flex: "1 1 220px" }}>
        <div className="card-label">Régime Marché</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--green)" }}>
          {regime.regime}
        </div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
          VIX: {regime.vix_level?.toFixed(1) ?? "—"}
          &nbsp;|&nbsp;S&amp;P500: {regime.sp500_trend ?? "—"}
        </div>
        {regime.macro_events.length > 0 && (
          <div style={{ fontSize: 11, color: "var(--yellow)", marginTop: 2 }}>
            ⚠ {regime.macro_events.join(", ")}
          </div>
        )}
      </div>

      {/* Budgets */}
      {data.budgets.map((b) => (
        <div key={b.provider} className="card" style={{ flex: "1 1 160px" }}>
          <div className="card-label">{b.provider.toUpperCase()}</div>
          <div style={{
            fontSize: 18, fontWeight: 700,
            color: b.status === "OK" ? "var(--green)" : b.status === "LOW" ? "var(--yellow)" : "var(--red)",
          }}>
            €{b.balance_eur?.toFixed(2) ?? "—"}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
            Dépensé: €{b.total_spent_eur?.toFixed(3) ?? "—"}
            &nbsp;|&nbsp;{b.total_calls ?? 0} appels
          </div>
        </div>
      ))}
    </div>
  );
}

function AgentCard({ agent, weight, dissenting }: {
  agent: AgentResponse;
  weight: number;
  dissenting: boolean;
}) {
  const [open, setOpen] = useState(false);
  const decColor = DECISION_COLORS[agent.decision] ?? "#888";
  const icon = AGENT_ICONS[agent.agent_slot] ?? "🤖";

  return (
    <div
      className="card"
      style={{
        cursor: "pointer",
        border: dissenting ? "1px solid var(--yellow)" : undefined,
        opacity: agent.vote_valid ? 1 : 0.5,
      }}
      onClick={() => setOpen((o) => !o)}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <span style={{ fontSize: 18 }}>{icon}</span>
          <span style={{ marginLeft: 8, fontWeight: 700 }}>{agent.agent_name}</span>
          {dissenting && (
            <span style={{ marginLeft: 8, fontSize: 10, color: "var(--yellow)" }}>DISSIDENT</span>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: decColor }}>
            {agent.decision}
          </div>
          <div style={{ fontSize: 12, color: confColor(agent.confidence) }}>
            {agent.confidence.toFixed(0)}%
          </div>
        </div>
      </div>

      <div style={{ marginTop: 8, display: "flex", gap: 16, fontSize: 11, color: "var(--text-dim)" }}>
        <span>Poids: ×{weight.toFixed(2)}</span>
        <span>Sufficiency: {agent.information_sufficiency.toFixed(0)}%</span>
        <span>{agent.duration_s.toFixed(1)}s</span>
      </div>

      <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-dim)" }}>
        {agent.model_used}
      </div>

      {/* Detail expand */}
      {open && (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
          {agent.why_this_asset && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 2 }}>THÈSE</div>
              <div style={{ fontSize: 12 }}>{agent.why_this_asset}</div>
            </div>
          )}

          {agent.based_on.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4 }}>BASÉ SUR</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {agent.based_on.map((s, i) => (
                  <span key={i} style={{
                    background: "var(--green-dark)", border: "1px solid var(--border-bright)",
                    padding: "2px 6px", borderRadius: 3, fontSize: 10,
                  }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {agent.ignored_signals.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4 }}>IGNORÉ</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {agent.ignored_signals.map((s, i) => (
                  <span key={i} style={{
                    background: "#1a0a0a", border: "1px solid #3a1a1a",
                    padding: "2px 6px", borderRadius: 3, fontSize: 10, color: "var(--text-dim)",
                  }}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {Object.keys(agent.factor_weights).length > 0 && (
            <div>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4 }}>PONDÉRATION FACTEURS</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {Object.entries(agent.factor_weights).map(([k, v]) => (
                  <div key={k} style={{ fontSize: 10 }}>
                    <span style={{ color: "var(--text-dim)" }}>{k}: </span>
                    <span style={{ color: "var(--green)" }}>{(v * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function VoteSummary({ result }: { result: CouncilResult }) {
  const decColor = DECISION_COLORS[result.decision] ?? "#888";

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        {/* Decision */}
        <div>
          <div className="card-label">DÉCISION FINALE</div>
          <div style={{ fontSize: 36, fontWeight: 900, color: decColor, letterSpacing: 2 }}>
            {result.decision}
          </div>
          <div style={{ fontSize: 14, color: "var(--text-dim)", marginTop: 4 }}>
            {result.ticker} &nbsp;·&nbsp; Vote {result.vote_score}
          </div>
        </div>

        {/* Metrics */}
        <div style={{ display: "flex", gap: 24 }}>
          <div style={{ textAlign: "center" }}>
            <div className="card-label">CONFIANCE MOY.</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: confColor(result.average_confidence) }}>
              {result.average_confidence.toFixed(0)}%
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div className="card-label">DÉLIBÉRATION</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text)" }}>
              {(result.deliberation_ms / 1000).toFixed(1)}s
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div className="card-label">UNANIMITÉ</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: result.unanimity ? "var(--green)" : "var(--yellow)" }}>
              {result.unanimity ? "OUI" : "NON"}
            </div>
          </div>
        </div>
      </div>

      {/* Flags */}
      <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
        {result.master_called && (
          <span style={{ background: "#1a1a3a", border: "1px solid var(--blue)", padding: "3px 10px", borderRadius: 3, fontSize: 11, color: "var(--blue)" }}>
            ⚖ MASTER APPELÉ → {result.master_decision ?? "—"}
          </span>
        )}
        {result.trade_held_for_data && (
          <span style={{ background: "#1a1a0a", border: "1px solid var(--yellow)", padding: "3px 10px", borderRadius: 3, fontSize: 11, color: "var(--yellow)" }}>
            ⏳ EN ATTENTE DONNÉES ({result.hold_duration_minutes} min)
          </span>
        )}
        {result.dissenting_agents.length > 0 && (
          <span style={{ background: "#1a1000", border: "1px solid #885500", padding: "3px 10px", borderRadius: 3, fontSize: 11, color: "var(--yellow)" }}>
            ↔ Dissidents: {result.dissenting_agents.join(", ")}
          </span>
        )}
        {result.error && (
          <span style={{ background: "#1a0000", border: "1px solid var(--red)", padding: "3px 10px", borderRadius: 3, fontSize: 11, color: "var(--red)" }}>
            ✗ {result.error}
          </span>
        )}
        <span style={{ background: "var(--bg-card2)", border: "1px solid var(--border)", padding: "3px 10px", borderRadius: 3, fontSize: 11, color: "var(--text-dim)" }}>
          trade_id: {result.trade_id.slice(0, 8)}…
        </span>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function CouncilPage() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [result, setResult] = useState<CouncilResult | null>(null);
  const [ticker, setTicker] = useState("AAPL");
  const [signalType, setSignalType] = useState("MOMENTUM");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cbResetting, setCbResetting] = useState(false);

  const fetchStatus = () => {
    fetch(`${API}/api/council/v2/status`)
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  };

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 30_000);
    return () => clearInterval(t);
  }, []);

  const runCouncil = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await fetch(`${API}/api/council/v2/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: ticker.trim().toUpperCase(),
          signal_type: signalType,
          watchlist_tickers: [],
        }),
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`${resp.status} — ${txt}`);
      }
      const data = await resp.json();
      setResult(data);
      fetchStatus(); // refresh budgets after call
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const resetCB = async () => {
    setCbResetting(true);
    try {
      await fetch(`${API}/api/council/v2/circuit-breaker/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "Manuel via dashboard" }),
      });
      fetchStatus();
    } finally {
      setCbResetting(false);
    }
  };

  const cbLevel = status?.circuit_breaker?.level ?? "GREEN";
  const tradingBlocked = cbLevel === "RED";

  return (
    <main className="container">
      <div className="page-header">
        <h1 className="page-title">AI Council v2</h1>
        <p className="page-subtitle">
          5 agents en débat autonome — vote pondéré — apprentissage RETEX
        </p>
      </div>

      {/* Status bar */}
      {status && <StatusBar data={status} />}

      {/* Run form */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-label">NOUVELLE SESSION CONSEIL</div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12, alignItems: "flex-end" }}>
          <div>
            <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>
              TICKER
            </label>
            <input
              className="input"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="AAPL"
              style={{ width: 120, textTransform: "uppercase" }}
              onKeyDown={(e) => e.key === "Enter" && !loading && !tradingBlocked && runCouncil()}
            />
          </div>
          <div>
            <label style={{ fontSize: 11, color: "var(--text-dim)", display: "block", marginBottom: 4 }}>
              SIGNAL
            </label>
            <select
              className="input"
              value={signalType}
              onChange={(e) => setSignalType(e.target.value)}
              style={{ width: 160 }}
            >
              <option value="MOMENTUM">MOMENTUM</option>
              <option value="BREAKOUT">BREAKOUT</option>
              <option value="NEWS_HIGH">NEWS_HIGH</option>
              <option value="FUNDAMENTAL">FUNDAMENTAL</option>
            </select>
          </div>
          <button
            className="btn"
            onClick={runCouncil}
            disabled={loading || tradingBlocked}
            style={{ height: 38 }}
          >
            {loading ? "⏳ Délibération…" : tradingBlocked ? "🔴 BLOQUÉ" : "▶ Lancer le conseil"}
          </button>
          {cbLevel !== "GREEN" && (
            <button
              className="btn"
              onClick={resetCB}
              disabled={cbResetting}
              style={{ height: 38, background: "transparent", border: "1px solid var(--red)", color: "var(--red)" }}
            >
              {cbResetting ? "…" : "↺ Reset CB"}
            </button>
          )}
        </div>
        {error && (
          <div style={{ marginTop: 12, color: "var(--red)", fontSize: 12 }}>
            Erreur : {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <>
          <VoteSummary result={result} />

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12, marginBottom: 24 }}>
            {result.agent_responses.map((agent) => (
              <AgentCard
                key={agent.agent_slot}
                agent={agent}
                weight={result.agent_weights_used[agent.agent_slot] ?? 1.0}
                dissenting={result.dissenting_agents.includes(agent.agent_slot)}
              />
            ))}
          </div>

          {/* Sufficiency heatmap */}
          {Object.keys(result.information_sufficiency_scores).length > 0 && (
            <div className="card" style={{ marginBottom: 24 }}>
              <div className="card-label">SUFFICIENCY D&apos;INFORMATION PAR AGENT</div>
              <div style={{ display: "flex", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
                {Object.entries(result.information_sufficiency_scores).map(([slot, score]) => (
                  <div key={slot} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 4 }}>
                      {slot.replace("slot_", "").replace("_", " ").toUpperCase()}
                    </div>
                    <div style={{
                      width: 60, height: 60, borderRadius: "50%",
                      background: `conic-gradient(${confColor(score)} ${score}%, var(--bg-card2) 0)`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      <div style={{
                        width: 44, height: 44, borderRadius: "50%",
                        background: "var(--bg-card)", display: "flex",
                        alignItems: "center", justifyContent: "center",
                        fontSize: 12, fontWeight: 700, color: confColor(score),
                      }}>
                        {score.toFixed(0)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!result && !loading && (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-dim)" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⬡</div>
          <div style={{ fontSize: 14 }}>Entrez un ticker et lancez une session de conseil</div>
          <div style={{ fontSize: 11, marginTop: 8 }}>5 agents IA délibèrent et votent en parallèle</div>
        </div>
      )}
    </main>
  );
}
