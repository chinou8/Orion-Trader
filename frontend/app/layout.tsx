"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import "./globals.css";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/committee", label: "Committee" },
  { href: "/council", label: "Council v2" },
  { href: "/proposals", label: "Proposals" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/market", label: "Market" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/news", label: "News" },
  { href: "/chat", label: "Chat" },
  { href: "/settings", label: "Settings" },
];

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [mode, setMode] = useState<string>("");

  useEffect(() => {
    fetch(`${backendUrl}/api/execution/status`, { cache: "no-store" })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setMode(d.mode ?? ""))
      .catch(() => {});
  }, []);

  return (
    <html lang="fr">
      <head>
        <title>Orion Trader</title>
        <meta name="description" content="Autonomous AI trading committee dashboard" />
      </head>
      <body>
        <nav className="nav">
          <a href="/" className="nav-brand">⬡ ORION</a>
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className={`nav-link${pathname === link.href ? " active" : ""}`}
            >
              {link.label}
            </a>
          ))}
          <span className="nav-spacer" />
          {mode && <span className="nav-mode">{mode}</span>}
        </nav>
        {children}
      </body>
    </html>
  );
}
