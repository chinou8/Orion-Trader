"use client";

import { useEffect, useState } from "react";

type Proposal = {
  id: number;
  created_at: string;
  symbol: string;
  asset_type: "EQUITY" | "ETF" | "BOND";
  market: string;
  side: "BUY" | "SELL" | "HOLD";
  qty: number | null;
  notional_eur: number | null;
  order_type: "LIMIT";
  limit_price: number | null;
  horizon_window: string;
  thesis_json: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXECUTED" | "CANCELLED";
  approved_by: string | null;
  approved_at: string | null;
  notes: string | null;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function ProposalsPage() {
  const [items, setItems] = useState<Proposal[]>([]);
  const [status, setStatus] = useState<string>("PENDING");
  const [error, setError] = useState<string>("");

  const load = async (nextStatus: string) => {
    const q = nextStatus === "ALL" ? "" : `?status=${encodeURIComponent(nextStatus)}&limit=100`;
    const res = await fetch(`${backendUrl}/api/proposals${q}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    setItems((await res.json()) as Proposal[]);
  };

  useEffect(() => {
    load(status).catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, [status]);

  const action = async (id: number, kind: "approve" | "reject") => {
    setError("");
    try {
      const res = await fetch(`${backendUrl}/api/proposals/${id}/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(kind === "approve" ? { approved_by: "operator" } : { notes: "Rejected from UI" })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await load(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  };

  return (
    <main>
      <h1>Trade Proposals</h1>
      <p>
        Backend URL: <code>{backendUrl}</code>
      </p>

      <section className="card">
        <h2>Filters</h2>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="ALL">ALL</option>
          <option value="PENDING">PENDING</option>
          <option value="APPROVED">APPROVED</option>
          <option value="REJECTED">REJECTED</option>
          <option value="EXECUTED">EXECUTED</option>
          <option value="CANCELLED">CANCELLED</option>
        </select>
      </section>

      <section className="card">
        <h2>Proposals</h2>
        {items.length === 0 ? (
          <p>No proposals.</p>
        ) : (
          <div className="watchlist-list">
            {items.map((item) => (
              <article key={item.id} className="feed-row">
                <div>
                  <p>
                    <strong>#{item.id}</strong> {item.symbol} {item.side} ({item.status})
                  </p>
                  <p>
                    {item.asset_type} · {item.market} · {item.order_type} · horizon {item.horizon_window}
                  </p>
                  <details>
                    <summary>Thesis JSON</summary>
                    <pre>{item.thesis_json}</pre>
                  </details>
                  {item.notes ? <p>Notes: {item.notes}</p> : null}
                </div>
                <div>
                  <button type="button" onClick={() => action(item.id, "approve")}>Approve</button>{" "}
                  <button type="button" onClick={() => action(item.id, "reject")}>Reject</button>
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
