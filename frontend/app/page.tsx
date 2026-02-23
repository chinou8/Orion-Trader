"use client";

import { useEffect, useState } from "react";

type WatchlistItem = {
  id: number;
  symbol: string;
  notes: string;
};

type NewsItem = {
  id: number;
  title: string;
  feed_name: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function DashboardPage() {
  const [watchlistTop, setWatchlistTop] = useState<WatchlistItem[]>([]);
  const [newsTop, setNewsTop] = useState<NewsItem[]>([]);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [watchlistRes, newsRes] = await Promise.all([
          fetch(`${backendUrl}/api/watchlist`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/news?limit=5`, { cache: "no-store" })
        ]);

        if (watchlistRes.ok) {
          const watchlistPayload = (await watchlistRes.json()) as WatchlistItem[];
          setWatchlistTop(watchlistPayload.slice(0, 5));
        }

        if (newsRes.ok) {
          const newsPayload = (await newsRes.json()) as NewsItem[];
          setNewsTop(newsPayload.slice(0, 5));
        }
      } catch {
        setWatchlistTop([]);
        setNewsTop([]);
      }
    };

    loadData();
  }, []);

  return (
    <main>
      <h1>Orion Trader Dashboard</h1>
      <p>
        Minimal frontend scaffold. Backend status page: <a href="/status">/status</a> · Settings: <a href="/settings">/settings</a> · Chat: <a href="/chat">/chat</a> · Watchlist: <a href="/watchlist">/watchlist</a> · News: <a href="/news">/news</a>
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
          {watchlistTop.length === 0 ? (
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

        <section className="card">
          <h2>Latest News</h2>
          {newsTop.length === 0 ? (
            <p>No news items yet.</p>
          ) : (
            <ul>
              {newsTop.map((item) => (
                <li key={item.id}>
                  <strong>{item.feed_name}</strong> - {item.title}
                </li>
              ))}
            </ul>
          )}
          <p><a href="/news">See all news</a></p>
        </section>
      </div>
    </main>
  );
}
