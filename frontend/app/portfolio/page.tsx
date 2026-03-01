"use client";

import { useEffect, useMemo, useState } from "react";

type PortfolioState = {
  cash_eur: number;
  equity_eur: number;
  unrealized_pnl_eur: number;
  realized_pnl_eur: number;
};

type Position = {
  symbol: string;
  qty: number;
  avg_price: number;
  market_price: number;
  market_value: number;
  unrealized_pnl_eur: number;
};

type Trade = {
  id: number;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  ts: string;
  fees_eur: number;
};

type Reflection = {
  id: number;
  proposal_id: number;
  text: string;
  json_payload: string;
  ts: string;
};

type EquityCurvePoint = {
  ts: string;
  equity_eur: number;
  cash_eur: number;
  realized_pnl_eur: number;
  unrealized_pnl_eur: number;
};

type PerformanceSummary = {
  current_equity_eur: number;
  performance_since_start_pct: number;
  trades_count: number;
  pnl_total_eur: number;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

function polylinePoints(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function PortfolioPage() {
  const [state, setState] = useState<PortfolioState | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reflections, setReflections] = useState<Reflection[]>([]);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [performanceSummary, setPerformanceSummary] = useState<PerformanceSummary | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const [portfolioRes, tradesRes, reflectionsRes, curveRes, perfRes] = await Promise.all([
          fetch(`${backendUrl}/api/portfolio`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/trades?limit=50`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/reflections?limit=50`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/portfolio/equity_curve?limit=500`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/portfolio/performance_summary`, { cache: "no-store" })
        ]);
        if (!portfolioRes.ok || !tradesRes.ok || !reflectionsRes.ok || !curveRes.ok || !perfRes.ok) {
          throw new Error("Load failed");
        }
        const portfolioPayload = (await portfolioRes.json()) as { state: PortfolioState; positions: Position[] };
        setState(portfolioPayload.state);
        setPositions(portfolioPayload.positions);
        setTrades((await tradesRes.json()) as Trade[]);
        setReflections((await reflectionsRes.json()) as Reflection[]);
        setEquityCurve((await curveRes.json()) as EquityCurvePoint[]);
        setPerformanceSummary((await perfRes.json()) as PerformanceSummary);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Load failed");
      }
    };
    load();
  }, []);

  const equityPolyline = useMemo(
    () => polylinePoints(equityCurve.map((point) => point.equity_eur), 680, 220),
    [equityCurve]
  );

  return (
    <main>
      <h1>Portfolio (Simulator)</h1>

      <section className="card">
        <h2>Equity Curve</h2>
        {equityCurve.length < 1 ? (
          <p>No equity points.</p>
        ) : (
          <svg viewBox="0 0 680 220" width="100%" height="220" role="img" aria-label="Portfolio equity curve">
            <polyline fill="none" stroke="#38bdf8" strokeWidth="2" points={equityPolyline} />
          </svg>
        )}
        {performanceSummary ? (
          <ul>
            <li>Current equity: {performanceSummary.current_equity_eur.toFixed(2)} EUR</li>
            <li>Perf since start: {performanceSummary.performance_since_start_pct.toFixed(2)}%</li>
            <li>Trades: {performanceSummary.trades_count}</li>
            <li>Total PnL: {performanceSummary.pnl_total_eur.toFixed(2)} EUR</li>
          </ul>
        ) : null}
      </section>

      <section className="card">
        <h2>Snapshot</h2>
        {state ? (
          <ul>
            <li>Cash EUR: {state.cash_eur}</li>
            <li>Equity EUR: {state.equity_eur}</li>
            <li>Unrealized PnL EUR: {state.unrealized_pnl_eur}</li>
            <li>Realized PnL EUR: {state.realized_pnl_eur}</li>
          </ul>
        ) : (
          <p>No state.</p>
        )}
      </section>

      <section className="card">
        <h2>Positions</h2>
        {positions.length === 0 ? (
          <p>No open positions.</p>
        ) : (
          <ul>
            {positions.map((p) => (
              <li key={p.symbol}>
                <strong>{p.symbol}</strong> qty {p.qty} avg {p.avg_price} mkt {p.market_price} value {p.market_value} uPnL {p.unrealized_pnl_eur}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Recent Trades</h2>
        {trades.length === 0 ? (
          <p>No simulated trades.</p>
        ) : (
          <ul>
            {trades.map((t) => (
              <li key={t.id}>
                #{t.id} {t.symbol} {t.side} qty {t.qty} @ {t.price} (fee {t.fees_eur})
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Recent Reflections</h2>
        {reflections.length === 0 ? (
          <p>No reflections.</p>
        ) : (
          <div className="watchlist-list">
            {reflections.map((r) => (
              <article key={r.id} className="feed-row">
                <div>
                  <p>
                    <strong>Reflection #{r.id}</strong> (proposal #{r.proposal_id})
                  </p>
                  <p>{r.text}</p>
                  <details>
                    <summary>Payload</summary>
                    <pre>{r.json_payload}</pre>
                  </details>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
