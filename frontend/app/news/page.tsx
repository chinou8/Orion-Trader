"use client";

import { useEffect, useState } from "react";

type RssFeed = {
  id: number;
  name: string;
  url: string;
  is_active: boolean;
};

type NewsItem = {
  id: number;
  title: string;
  link: string;
  published_at: string;
  feed_name: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function NewsPage() {
  const [feeds, setFeeds] = useState<RssFeed[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [status, setStatus] = useState("Loading...");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const [feedsRes, newsRes] = await Promise.all([
        fetch(`${backendUrl}/api/rss/feeds`, { cache: "no-store" }),
        fetch(`${backendUrl}/api/news?limit=50`, { cache: "no-store" })
      ]);
      if (!feedsRes.ok || !newsRes.ok) throw new Error("Failed to load news data");

      setFeeds((await feedsRes.json()) as RssFeed[]);
      setNews((await newsRes.json()) as NewsItem[]);
      setStatus("Loaded");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
      setStatus("Failed");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const fetchRss = async () => {
    try {
      setStatus("Fetching RSS...");
      const response = await fetch(`${backendUrl}/api/rss/fetch`, { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load();
      setStatus("Fetched");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fetch failed");
      setStatus("Failed");
    }
  };

  const toggleFeed = async (feed: RssFeed) => {
    try {
      const response = await fetch(`${backendUrl}/api/rss/feeds/${feed.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !feed.is_active })
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feed update failed");
    }
  };

  return (
    <main>
      <h1>Institutional News</h1>
      <p>
        Backend URL: <code>{backendUrl}</code>
      </p>
      <p>Status: {status}</p>

      <button type="button" onClick={fetchRss}>Fetch RSS</button>

      <section className="card">
        <h2>Feeds</h2>
        {feeds.map((feed) => (
          <div key={feed.id} className="feed-row">
            <div>
              <strong>{feed.name}</strong>
              <p>{feed.url}</p>
            </div>
            <button type="button" onClick={() => toggleFeed(feed)}>
              {feed.is_active ? "Disable" : "Enable"}
            </button>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Latest News</h2>
        {news.length === 0 ? (
          <p>No news yet.</p>
        ) : (
          <ul>
            {news.map((item) => (
              <li key={item.id}>
                <a href={item.link} target="_blank" rel="noreferrer">{item.title}</a>
                <div>
                  <small>{item.feed_name} · {item.published_at}</small>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
