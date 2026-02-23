export default function DashboardPage() {
  return (
    <main>
      <h1>Orion Trader Dashboard</h1>
      <p>
        Minimal frontend scaffold. Backend status page: <a href="/status">/status</a>
      </p>

      <div className="grid">
        <section className="card">
          <h2>Equity Curve</h2>
          <p>Placeholder: chart area for account equity over time.</p>
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
      </div>
    </main>
  );
}
