"use client";

import { useEffect, useState } from "react";

type AgentVote = {
  agent: "claude" | "gpt4o" | "grok";
  action: "BUY" | "SELL" | "HOLD";
  ticker: string;
  notional_eur: number | null;
  reasoning: string;
  confidence: number;
};

type CommitteeRun = {
  id: number;
  run_at: string;
  votes_round1: AgentVote[];
  votes_round2: AgentVote[];
  winning_action: string | null;
  winning_ticker: string | null;
  winning_notional_eur: number | null;
  proposal_id: number | null;
  error: string | null;
};

type AgentConfigResponse = {
  claude_enabled: boolean;
  gpt4o_enabled: boolean;
  grok_enabled: boolean;
  anthropic_key_set: boolean;
  openai_key_set: boolean;
  xai_key_set: boolean;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

const AGENT_LABELS: Record<string, string> = {
  claude: "Claude",
  gpt4o: "GPT-4o",
  grok: "Grok",
};

function agentEnabled(agent: string, cfg: AgentConfigResponse | null): boolean {
  if (!cfg) return true;
  if (agent === "claude") return cfg.claude_enabled;
  if (agent === "gpt4o") return cfg.gpt4o_enabled;
  if (agent === "grok") return cfg.grok_enabled;
  return true;
}

function VoteCard({ vote, cfg }: { vote: AgentVote; cfg: AgentConfigResponse | null }) {
  const enabled = agentEnabled(vote.agent, cfg);
  const actionClass = vote.action.toLowerCase();
  return (
    <div className={`agent-card ${enabled ? "enabled" : "disabled"}`}>
      <div className="agent-name">{AGENT_LABELS[vote.agent] ?? vote.agent}</div>
      <div className={`agent-action ${actionClass}`}>{vote.action}</div>
      {vote.ticker && <div className="agent-ticker">{vote.ticker}{vote.notional_eur ? ` · ${vote.notional_eur.toFixed(0)} €` : ""}</div>}
      <div className="agent-reasoning">{vote.reasoning}</div>
      <div className="confidence-bar">
        <div className="confidence-fill" style={{ width: `${vote.confidence * 100}%` }} />
      </div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", marginTop: "0.3rem" }}>
        Confidence {(vote.confidence * 100).toFixed(0)}%
      </div>
    </div>
  );
}

function RunCard({ run, cfg }: { run: CommitteeRun; cfg: AgentConfigResponse | null }) {
  const [open, setOpen] = useState(false);
  const actionClass = (run.winning_action ?? "hold").toLowerCase();
  const date = new Date(run.run_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

  return (
    <div className="card" style={{ marginBottom: "0.75rem", cursor: "pointer" }} onClick={() => setOpen((v) => !v)}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <span className={`badge badge-${actionClass}`}>{run.winning_action ?? "HOLD"}</span>
        {run.winning_ticker && <strong style={{ fontSize: "0.9rem" }}>{run.winning_ticker}</strong>}
        {run.winning_notional_eur && <span style={{ color: "var(--text-dim)", fontSize: "0.8rem" }}>{run.winning_notional_eur.toFixed(0)} €</span>}
        <span style={{ marginLeft: "auto", fontSize: "0.75rem", color: "var(--text-dim)" }}>#{run.id} · {date}</span>
        {run.proposal_id && <span className="badge badge-pending">→ Prop #{run.proposal_id}</span>}
        <span style={{ color: "var(--text-dim)", fontSize: "0.8rem" }}>{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ marginTop: "1rem" }}>
          <p style={{ color: "var(--text-dim)", fontSize: "0.75rem", marginBottom: "0.5rem" }}>ROUND 1 — Initial votes</p>
          <div className="agent-grid">
            {run.votes_round1.map((v) => <VoteCard key={v.agent} vote={v} cfg={cfg} />)}
          </div>
          <p style={{ color: "var(--text-dim)", fontSize: "0.75rem", margin: "0.75rem 0 0.5rem" }}>ROUND 2 — After debate</p>
          <div className="agent-grid">
            {run.votes_round2.map((v) => <VoteCard key={v.agent} vote={v} cfg={cfg} />)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function CommitteePage() {
  const [cfg, setCfg] = useState<AgentConfigResponse | null>(null);
  const [runs, setRuns] = useState<CommitteeRun[]>([]);
  const [latestRun, setLatestRun] = useState<CommitteeRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadConfig = async () => {
    const r = await fetch(`${backendUrl}/api/agents/config`, { cache: "no-store" });
    if (r.ok) setCfg(await r.json());
  };

  const loadRuns = async () => {
    const r = await fetch(`${backendUrl}/api/committee/runs?limit=20`, { cache: "no-store" });
    if (r.ok) {
      const data: CommitteeRun[] = await r.json();
      setRuns(data);
      if (data.length > 0) setLatestRun(data[0]);
    }
  };

  useEffect(() => {
    loadConfig();
    loadRuns();
  }, []);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const r = await fetch(`${backendUrl}/api/committee/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail ?? "Erreur lors du run");
      } else {
        const run: CommitteeRun = await r.json();
        setLatestRun(run);
        setRuns((prev) => [run, ...prev.slice(0, 19)]);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const activeAgents = cfg
    ? [cfg.claude_enabled && "Claude", cfg.gpt4o_enabled && "GPT-4o", cfg.grok_enabled && "Grok"]
        .filter(Boolean)
        .join(" · ")
    : "…";

  const actionClass = (latestRun?.winning_action ?? "hold").toLowerCase();

  return (
    <main>
      <h1>AI Committee</h1>

      {/* ── Status bar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-dim)" }}>
          Agents actifs : <span style={{ color: "var(--green)" }}>{activeAgents || "aucun"}</span>
        </div>
        <a href="/settings#agents" style={{ fontSize: "0.75rem" }}>Configurer →</a>
        <span style={{ flex: 1 }} />
        <button className="btn-run" onClick={handleRun} disabled={running}>
          {running ? "⏳ Analyse en cours…" : "▶ Lancer le comité"}
        </button>
      </div>

      {error && <p className="status-ko" style={{ marginBottom: "1rem" }}>⚠ {error}</p>}

      {/* ── Latest run result ── */}
      {latestRun && (
        <>
          <div className="committee-result">
            <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
              Décision du comité #{latestRun.id}
            </div>
            <div className={`committee-action ${actionClass}`}>{latestRun.winning_action ?? "HOLD"}</div>
            {latestRun.winning_ticker && (
              <div style={{ fontSize: "1.1rem", color: "var(--text)", fontWeight: 600 }}>
                {latestRun.winning_ticker}
                {latestRun.winning_notional_eur && <span style={{ color: "var(--text-dim)", fontWeight: 400 }}> · {latestRun.winning_notional_eur.toFixed(0)} €</span>}
              </div>
            )}
            {latestRun.proposal_id && (
              <div style={{ marginTop: "0.5rem" }}>
                <a href="/proposals" className="badge badge-pending">→ Proposition #{latestRun.proposal_id} créée</a>
              </div>
            )}
          </div>

          {/* Round 1 */}
          <h2 style={{ marginBottom: "0.5rem" }}>Round 1 — Analyse indépendante</h2>
          <div className="agent-grid" style={{ marginBottom: "1.25rem" }}>
            {latestRun.votes_round1.map((v) => (
              <VoteCard key={v.agent} vote={v} cfg={cfg} />
            ))}
          </div>

          {/* Round 2 */}
          <h2 style={{ marginBottom: "0.5rem" }}>Round 2 — Après débat</h2>
          <div className="agent-grid" style={{ marginBottom: "1.5rem" }}>
            {latestRun.votes_round2.map((v) => (
              <VoteCard key={v.agent} vote={v} cfg={cfg} />
            ))}
          </div>
        </>
      )}

      {/* ── History ── */}
      {runs.length > 1 && (
        <>
          <h2>Historique</h2>
          {runs.slice(1).map((run) => (
            <RunCard key={run.id} run={run} cfg={cfg} />
          ))}
        </>
      )}

      {!latestRun && !running && (
        <div className="card" style={{ textAlign: "center", color: "var(--text-dim)", padding: "2rem" }}>
          Aucun run. Cliquez sur <strong>Lancer le comité</strong> pour démarrer l'analyse.
        </div>
      )}
    </main>
  );
}
