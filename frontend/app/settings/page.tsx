"use client";

import { FormEvent, useEffect, useState } from "react";

type SettingsPayload = {
  markets_enabled: { EU: boolean; US: boolean };
  max_trades_per_day: number;
  boost_trades_per_day: number;
  boost_threshold_liquid: number;
  boost_threshold_illiquid: number;
  bonds_auto_enabled: boolean;
  bonds_allocation_cap: number;
  divergence_liquid: number;
  divergence_illiquid: number;
  default_order_type_equity: string;
  execution_mode: "SIMULATED" | "IBKR_PAPER" | "IBKR_LIVE";
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsPayload | null>(null);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetch(`${backendUrl}/api/settings`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = (await response.json()) as SettingsPayload;
        setForm(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load settings");
      }
    };

    load();
  }, []);

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setError("");

    if (!form) return;

    try {
      const response = await fetch(`${backendUrl}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form)
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`HTTP ${response.status}: ${body}`);
      }

      const saved = (await response.json()) as SettingsPayload;
      setForm(saved);
      setMessage("Saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  };

  if (!form) {
    return (
      <main>
        <h1>Settings</h1>
        {error ? <p className="status-ko">Error: {error}</p> : <p>Loading...</p>}
      </main>
    );
  }

  return (
    <main>
      <h1>Settings</h1>
      <p>
        Backend URL: <code>{backendUrl}</code>
      </p>

      <form onSubmit={saveSettings} className="settings-form">
        <label>
          Market EU
          <input
            type="checkbox"
            checked={form.markets_enabled.EU}
            onChange={(event) =>
              setForm({ ...form, markets_enabled: { ...form.markets_enabled, EU: event.target.checked } })
            }
          />
        </label>

        <label>
          Market US
          <input
            type="checkbox"
            checked={form.markets_enabled.US}
            onChange={(event) =>
              setForm({ ...form, markets_enabled: { ...form.markets_enabled, US: event.target.checked } })
            }
          />
        </label>

        <label>
          max_trades_per_day
          <input
            type="number"
            value={form.max_trades_per_day}
            onChange={(event) => setForm({ ...form, max_trades_per_day: Number(event.target.value) })}
          />
        </label>

        <label>
          boost_trades_per_day
          <input
            type="number"
            value={form.boost_trades_per_day}
            onChange={(event) => setForm({ ...form, boost_trades_per_day: Number(event.target.value) })}
          />
        </label>

        <label>
          boost_threshold_liquid
          <input
            type="number"
            step="0.01"
            value={form.boost_threshold_liquid}
            onChange={(event) => setForm({ ...form, boost_threshold_liquid: Number(event.target.value) })}
          />
        </label>

        <label>
          boost_threshold_illiquid
          <input
            type="number"
            step="0.01"
            value={form.boost_threshold_illiquid}
            onChange={(event) => setForm({ ...form, boost_threshold_illiquid: Number(event.target.value) })}
          />
        </label>

        <label>
          bonds_auto_enabled
          <input
            type="checkbox"
            checked={form.bonds_auto_enabled}
            onChange={(event) => setForm({ ...form, bonds_auto_enabled: event.target.checked })}
          />
        </label>

        <label>
          bonds_allocation_cap
          <input
            type="number"
            step="0.01"
            value={form.bonds_allocation_cap}
            onChange={(event) => setForm({ ...form, bonds_allocation_cap: Number(event.target.value) })}
          />
        </label>

        <label>
          divergence_liquid
          <input
            type="number"
            step="0.01"
            value={form.divergence_liquid}
            onChange={(event) => setForm({ ...form, divergence_liquid: Number(event.target.value) })}
          />
        </label>

        <label>
          divergence_illiquid
          <input
            type="number"
            step="0.01"
            value={form.divergence_illiquid}
            onChange={(event) => setForm({ ...form, divergence_illiquid: Number(event.target.value) })}
          />
        </label>

        <label>
          default_order_type_equity
          <input
            type="text"
            value={form.default_order_type_equity}
            onChange={(event) => setForm({ ...form, default_order_type_equity: event.target.value })}
          />
        </label>


        <label>
          execution_mode
          <select
            value={form.execution_mode}
            onChange={(event) =>
              setForm({
                ...form,
                execution_mode: event.target.value as SettingsPayload["execution_mode"]
              })
            }
          >
            <option value="SIMULATED">SIMULATED</option>
            <option value="IBKR_PAPER">IBKR_PAPER</option>
            <option value="IBKR_LIVE">IBKR_LIVE</option>
          </select>
        </label>

        <button type="submit">Save</button>
      </form>

      {message && <p className="status-ok">{message}</p>}
      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
