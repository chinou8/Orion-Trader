import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Orion Trader Dashboard",
  description: "Minimal dashboard and backend status for Orion Trader."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
