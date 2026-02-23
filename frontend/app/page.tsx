"use client";

import { useEffect, useState } from "react";

type WatchlistItem = {
  id: number;
  symbol: string;
  notes: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function DashboardPage() {
  const [watchlistTop, setWatchlistTop] = useState<WatchlistItem[]>([]);

  useEffect(() => {
    const loadWatchlist = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/watchlist`, { cache: "no-store" });
        if (!response.ok) return;
        const payload = (await response.json()) as WatchlistItem[];
        setWatchlistTop(payload.slice(0, 5));
      } catch {
        setWatchlistTop([]);
      }
    };

    loadWatchlist();
  }, []);

  return (
    <main>
      <h1>Orion Trader Dashboard</h1>
      <p>
        Minimal frontend scaffold. Backend status page: <a href="/status">/status</a> · Settings: <a href="/settings">/settings</a> · Chat: <a href="/chat">/chat</a> · Watchlist: <a href="/watchlist">/watchlist</a>
      </p>

      <div className="grid">
        <section className="card">
          <h2>Equity Curve</h2>
          <p>Placeholder: chart area for account equity over time.</p>
        </section>

        <section className="card">
          <h2>Agents (LIVE/SHADOW)</h2>
          <p>Placeholder: active agents and execution mode.</p>
        </section>

        <section className="card">
          <h2>Logs</h2>
          <p>Placeholder: latest strategy and execution logs.</p>
        </section>

        <section className="card">
          <h2>Orders / Proposals</h2>
          <p>Placeholder: current orders, proposals, and statuses.</p>
        </section>

        <section className="card">
          <h2>Watchlist (Top 5)</h2>
          {watchlistTop.length == 0 ? (
            <p>No active watchlist items.</p>
          ) : (
            <ul>
              {watchlistTop.map((item) => (
                <li key={item.id}>
                  <strong>{item.symbol}</strong> {item.notes ? `- ${item.notes}` : ""}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
