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

type AgentCfg = {
  claude_enabled: boolean;
  gpt4o_enabled: boolean;
  grok_enabled: boolean;
  anthropic_key_set: boolean;
  openai_key_set: boolean;
  xai_key_set: boolean;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

const AGENTS = [
  {
    id: "claude" as const,
    label: "Claude (Anthropic)",
    model: "claude-opus-4-6",
    keyField: "anthropic_api_key" as const,
    keySetField: "anthropic_key_set" as const,
    enabledField: "claude_enabled" as const,
    placeholder: "sk-ant-api03-…",
  },
  {
    id: "gpt4o" as const,
    label: "GPT-4o (OpenAI)",
    model: "gpt-4o",
    keyField: "openai_api_key" as const,
    keySetField: "openai_key_set" as const,
    enabledField: "gpt4o_enabled" as const,
    placeholder: "sk-…",
  },
  {
    id: "grok" as const,
    label: "Grok (xAI)",
    model: "grok-3",
    keyField: "xai_api_key" as const,
    keySetField: "xai_key_set" as const,
    enabledField: "grok_enabled" as const,
    placeholder: "xai-…",
  },
];

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsPayload | null>(null);
  const [message, setMessage] = useState<string>("");
  const [error, setError] = useState<string>("");

  // Agent config state
  const [agentCfg, setAgentCfg] = useState<AgentCfg | null>(null);
  const [agentKeys, setAgentKeys] = useState<Record<string, string>>({});
  const [agentMsg, setAgentMsg] = useState<string>("");
  const [agentErr, setAgentErr] = useState<string>("");
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch(`${backendUrl}/api/settings`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((d) => setForm(d as SettingsPayload))
      .catch((e) => setError(String(e)));

    fetch(`${backendUrl}/api/agents/config`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((d) => setAgentCfg(d as AgentCfg))
      .catch(() => {});
  }, []);

  const saveSettings = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!form) return;
    try {
      const r = await fetch(`${backendUrl}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      setForm(await r.json());
      setMessage("Paramètres sauvegardés");
    } catch (e) {
      setError(String(e));
    }
  };

  const saveAgentCfg = async () => {
    setAgentMsg("");
    setAgentErr("");
    if (!agentCfg) return;
    try {
      const payload: Record<string, unknown> = {
        claude_enabled: agentCfg.claude_enabled,
        gpt4o_enabled: agentCfg.gpt4o_enabled,
        grok_enabled: agentCfg.grok_enabled,
      };
      for (const agent of AGENTS) {
        const val = agentKeys[agent.keyField];
        if (val !== undefined) payload[agent.keyField] = val;
      }
      const r = await fetch(`${backendUrl}/api/agents/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      const updated = await r.json() as AgentCfg;
      setAgentCfg(updated);
      setAgentKeys({});
      setAgentMsg("Configuration IA sauvegardée");
    } catch (e) {
      setAgentErr(String(e));
    }
  };

  if (!form) {
    return (
      <main>
        <h1>Settings</h1>
        {error ? <p className="status-ko">{error}</p> : <p style={{ color: "var(--text-dim)" }}>Chargement…</p>}
      </main>
    );
  }

  return (
    <main>
      <h1>Settings</h1>

      {/* ── AI Agents ── */}
      <section id="agents" style={{ marginBottom: "2.5rem" }}>
        <h2>Agents IA</h2>
        <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "1rem" }}>
          Activez les agents qui participent au comité de vote. Chaque agent nécessite une clé API.
        </p>

        {agentCfg && (
          <div style={{ display: "grid", gap: "0.75rem", maxWidth: "580px" }}>
            {AGENTS.map((agent) => {
              const enabled = agentCfg[agent.enabledField];
              const keySet = agentCfg[agent.keySetField];
              const pendingKey = agentKeys[agent.keyField] ?? "";
              const revealed = showKeys[agent.id] ?? false;

              return (
                <div key={agent.id} className={`card card-accent`} style={{ padding: "0.9rem 1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.6rem" }}>
                    <label className="toggle">
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => setAgentCfg({ ...agentCfg, [agent.enabledField]: e.target.checked })}
                      />
                      <span className="toggle-slider" />
                    </label>
                    <span style={{ fontWeight: 700, fontSize: "0.9rem", color: enabled ? "var(--green)" : "var(--text-dim)" }}>
                      {agent.label}
                    </span>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-dim)", marginLeft: "auto" }}>{agent.model}</span>
                    <span className={`badge ${keySet || pendingKey ? "badge-on" : "badge-off"}`}>
                      {keySet || pendingKey ? "Clé ✓" : "Pas de clé"}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    <input
                      type={revealed ? "text" : "password"}
                      value={pendingKey}
                      placeholder={keySet ? "••••••• (clé existante)" : agent.placeholder}
                      style={{ flex: 1, fontSize: "0.8rem" }}
                      onChange={(e) => setAgentKeys({ ...agentKeys, [agent.keyField]: e.target.value })}
                    />
                    <button
                      type="button"
                      style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                      onClick={() => setShowKeys({ ...showKeys, [agent.id]: !revealed })}
                    >
                      {revealed ? "Masquer" : "Voir"}
                    </button>
                  </div>
                </div>
              );
            })}

            <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.25rem" }}>
              <button type="button" onClick={saveAgentCfg}>Sauvegarder la config IA</button>
              {agentMsg && <span className="status-ok" style={{ fontSize: "0.8rem" }}>{agentMsg}</span>}
              {agentErr && <span className="status-ko" style={{ fontSize: "0.8rem" }}>{agentErr}</span>}
            </div>
          </div>
        )}
      </section>

      {/* ── Trading Settings ── */}
      <section>
        <h2>Paramètres de trading</h2>
        <form onSubmit={saveSettings} className="settings-form">
          <label>
            Marché EU
            <input
              type="checkbox"
              checked={form.markets_enabled.EU}
              onChange={(e) => setForm({ ...form, markets_enabled: { ...form.markets_enabled, EU: e.target.checked } })}
            />
          </label>

          <label>
            Marché US
            <input
              type="checkbox"
              checked={form.markets_enabled.US}
              onChange={(e) => setForm({ ...form, markets_enabled: { ...form.markets_enabled, US: e.target.checked } })}
            />
          </label>

          <label>
            max_trades_per_day
            <input type="number" value={form.max_trades_per_day}
              onChange={(e) => setForm({ ...form, max_trades_per_day: Number(e.target.value) })} />
          </label>

          <label>
            boost_trades_per_day
            <input type="number" value={form.boost_trades_per_day}
              onChange={(e) => setForm({ ...form, boost_trades_per_day: Number(e.target.value) })} />
          </label>

          <label>
            boost_threshold_liquid
            <input type="number" step="0.01" value={form.boost_threshold_liquid}
              onChange={(e) => setForm({ ...form, boost_threshold_liquid: Number(e.target.value) })} />
          </label>

          <label>
            boost_threshold_illiquid
            <input type="number" step="0.01" value={form.boost_threshold_illiquid}
              onChange={(e) => setForm({ ...form, boost_threshold_illiquid: Number(e.target.value) })} />
          </label>

          <label>
            bonds_auto_enabled
            <input type="checkbox" checked={form.bonds_auto_enabled}
              onChange={(e) => setForm({ ...form, bonds_auto_enabled: e.target.checked })} />
          </label>

          <label>
            bonds_allocation_cap
            <input type="number" step="0.01" value={form.bonds_allocation_cap}
              onChange={(e) => setForm({ ...form, bonds_allocation_cap: Number(e.target.value) })} />
          </label>

          <label>
            divergence_liquid
            <input type="number" step="0.01" value={form.divergence_liquid}
              onChange={(e) => setForm({ ...form, divergence_liquid: Number(e.target.value) })} />
          </label>

          <label>
            divergence_illiquid
            <input type="number" step="0.01" value={form.divergence_illiquid}
              onChange={(e) => setForm({ ...form, divergence_illiquid: Number(e.target.value) })} />
          </label>

          <label>
            default_order_type_equity
            <input type="text" value={form.default_order_type_equity}
              onChange={(e) => setForm({ ...form, default_order_type_equity: e.target.value })} />
          </label>

          <label>
            execution_mode
            <select value={form.execution_mode}
              onChange={(e) => setForm({ ...form, execution_mode: e.target.value as SettingsPayload["execution_mode"] })}>
              <option value="SIMULATED">SIMULATED</option>
              <option value="IBKR_PAPER">IBKR_PAPER</option>
              <option value="IBKR_LIVE">IBKR_LIVE</option>
            </select>
          </label>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <button type="submit">Sauvegarder</button>
            {message && <span className="status-ok" style={{ fontSize: "0.8rem" }}>{message}</span>}
            {error && <span className="status-ko" style={{ fontSize: "0.8rem" }}>{error}</span>}
          </div>
        </form>
      </section>
    </main>
  );
}
