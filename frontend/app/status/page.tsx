type HealthResponse = { status: string };

function getBackendUrl(): string {
  return process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";
}

export default async function StatusPage() {
  const backendUrl = getBackendUrl();
  const endpoint = `${backendUrl}/health`;

  let isOk = false;
  let payload: HealthResponse | { error: string } | null = null;

  try {
    const response = await fetch(endpoint, { cache: "no-store" });
    if (response.ok) {
      payload = (await response.json()) as HealthResponse;
      isOk = true;
    } else {
      payload = { error: `HTTP ${response.status}` };
    }
  } catch (error) {
    payload = { error: error instanceof Error ? error.message : "Unknown error" };
  }

  return (
    <main>
      <h1>Backend Status</h1>
      <p>
        Endpoint: <code>{endpoint}</code>
      </p>
      <p>
        Backend: <strong className={isOk ? "status-ok" : "status-ko"}>{isOk ? "OK" : "KO"}</strong>
      </p>

      {payload && (
        <>
          <h2>Response</h2>
          <pre>{JSON.stringify(payload, null, 2)}</pre>
        </>
      )}
    </main>
  );
}
