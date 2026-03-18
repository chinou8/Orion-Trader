"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

type RssFeed = { id: number; name: string; url: string; is_active: boolean };

// v1 news (RSS, sans scoring)
type NewsItemV1 = { id: number; title: string; link: string; published_at: string; feed_name: string };

// v2 news (scorées par le news_aggregator)
type NewsItemV2 = {
  id: number;
  source: string;
  title: string;
  url: string;
  published_at: string;
  impact_score: number;
  impact_level: "HIGH" | "MEDIUM" | "LOW";
  tickers_mentioned: string;   // JSON string
  category: string;
};

const IMPACT_COLORS: Record<string, string> = {
  HIGH:   "var(--red)",
  MEDIUM: "var(--yellow)",
  LOW:    "var(--text-dim)",
};

function ImpactBadge({ level }: { level: string }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 3,
      border: `1px solid ${IMPACT_COLORS[level] ?? "var(--border)"}`,
      color: IMPACT_COLORS[level] ?? "var(--text-dim)",
    }}>
      {level}
    </span>
  );
}

function parseTickers(raw: string): string[] {
  try { return JSON.parse(raw) as string[]; } catch { return []; }
}

export default function NewsPage() {
  const [feeds, setFeeds] = useState<RssFeed[]>([]);
  const [newsV1, setNewsV1] = useState<NewsItemV1[]>([]);
  const [newsV2, setNewsV2] = useState<NewsItemV2[]>([]);
  const [tab, setTab] = useState<"scored" | "rss">("scored");
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const [feedsRes, v1Res, v2Res] = await Promise.allSettled([
      fetch(`${API}/api/rss/feeds`, { cache: "no-store" }),
      fetch(`${API}/api/news?limit=50`, { cache: "no-store" }),
      fetch(`${API}/api/council/v2/news?limit=50`, { cache: "no-store" }),
    ]);
    if (feedsRes.status === "fulfilled" && feedsRes.value.ok)
      setFeeds(await feedsRes.value.json());
    if (v1Res.status === "fulfilled" && v1Res.value.ok)
      setNewsV1(await v1Res.value.json());
    if (v2Res.status === "fulfilled" && v2Res.value.ok) {
      const d = await v2Res.value.json();
      setNewsV2(d.high_impact_news ?? []);
    }
  };

  useEffect(() => { load(); }, []);

  const fetchRss = async () => {
    setFetching(true);
    setError("");
    try {
      const r = await fetch(`${API}/api/rss/fetch`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setFetching(false);
    }
  };

  const toggleFeed = async (feed: RssFeed) => {
    try {
      await fetch(`${API}/api/rss/feeds/${feed.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !feed.is_active }),
      });
      await load();
    } catch { /* ignore */ }
  };

  return (
    <main className="container">
      <div className="page-header">
        <h1 className="page-title">Actualités</h1>
        <p className="page-subtitle">Flux RSS + scoring d&apos;impact Council v2</p>
      </div>

      {/* ── Tabs + actions ── */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 20, flexWrap: "wrap" }}>
        <button
          className="btn"
          onClick={() => setTab("scored")}
          style={tab === "scored" ? {} : { background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)" }}
        >
          Scorées v2 {newsV2.length > 0 && `(${newsV2.length})`}
        </button>
        <button
          className="btn"
          onClick={() => setTab("rss")}
          style={tab === "rss" ? {} : { background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)" }}
        >
          Flux RSS {newsV1.length > 0 && `(${newsV1.length})`}
        </button>
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={fetchRss} disabled={fetching}>
          {fetching ? "⏳ Récupération…" : "↻ Rafraîchir RSS"}
        </button>
      </div>

      {error && <div style={{ color: "var(--red)", fontSize: 12, marginBottom: 12 }}>Erreur : {error}</div>}

      {/* ── Tab: Actualités scorées (v2) ── */}
      {tab === "scored" && (
        <div>
          {newsV2.length === 0 ? (
            <div className="card" style={{ textAlign: "center", color: "var(--text-dim)", padding: "40px 20px" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>📰</div>
              <div>Aucune actualité scorée pour l&apos;instant.</div>
              <div style={{ fontSize: 12, marginTop: 8 }}>Le scheduler v2 met à jour toutes les 5 min.</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {newsV2.map((item) => {
                const tickers = parseTickers(item.tickers_mentioned);
                return (
                  <div key={item.id} className="card" style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
                          <ImpactBadge level={item.impact_level} />
                          {item.category && (
                            <span style={{ fontSize: 10, color: "var(--text-dim)", border: "1px solid var(--border)", padding: "1px 5px", borderRadius: 3 }}>
                              {item.category}
                            </span>
                          )}
                          {tickers.map((t) => (
                            <span key={t} style={{ fontSize: 10, color: "var(--green)", border: "1px solid var(--border-bright)", padding: "1px 5px", borderRadius: 3 }}>
                              {t}
                            </span>
                          ))}
                        </div>
                        {item.url ? (
                          <a href={item.url} target="_blank" rel="noreferrer" style={{ fontSize: 13, lineHeight: 1.4 }}>
                            {item.title}
                          </a>
                        ) : (
                          <span style={{ fontSize: 13 }}>{item.title}</span>
                        )}
                        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4 }}>
                          {item.source} · {item.published_at}
                          <span style={{ marginLeft: 8, color: "var(--text-dim)" }}>score: {item.impact_score}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Flux RSS (v1) ── */}
      {tab === "rss" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Feeds management */}
          <div className="card">
            <div className="card-label">SOURCES RSS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
              {feeds.length === 0 && (
                <p style={{ color: "var(--text-dim)", fontSize: 13 }}>Aucun flux configuré.</p>
              )}
              {feeds.map((feed) => (
                <div key={feed.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className={`dot ${feed.is_active ? "dot-green" : "dot-gray"}`} />
                  <span style={{ flex: 1, fontSize: 13 }}>{feed.name}</span>
                  <span style={{ fontSize: 11, color: "var(--text-dim)", flex: 2 }}>{feed.url}</span>
                  <button
                    className="btn"
                    style={{ padding: "2px 10px", fontSize: 11, background: "transparent", border: `1px solid ${feed.is_active ? "var(--red)" : "var(--green)"}`, color: feed.is_active ? "var(--red)" : "var(--green)" }}
                    onClick={() => toggleFeed(feed)}
                  >
                    {feed.is_active ? "Désactiver" : "Activer"}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* V1 news list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {newsV1.length === 0 ? (
              <div className="card" style={{ textAlign: "center", color: "var(--text-dim)", padding: "30px 20px" }}>
                Aucune news RSS. Cliquez sur Rafraîchir.
              </div>
            ) : (
              newsV1.map((item) => (
                <div key={item.id} className="card" style={{ padding: "10px 14px" }}>
                  <div style={{ fontSize: 11, color: "var(--text-dim)", marginBottom: 4 }}>
                    {item.feed_name} · {item.published_at}
                  </div>
                  <a href={item.link} target="_blank" rel="noreferrer" style={{ fontSize: 13 }}>
                    {item.title}
                  </a>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </main>
  );
}
