"use client";

import { FormEvent, useEffect, useState } from "react";

type WatchlistItem = {
  id: number;
  symbol: string;
  name: string;
  asset_type: string;
  market: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [symbol, setSymbol] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("Loading...");

  const load = async () => {
    try {
      const response = await fetch(`${backendUrl}/api/watchlist`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = (await response.json()) as WatchlistItem[];
      setItems(payload);
      setStatus("Loaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
      setStatus("Failed");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onAdd = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!symbol.trim()) return;

    try {
      const response = await fetch(`${backendUrl}/api/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: symbol.trim().toUpperCase(), notes: notes.trim() })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setSymbol("");
      setNotes("");
      await load();
      setStatus("Saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  };

  const onToggle = async (item: WatchlistItem) => {
    setError("");
    try {
      const response = await fetch(`${backendUrl}/api/watchlist/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !item.is_active })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  };

  return (
    <main>
      <h1>Watchlist</h1>
      <p>
        Backend URL: <code>{backendUrl}</code>
      </p>
      <p>Status: {status}</p>

      <form className="watchlist-form" onSubmit={onAdd}>
        <input
          type="text"
          value={symbol}
          onChange={(event) => setSymbol(event.target.value)}
          placeholder="Symbol (ex: AIR.PA)"
        />
        <input
          type="text"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Notes"
        />
        <button type="submit">Add</button>
      </form>

      <div className="watchlist-list">
        {items.length === 0 ? (
          <p>No active items.</p>
        ) : (
          items.map((item) => (
            <div className="card" key={item.id}>
              <h3>{item.symbol}</h3>
              <p>{item.notes || "No notes"}</p>
              <button type="button" onClick={() => onToggle(item)}>
                {item.is_active ? "Deactivate" : "Activate"}
              </button>
            </div>
          ))
        )}
      </div>

      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
