"use client";

import { useEffect, useState } from "react";

type WatchlistItem = { id: number; symbol: string; notes: string };
type MarketBar = {
  id: number;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
type MarketIndicators = {
  symbol: string;
  sma20: number | null;
  sma50: number | null;
  rsi14: number | null;
  volatility: number | null;
  horizon_hint: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function MarketPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [bars, setBars] = useState<MarketBar[]>([]);
  const [indicators, setIndicators] = useState<MarketIndicators | null>(null);
  const [status, setStatus] = useState<string>("Loading...");
  const [error, setError] = useState<string>("");

  const loadWatchlist = async () => {
    const res = await fetch(`${backendUrl}/api/watchlist`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as WatchlistItem[];
    setWatchlist(data);
    if (!selected && data.length > 0) {
      setSelected(data[0].symbol);
    }
  };

  const loadMarket = async (symbol: string) => {
    if (!symbol) return;
    const [barsRes, indRes] = await Promise.all([
      fetch(`${backendUrl}/api/market/bars?symbol=${encodeURIComponent(symbol)}&limit=200`, {
        cache: "no-store"
      }),
      fetch(`${backendUrl}/api/market/indicators?symbol=${encodeURIComponent(symbol)}`, {
        cache: "no-store"
      })
    ]);
    if (!barsRes.ok || !indRes.ok) throw new Error("Failed to load market data");
    setBars((await barsRes.json()) as MarketBar[]);
    setIndicators((await indRes.json()) as MarketIndicators);
  };

  const init = async () => {
    try {
      await loadWatchlist();
      setStatus("Loaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
      setStatus("Failed");
    }
  };

  useEffect(() => {
    init();
  }, []);

  useEffect(() => {
    if (selected) {
      loadMarket(selected).catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Market load failed");
      });
    }
  }, [selected]);

  const fetchOne = async () => {
    if (!selected) return;
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/market/fetch?symbol=${encodeURIComponent(selected)}`, {
        method: "POST"
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadMarket(selected);
      setStatus("Fetched selected symbol");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
    }
  };

  const fetchWatchlist = async () => {
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/market/fetch_watchlist`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (selected) await loadMarket(selected);
      setStatus("Fetched watchlist");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch watchlist failed");
    }
  };

  return (
    <main>
      <h1>Market Data</h1>
      <p>Status: {status}</p>

      <section className="card">
        <h2>Active Watchlist</h2>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          {watchlist.map((item) => (
            <option key={item.id} value={item.symbol}>
              {item.symbol}
            </option>
          ))}
        </select>
        <div className="market-actions">
          <button type="button" onClick={fetchOne}>Fetch</button>
          <button type="button" onClick={fetchWatchlist}>Fetch watchlist</button>
        </div>
      </section>

      <section className="card">
        <h2>Indicators</h2>
        {indicators ? (
          <ul>
            <li>SMA20: {indicators.sma20 ?? "n/a"}</li>
            <li>SMA50: {indicators.sma50 ?? "n/a"}</li>
            <li>RSI14: {indicators.rsi14 ?? "n/a"}</li>
            <li>Volatility: {indicators.volatility ?? "n/a"}</li>
            <li>Horizon: {indicators.horizon_hint}</li>
          </ul>
        ) : (
          <p>No indicators.</p>
        )}
      </section>

      <section className="card">
        <h2>Latest Bars</h2>
        {bars.length === 0 ? (
          <p>No bars.</p>
        ) : (
          <table className="bars-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Close</th>
                <th>Volume</th>
              </tr>
            </thead>
            <tbody>
              {bars.slice(0, 30).map((bar) => (
                <tr key={bar.id}>
                  <td>{bar.ts}</td>
                  <td>{bar.open}</td>
                  <td>{bar.high}</td>
                  <td>{bar.low}</td>
                  <td>{bar.close}</td>
                  <td>{bar.volume}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
