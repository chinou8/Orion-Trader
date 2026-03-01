"use client";

import { useEffect, useMemo, useState } from "react";

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

type Proposal = {
  id: number;
  symbol: string;
  side: string;
  status: string;
};

type PortfolioState = {
  cash_eur: number;
  equity_eur: number;
  unrealized_pnl_eur: number;
  realized_pnl_eur: number;
};

type EquityCurvePoint = {
  ts: string;
  equity_eur: number;
  cash_eur: number;
  realized_pnl_eur: number;
  unrealized_pnl_eur: number;
};

type PerformanceSummary = {
  current_equity_eur: number;
  performance_since_start_pct: number;
  trades_count: number;
  pnl_total_eur: number;
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

function polylinePoints(values: number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function DashboardPage() {
  const [watchlistTop, setWatchlistTop] = useState<WatchlistItem[]>([]);
  const [newsTop, setNewsTop] = useState<NewsItem[]>([]);
  const [marketTop, setMarketTop] = useState<MarketIndicators[]>([]);
  const [pendingProposals, setPendingProposals] = useState<Proposal[]>([]);
  const [portfolioState, setPortfolioState] = useState<PortfolioState | null>(null);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [performanceSummary, setPerformanceSummary] = useState<PerformanceSummary | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [watchlistRes, newsRes, proposalsRes, portfolioRes, curveRes, perfRes] = await Promise.all([
          fetch(`${backendUrl}/api/watchlist`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/news?limit=5`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/proposals?status=PENDING&limit=5`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/portfolio`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/portfolio/equity_curve?limit=120`, { cache: "no-store" }),
          fetch(`${backendUrl}/api/portfolio/performance_summary`, { cache: "no-store" })
        ]);

        let watchlistPayload: WatchlistItem[] = [];
        if (watchlistRes.ok) {
          watchlistPayload = (await watchlistRes.json()) as WatchlistItem[];
          setWatchlistTop(watchlistPayload.slice(0, 5));
        }

        if (newsRes.ok) {
          const newsPayload = (await newsRes.json()) as NewsItem[];
          setNewsTop(newsPayload.slice(0, 5));
        }

        if (proposalsRes.ok) {
          const proposalsPayload = (await proposalsRes.json()) as Proposal[];
          setPendingProposals(proposalsPayload.slice(0, 5));
        }

        if (portfolioRes.ok) {
          const portfolioPayload = (await portfolioRes.json()) as { state: PortfolioState };
          setPortfolioState(portfolioPayload.state);
        }

        if (curveRes.ok) {
          setEquityCurve((await curveRes.json()) as EquityCurvePoint[]);
        }

        if (perfRes.ok) {
          setPerformanceSummary((await perfRes.json()) as PerformanceSummary);
        }

        const topSymbols = watchlistPayload.slice(0, 3).map((item) => item.symbol);
        const indicatorResponses = await Promise.all(
          topSymbols.map(async (symbol) => {
            const res = await fetch(
              `${backendUrl}/api/market/indicators?symbol=${encodeURIComponent(symbol)}`,
              { cache: "no-store" }
            );
            if (!res.ok) return null;
            return (await res.json()) as MarketIndicators;
          })
        );
        setMarketTop(indicatorResponses.filter((x): x is MarketIndicators => x !== null));
      } catch {
        setWatchlistTop([]);
        setNewsTop([]);
        setMarketTop([]);
        setPendingProposals([]);
        setPortfolioState(null);
        setEquityCurve([]);
        setPerformanceSummary(null);
      }
    };

    loadData();
  }, []);

  const equityPolyline = useMemo(
    () => polylinePoints(equityCurve.map((point) => point.equity_eur), 320, 120),
    [equityCurve]
  );

  return (
    <main>
      <h1>Orion Trader Dashboard</h1>
      <p>
        Minimal frontend scaffold. Backend status page: <a href="/status">/status</a> · Settings: <a href="/settings">/settings</a> · Chat: <a href="/chat">/chat</a> · Watchlist: <a href="/watchlist">/watchlist</a> · News: <a href="/news">/news</a> · Market: <a href="/market">/market</a> · Proposals: <a href="/proposals">/proposals</a> · Portfolio: <a href="/portfolio">/portfolio</a>
      </p>

      <div className="grid">
        <section className="card">
          <h2>Equity Curve</h2>
          {equityCurve.length < 1 ? (
            <p>No equity points yet.</p>
          ) : (
            <>
              <svg viewBox="0 0 320 120" width="100%" height="120" role="img" aria-label="Equity curve">
                <polyline fill="none" stroke="#38bdf8" strokeWidth="2" points={equityPolyline} />
              </svg>
              <p>Last equity: {equityCurve[equityCurve.length - 1].equity_eur.toFixed(2)} EUR</p>
            </>
          )}
          {performanceSummary ? (
            <ul>
              <li>Perf since start: {performanceSummary.performance_since_start_pct.toFixed(2)}%</li>
              <li>Trades: {performanceSummary.trades_count}</li>
              <li>Total PnL: {performanceSummary.pnl_total_eur.toFixed(2)} EUR</li>
            </ul>
          ) : null}
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

        <section className="card">
          <h2>Pending Proposals</h2>
          {pendingProposals.length === 0 ? (
            <p>No pending proposals.</p>
          ) : (
            <ul>
              {pendingProposals.map((item) => (
                <li key={item.id}>
                  <strong>#{item.id}</strong> {item.symbol} — {item.side}
                </li>
              ))}
            </ul>
          )}
          <p><a href="/proposals">Open proposals</a></p>
        </section>

        <section className="card">
          <h2>Portfolio Snapshot</h2>
          {portfolioState ? (
            <ul>
              <li>Cash: {portfolioState.cash_eur}</li>
              <li>Equity: {portfolioState.equity_eur}</li>
              <li>uPnL: {portfolioState.unrealized_pnl_eur}</li>
              <li>rPnL: {portfolioState.realized_pnl_eur}</li>
            </ul>
          ) : (
            <p>No portfolio state.</p>
          )}
          <p><a href="/portfolio">Open portfolio</a></p>
        </section>

        <section className="card">
          <h2>Market Snapshot</h2>
          {marketTop.length === 0 ? (
            <p>No market snapshot yet.</p>
          ) : (
            <ul>
              {marketTop.map((item) => (
                <li key={item.symbol}>
                  <strong>{item.symbol}</strong> — RSI {item.rsi14 ?? "n/a"} — Trend {item.sma20 && item.sma50 && item.sma20 > item.sma50 ? "SMA20>SMA50" : "SMA20<=SMA50"}
                </li>
              ))}
            </ul>
          )}
          <p><a href="/market">Open market module</a></p>
        </section>
      </div>
    </main>
  );
}
