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

type CouncilKeyStatus = { set: boolean; source: "db" | "env" | "none" };
type CouncilKeysStatus = {
  openrouter_api_key: CouncilKeyStatus;
  xai_api_key: CouncilKeyStatus;
};

const COUNCIL_KEYS = [
  {
    id: "openrouter_api_key" as const,
    label: "OpenRouter API Key",
    hint: "Utilisée par les agents Fundamentalist, Quant, Contrarian, Finance et Master",
    placeholder: "sk-or-…",
  },
  {
    id: "xai_api_key" as const,
    label: "xAI API Key (Grok)",
    hint: "Utilisée par l'agent News/Sentiment (slot 3)",
    placeholder: "xai-…",
  },
];

// Modèles suggérés par provider (liste non exhaustive, l'utilisateur peut taper librement)
const SUGGESTED_MODELS: Record<string, string[]> = {
  slot_1_fundamentalist: ["anthropic/claude-sonnet-4-5", "anthropic/claude-opus-4", "meta-llama/llama-3.3-70b-instruct"],
  slot_2_quant:          ["mistralai/magistral-medium", "mistralai/mistral-large-latest", "meta-llama/llama-3.3-70b-instruct"],
  slot_3_news:           ["x-ai/grok-3", "meta-llama/llama-3.3-70b-instruct"],
  slot_4_contrarian:     ["openai/gpt-4o", "qwen/qwen3-235b-a22b", "meta-llama/llama-3.3-70b-instruct"],
  slot_5_finance:        ["mistralai/mistral-large-latest", "openai/gpt-4o-mini", "meta-llama/llama-3.3-70b-instruct"],
  master:                ["anthropic/claude-opus-4", "anthropic/claude-sonnet-4-5", "meta-llama/llama-3.3-70b-instruct"],
};

const SLOT_LABELS: Record<string, string> = {
  slot_1_fundamentalist: "Fundamentalist",
  slot_2_quant:          "Quant",
  slot_3_news:           "News / Sentiment",
  slot_4_contrarian:     "Contrarian",
  slot_5_finance:        "Finance",
  master:                "Master (arbitrage)",
};

const SLOT_HINTS: Record<string, string> = {
  slot_1_fundamentalist: "Analyse fondamentale — via OpenRouter",
  slot_2_quant:          "Analyse quantitative — via OpenRouter",
  slot_3_news:           "Actualités & sentiment — via xAI (Grok natif) ou OpenRouter",
  slot_4_contrarian:     "Vision contrariante — via OpenRouter",
  slot_5_finance:        "Analyse financière macro — via OpenRouter",
  master:                "Arbitrage 3/2 — appelé uniquement si vote serré",
};

