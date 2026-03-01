"use client";

import { useEffect, useState } from "react";

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

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function PortfolioPage() {
  const [state, setState] = useState<PortfolioState | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reflections, setReflections] = useState<Reflection[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const [portfolioRes, tradesRes, reflectionsRes] = await Promise.all([
          fetch(`${backendUrl}/api/portfolio`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/trades?limit=50`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/reflections?limit=50`, { cache: "no-store" })
        ]);
        if (!portfolioRes.ok || !tradesRes.ok || !reflectionsRes.ok) {
          throw new Error("Load failed");
        }
        const portfolioPayload = (await portfolioRes.json()) as { state: PortfolioState; positions: Position[] };
        setState(portfolioPayload.state);
        setPositions(portfolioPayload.positions);
        setTrades((await tradesRes.json()) as Trade[]);
        setReflections((await reflectionsRes.json()) as Reflection[]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Load failed");
      }
    };
    load();
  }, []);

  return (
    <main>
      <h1>Portfolio (Simulator)</h1>

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
