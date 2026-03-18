"use client";

import { useEffect, useMemo, useState } from "react";

type WatchlistItem = { id: number; symbol: string; notes: string };
type NewsItem = { id: number; title: string; feed_name: string; link?: string };
type Proposal = { id: number; symbol: string; side: string; status: string };
type PortfolioState = { cash_eur: number; equity_eur: number; unrealized_pnl_eur: number; realized_pnl_eur: number };
type EquityCurvePoint = { ts: string; equity_eur: number };
type PerformanceSummary = { current_equity_eur: number; performance_since_start_pct: number; trades_count: number; pnl_total_eur: number };
type ExecutionStatus = { mode: string };
type MarketIndicators = { symbol: string; sma20: number | null; sma50: number | null; rsi14: number | null };
type AgentCfg = { claude_enabled: boolean; gpt4o_enabled: boolean; grok_enabled: boolean; anthropic_key_set: boolean; openai_key_set: boolean; xai_key_set: boolean };
type CouncilStatus = {
  circuit_breaker: { level: string; description: string; position_multiplier: number };
  market_regime: { regime: string; vix_level: number | null };
  budgets: { provider: string; balance_eur: number; status: string }[];
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

function svgPolyline(values: number[], w: number, h: number): string {
  if (values.length < 2) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / span) * (h - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function rsiColor(rsi: number | null): string {
  if (rsi === null) return "var(--text-dim)";
  if (rsi > 70) return "var(--red)";
  if (rsi < 30) return "var(--green)";
  return "var(--yellow)";
}

export default function DashboardPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [market, setMarket] = useState<MarketIndicators[]>([]);
  const [pending, setPending] = useState<Proposal[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioState | null>(null);
  const [curve, setCurve] = useState<EquityCurvePoint[]>([]);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [exec, setExec] = useState<ExecutionStatus | null>(null);
  const [agentCfg, setAgentCfg] = useState<AgentCfg | null>(null);
  const [councilStatus, setCouncilStatus] = useState<CouncilStatus | null>(null);

  useEffect(() => {
    const load = async () => {
      const [wRes, nRes, pRes, pfRes, cRes, perfRes, eRes, aRes, csRes] = await Promise.allSettled([
        fetch(`${backendUrl}/api/watchlist`),
        fetch(`${backendUrl}/api/news?limit=5`),
        fetch(`${backendUrl}/api/proposals?status=PENDING&limit=5`),
        fetch(`${backendUrl}/api/portfolio`),
        fetch(`${backendUrl}/api/portfolio/equity_curve?limit=120`),
        fetch(`${backendUrl}/api/portfolio/performance_summary`),
        fetch(`${backendUrl}/api/execution/status`),
        fetch(`${backendUrl}/api/agents/config`),
        fetch(`${backendUrl}/api/council/v2/status`),
      ]);

      let wl: WatchlistItem[] = [];
      if (wRes.status === "fulfilled" && wRes.value.ok) {
        wl = await wRes.value.json();
        setWatchlist(wl.slice(0, 5));
      }
      if (nRes.status === "fulfilled" && nRes.value.ok) setNews(await nRes.value.json());
      if (pRes.status === "fulfilled" && pRes.value.ok) setPending(await pRes.value.json());
      if (pfRes.status === "fulfilled" && pfRes.value.ok) {
        const d = await pfRes.value.json();
        setPortfolio(d.state ?? null);
      }
      if (cRes.status === "fulfilled" && cRes.value.ok) setCurve(await cRes.value.json());
      if (perfRes.status === "fulfilled" && perfRes.value.ok) setPerf(await perfRes.value.json());
      if (eRes.status === "fulfilled" && eRes.value.ok) setExec(await eRes.value.json());
      if (aRes.status === "fulfilled" && aRes.value.ok) setAgentCfg(await aRes.value.json());
      if (csRes.status === "fulfilled" && csRes.value.ok) setCouncilStatus(await csRes.value.json());

      const symbols = wl.slice(0, 3).map((i) => i.symbol);
      const indics = await Promise.allSettled(
        symbols.map((s) => fetch(`${backendUrl}/api/market/indicators?symbol=${s}`).then((r) => r.ok ? r.json() : null))
      );
      setMarket(indics.flatMap((r) => (r.status === "fulfilled" && r.value ? [r.value] : [])));
    };
    load();
  }, []);

  const polyline = useMemo(() => svgPolyline(curve.map((p) => p.equity_eur), 400, 100), [curve]);
  const perfPct = perf?.performance_since_start_pct ?? 0;
  const perfColor = perfPct >= 0 ? "var(--green)" : "var(--red)";

  const agents = agentCfg ? [
    { name: "Claude", enabled: agentCfg.claude_enabled, keySet: agentCfg.anthropic_key_set },
    { name: "GPT-4o", enabled: agentCfg.gpt4o_enabled, keySet: agentCfg.openai_key_set },
    { name: "Grok",   enabled: agentCfg.grok_enabled,   keySet: agentCfg.xai_key_set },
  ] : [];

  return (
    <main>
      <h1>Dashboard</h1>

      <div className="grid">
        {/* ── Equity curve ── */}
        <div className="card card-accent" style={{ gridColumn: "span 2" }}>
          <h2>Equity curve</h2>
          {curve.length < 2 ? (
            <p style={{ color: "var(--text-dim)" }}>Aucune donnée.</p>
          ) : (
            <svg className="equity-svg" viewBox={`0 0 400 100`} height="100" preserveAspectRatio="none">
              <defs>
                <linearGradient id="eg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--green)" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="var(--green)" stopOpacity="0" />
                </linearGradient>
              </defs>
              <polyline fill="none" stroke="var(--green)" strokeWidth="1.5" points={polyline} />
            </svg>
          )}
          {perf && (
            <div style={{ display: "flex", gap: "1.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
              <span style={{ fontSize: "0.85rem" }}>
                Equity : <strong>{perf.current_equity_eur.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €</strong>
              </span>
              <span style={{ fontSize: "0.85rem", color: perfColor, fontWeight: 700 }}>
                {perfPct >= 0 ? "+" : ""}{perfPct.toFixed(2)}%
              </span>
              <span style={{ fontSize: "0.85rem", color: "var(--text-dim)" }}>
                {perf.trades_count} trades · PnL {perf.pnl_total_eur >= 0 ? "+" : ""}{perf.pnl_total_eur.toFixed(2)} €
              </span>
            </div>
          )}
        </div>

        {/* ── Comité v1 ── */}
        <div className="card">
          <h2>Comité v1</h2>
          <div style={{ fontSize: "0.72rem", color: "var(--text-dim)", marginBottom: "0.5rem" }}>
            3 agents · 2 rounds · vote majoritaire
          </div>
          {agents.length === 0 ? (
            <p style={{ color: "var(--text-dim)" }}>Chargement…</p>
          ) : (
            <div style={{ display: "grid", gap: "0.4rem" }}>
              {agents.map((a) => (
                <div key={a.name} className="toggle-row">
                  <span style={{ color: a.enabled ? "var(--green)" : "var(--text-dim)" }}>
                    <span className={`dot ${a.enabled ? "dot-green" : "dot-gray"}`} />
                    {a.name}
                  </span>
                  <span style={{ display: "flex", gap: "0.4rem" }}>
                    <span className={`badge ${a.enabled ? "badge-on" : "badge-off"}`}>{a.enabled ? "ON" : "OFF"}</span>
                    <span className={`badge ${a.keySet ? "badge-on" : "badge-off"}`}>{a.keySet ? "Clé ✓" : "Pas de clé"}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: "0.75rem" }}>
            <a href="/committee" style={{ fontSize: "0.8rem" }}>→ Lancer le comité</a>
            {" · "}
            <a href="/settings#agents" style={{ fontSize: "0.8rem" }}>Configurer</a>
          </div>
        </div>

        {/* ── Council v2 ── */}
        <div className="card">
          <h2>Council v2</h2>
          <div style={{ fontSize: "0.72rem", color: "var(--text-dim)", marginBottom: "0.5rem" }}>
            5 agents · vote pondéré · RETEX · circuit breaker
          </div>
          {councilStatus ? (
            <>
              {/* Circuit breaker */}
              <div className="toggle-row" style={{ marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.8rem" }}>Circuit Breaker</span>
                <span style={{
                  fontWeight: 700, fontSize: "0.8rem",
                  color: { GREEN: "var(--green)", YELLOW: "var(--yellow)", ORANGE: "#ff8800", RED: "var(--red)" }[councilStatus.circuit_breaker.level] ?? "var(--text-dim)",
                }}>
                  {councilStatus.circuit_breaker.level}
                </span>
              </div>
              {/* Regime */}
              <div className="toggle-row" style={{ marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.8rem" }}>Régime</span>
                <span style={{ fontSize: "0.8rem", color: "var(--green)" }}>
                  {councilStatus.market_regime.regime}
                  {councilStatus.market_regime.vix_level !== null && (
                    <span style={{ color: "var(--text-dim)", fontWeight: 400 }}> · VIX {councilStatus.market_regime.vix_level.toFixed(1)}</span>
                  )}
                </span>
              </div>
              {/* Budgets */}
              {councilStatus.budgets.map((b) => (
                <div key={b.provider} className="toggle-row">
                  <span style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>{b.provider}</span>
                  <span style={{
                    fontSize: "0.8rem", fontWeight: 700,
                    color: b.status === "OK" ? "var(--green)" : b.status === "LOW" ? "var(--yellow)" : "var(--red)",
                  }}>
                    €{b.balance_eur?.toFixed(2) ?? "—"}
                  </span>
                </div>
              ))}
            </>
          ) : (
            <p style={{ color: "var(--text-dim)", fontSize: "0.8rem" }}>Chargement…</p>
          )}
          <div style={{ marginTop: "0.75rem" }}>
            <a href="/council" style={{ fontSize: "0.8rem" }}>→ Lancer le conseil</a>
            {" · "}
            <a href="/settings#council-keys" style={{ fontSize: "0.8rem" }}>Clés API</a>
          </div>
        </div>

        {/* ── Portfolio ── */}
        <div className="card">
          <h2>Portfolio</h2>
          {portfolio ? (
            <div style={{ display: "grid", gap: "0.3rem" }}>
              <div className="toggle-row"><span>Cash</span><strong>{portfolio.cash_eur.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €</strong></div>
              <div className="toggle-row"><span>Equity</span><strong>{portfolio.equity_eur.toLocaleString("fr-FR", { minimumFractionDigits: 2 })} €</strong></div>
              <div className="toggle-row"><span>uPnL</span><strong style={{ color: portfolio.unrealized_pnl_eur >= 0 ? "var(--green)" : "var(--red)" }}>{portfolio.unrealized_pnl_eur >= 0 ? "+" : ""}{portfolio.unrealized_pnl_eur.toFixed(2)} €</strong></div>
              <div className="toggle-row"><span>rPnL</span><strong style={{ color: portfolio.realized_pnl_eur >= 0 ? "var(--green)" : "var(--red)" }}>{portfolio.realized_pnl_eur >= 0 ? "+" : ""}{portfolio.realized_pnl_eur.toFixed(2)} €</strong></div>
            </div>
          ) : (
            <p style={{ color: "var(--text-dim)" }}>Aucun portefeuille.</p>
          )}
          <div style={{ marginTop: "0.75rem" }}><a href="/portfolio" style={{ fontSize: "0.8rem" }}>→ Portfolio complet</a></div>
        </div>

        {/* ── Market snapshot ── */}
        <div className="card">
          <h2>Market snapshot</h2>
          {market.length === 0 ? (
            <p style={{ color: "var(--text-dim)" }}>Pas de données.</p>
          ) : (
            <div style={{ display: "grid", gap: "0.4rem" }}>
              {market.map((m) => (
                <div key={m.symbol} className="toggle-row">
                  <strong style={{ letterSpacing: "0.06em" }}>{m.symbol}</strong>
                  <span style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.8rem" }}>
                    {m.rsi14 !== null && (
                      <span style={{ color: rsiColor(m.rsi14) }}>RSI {m.rsi14.toFixed(0)}</span>
                    )}
                    <span style={{ color: m.sma20 && m.sma50 && m.sma20 > m.sma50 ? "var(--green)" : "var(--red)", fontSize: "0.72rem" }}>
                      {m.sma20 && m.sma50 ? (m.sma20 > m.sma50 ? "↑ bull" : "↓ bear") : "—"}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: "0.75rem" }}><a href="/market" style={{ fontSize: "0.8rem" }}>→ Marché</a></div>
        </div>

        {/* ── Watchlist ── */}
        <div className="card">
          <h2>Watchlist</h2>
          {watchlist.length === 0 ? (
            <p style={{ color: "var(--text-dim)" }}>Vide.</p>
          ) : (
            <ul>
              {watchlist.map((item) => (
                <li key={item.id}>
                  <strong style={{ letterSpacing: "0.06em" }}>{item.symbol}</strong>
                  {item.notes && <span style={{ color: "var(--text-dim)", fontSize: "0.78rem" }}> — {item.notes}</span>}
                </li>
              ))}
            </ul>
          )}
          <div style={{ marginTop: "0.75rem" }}><a href="/watchlist" style={{ fontSize: "0.8rem" }}>→ Gérer la watchlist</a></div>
        </div>

        {/* ── Pending proposals ── */}
        <div className="card">
          <h2>Propositions en attente</h2>
          {pending.length === 0 ? (
            <p style={{ color: "var(--text-dim)" }}>Aucune proposition.</p>
          ) : (
            <ul>
              {pending.map((p) => (
                <li key={p.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className={`badge badge-${p.side.toLowerCase()}`}>{p.side}</span>
                  <strong style={{ letterSpacing: "0.06em" }}>{p.symbol}</strong>
                  <span style={{ color: "var(--text-dim)", fontSize: "0.78rem" }}>#{p.id}</span>
                </li>
              ))}
            </ul>
          )}
          <div style={{ marginTop: "0.75rem" }}><a href="/proposals" style={{ fontSize: "0.8rem" }}>→ Gérer les propositions</a></div>
        </div>

        {/* ── News ── */}
        <div className="card" style={{ gridColumn: "span 2" }}>
          <h2>Dernières actualités</h2>
          {news.length === 0 ? (
            <p style={{ color: "var(--text-dim)" }}>Aucune news.</p>
          ) : (
            <ul>
              {news.map((item) => (
                <li key={item.id} style={{ padding: "0.3rem 0" }}>
                  <span style={{ color: "var(--text-dim)", fontSize: "0.72rem", marginRight: "0.5rem" }}>{item.feed_name}</span>
                  {item.link ? (
                    <a href={item.link} target="_blank" rel="noreferrer" style={{ fontSize: "0.83rem" }}>{item.title}</a>
                  ) : (
                    <span style={{ fontSize: "0.83rem" }}>{item.title}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div style={{ marginTop: "0.75rem" }}><a href="/news" style={{ fontSize: "0.8rem" }}>→ Toutes les news</a></div>
        </div>
      </div>
    </main>
  );
}