type AgentModelInfo = {
  name: string;
  model_current: string;
  model_default: string;
  customized: boolean;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsPayload | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [councilKeysStatus, setCouncilKeysStatus] = useState<CouncilKeysStatus | null>(null);
  const [councilKeyInputs, setCouncilKeyInputs] = useState<Record<string, string>>({});
  const [councilKeysMsg, setCouncilKeysMsg] = useState("");
  const [councilKeysErr, setCouncilKeysErr] = useState("");
  const [showCouncilKeys, setShowCouncilKeys] = useState<Record<string, boolean>>({});

  const [agentModels, setAgentModels] = useState<Record<string, AgentModelInfo>>({});
  const [modelInputs, setModelInputs] = useState<Record<string, string>>({});
  const [agentModelsMsg, setAgentModelsMsg] = useState("");
  const [agentModelsErr, setAgentModelsErr] = useState("");

  useEffect(() => {
    fetch(`${backendUrl}/api/settings`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((d) => setForm(d as SettingsPayload))
      .catch((e) => setError(String(e)));

    fetch(`${backendUrl}/api/council/v2/keys`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((d) => setCouncilKeysStatus(d as CouncilKeysStatus))
      .catch(() => {});

    fetch(`${backendUrl}/api/council/v2/agents`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((d) => setAgentModels(d as Record<string, AgentModelInfo>))
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

  const saveCouncilKeys = async () => {
    setCouncilKeysMsg("");
    setCouncilKeysErr("");
    try {
      const payload: Record<string, string> = {};
      for (const k of COUNCIL_KEYS) {
        if (councilKeyInputs[k.id] !== undefined) payload[k.id] = councilKeyInputs[k.id];
      }
      const r = await fetch(`${backendUrl}/api/council/v2/keys`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      setCouncilKeysStatus(await r.json() as CouncilKeysStatus);
      setCouncilKeyInputs({});
      setCouncilKeysMsg("Clés sauvegardées");
    } catch (e) {
      setCouncilKeysErr(String(e));
    }
  };

  const saveAgentModels = async () => {
    setAgentModelsMsg("");
    setAgentModelsErr("");
    try {
      const r = await fetch(`${backendUrl}/api/council/v2/agents`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ models: modelInputs }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
      setAgentModels(await r.json() as Record<string, AgentModelInfo>);
      setModelInputs({});
      setAgentModelsMsg("Modèles sauvegardés");
    } catch (e) {
      setAgentModelsErr(String(e));
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

      {/* ── Council v2 API Keys ── */}
      <section id="council-keys" style={{ marginBottom: "2.5rem" }}>
        <h2>Clés API — Council v2</h2>
        <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "1rem" }}>
          Stockées en base de données locale. Priorité : DB → variable d&apos;environnement → clé fictive.
        </p>

        <div style={{ display: "grid", gap: "0.75rem", maxWidth: "580px" }}>
          {COUNCIL_KEYS.map((k) => {
            const status  = councilKeysStatus?.[k.id];
            const isSet   = status?.set ?? false;
            const source  = status?.source ?? "none";
            const pending = councilKeyInputs[k.id] ?? "";
            const revealed = showCouncilKeys[k.id] ?? false;

            return (
              <div key={k.id} className="card card-accent" style={{ padding: "0.9rem 1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{k.label}</span>
                  <span className={`badge ${isSet || pending ? "badge-on" : "badge-off"}`} style={{ marginLeft: "auto" }}>
                    {isSet || pending ? `✓ Clé (${pending ? "en attente" : source})` : "Non configurée"}
                  </span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-dim)", marginBottom: "0.6rem" }}>
                  {k.hint}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <input
                    type={revealed ? "text" : "password"}
                    value={pending}
                    placeholder={isSet ? "••••••• (clé existante)" : k.placeholder}
                    style={{ flex: 1, fontSize: "0.8rem" }}
                    onChange={(e) => setCouncilKeyInputs({ ...councilKeyInputs, [k.id]: e.target.value })}
                  />
                  <button
                    type="button"
                    style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem" }}
                    onClick={() => setShowCouncilKeys({ ...showCouncilKeys, [k.id]: !revealed })}
                  >
                    {revealed ? "Masquer" : "Voir"}
                  </button>
                  {isSet && (
                    <button
                      type="button"
                      style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem", color: "var(--red)", borderColor: "var(--red)" }}
                      onClick={() => setCouncilKeyInputs({ ...councilKeyInputs, [k.id]: "" })}
                      title="Effacer la clé"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            );
          })}

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.25rem" }}>
            <button type="button" onClick={saveCouncilKeys}>Sauvegarder les clés</button>
            {councilKeysMsg && <span className="status-ok" style={{ fontSize: "0.8rem" }}>{councilKeysMsg}</span>}
            {councilKeysErr && <span className="status-ko" style={{ fontSize: "0.8rem" }}>{councilKeysErr}</span>}
          </div>
        </div>
      </section>

      {/* ── Agents Council v2 ── */}
      <section id="agents" style={{ marginBottom: "2.5rem" }}>
        <h2>Agents — Council v2</h2>
        <p style={{ color: "var(--text-dim)", fontSize: "0.8rem", marginBottom: "1rem" }}>
          Modèle IA de chaque agent. Sélectionnez dans la liste ou saisissez un identifiant OpenRouter.
          Laissez vide pour revenir au modèle par défaut.
        </p>

        <div style={{ display: "grid", gap: "0.75rem", maxWidth: "580px" }}>
          {Object.entries(SLOT_LABELS).map(([slot, label]) => {
            const info    = agentModels[slot];
            const current = modelInputs[slot] ?? info?.model_current ?? "";
            const isDefault = !info?.customized && !modelInputs[slot];

            return (
              <div key={slot} className="card card-accent" style={{ padding: "0.9rem 1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.4rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{label}</span>
                  {info?.customized && !modelInputs[slot] ? (
                    <span className="badge badge-on" style={{ marginLeft: "auto" }}>Personnalisé</span>
                  ) : (
                    <span className="badge badge-off" style={{ marginLeft: "auto" }}>Défaut</span>
                  )}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-dim)", marginBottom: "0.6rem" }}>
                  {SLOT_HINTS[slot]}
                  {isDefault && info && (
                    <span style={{ marginLeft: 6, color: "var(--green)" }}>({info.model_default})</span>
                  )}
                </div>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <input
                    list={`models-${slot}`}
                    value={current}
                    placeholder={info?.model_default ?? "provider/model-name"}
                    style={{ flex: 1, fontSize: "0.8rem" }}
                    onChange={(e) => setModelInputs({ ...modelInputs, [slot]: e.target.value })}
                  />
                  <datalist id={`models-${slot}`}>
                    {(SUGGESTED_MODELS[slot] ?? []).map((m) => (
                      <option key={m} value={m} />
                    ))}
                  </datalist>
                  {(modelInputs[slot] || info?.customized) && (
                    <button
                      type="button"
                      style={{ padding: "0.3rem 0.6rem", fontSize: "0.75rem", color: "var(--text-dim)", borderColor: "var(--border)" }}
                      onClick={() => {
                        setModelInputs({ ...modelInputs, [slot]: "" });
                      }}
                      title="Revenir au modèle par défaut"
                    >
                      ↺
                    </button>
                  )}
                </div>
              </div>
            );
          })}

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginTop: "0.25rem" }}>
            <button type="button" onClick={saveAgentModels}>Sauvegarder les modèles</button>
            {agentModelsMsg && <span className="status-ok" style={{ fontSize: "0.8rem" }}>{agentModelsMsg}</span>}
            {agentModelsErr && <span className="status-ko" style={{ fontSize: "0.8rem" }}>{agentModelsErr}</span>}
          </div>
        </div>
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
