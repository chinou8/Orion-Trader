"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type ChatMessage = {
  id: number;
  thread_id: number;
  role: "user" | "orion";
  content: string;
  created_at: string;
};

type OrionReply = {
  reply_text: string;
  recommendations: string[];
  watch_requests: string[];
  meta: { mode: string; timestamp: string };
};

type ChatThreadResponse = {
  thread_id: number;
  title: string;
  messages: ChatMessage[];
};

type ChatSendResponse = {
  thread_id: number;
  user_message: ChatMessage;
  orion_message: ChatMessage;
  orion_reply: OrionReply;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8080";

export default function ChatPage() {
  const [threadId, setThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState<string>("");
  const [status, setStatus] = useState<string>("Initializing thread...");
  const [error, setError] = useState<string>("");
  const [watchRequests, setWatchRequests] = useState<string[]>([]);

  useEffect(() => {
    const initThread = async () => {
      try {
        const createResponse = await fetch(`${backendUrl}/api/chat/thread`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "Orion Chat" })
        });
        if (!createResponse.ok) {
          throw new Error(`HTTP ${createResponse.status}`);
        }

        const created = (await createResponse.json()) as { thread_id: number };
        setThreadId(created.thread_id);

        const threadResponse = await fetch(`${backendUrl}/api/chat/thread/${created.thread_id}`);
        if (!threadResponse.ok) {
          throw new Error(`HTTP ${threadResponse.status}`);
        }

        const thread = (await threadResponse.json()) as ChatThreadResponse;
        setMessages(thread.messages);
        setStatus("Thread ready");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to initialize chat thread");
        setStatus("Failed");
      }
    };

    initThread();
  }, []);

  const parsedMessages = useMemo(
    () =>
      messages.map((message) => {
        if (message.role !== "orion") {
          return { ...message, display: message.content };
        }

        try {
          const payload = JSON.parse(message.content) as OrionReply;
          return { ...message, display: payload.reply_text };
        } catch {
          return { ...message, display: message.content };
        }
      }),
    [messages]
  );

  const onSend = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!threadId || !text.trim()) {
      return;
    }

    try {
      const response = await fetch(`${backendUrl}/api/chat/thread/${threadId}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text.trim() })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = (await response.json()) as ChatSendResponse;
      setMessages((prev) => [...prev, payload.user_message, payload.orion_message]);
      setWatchRequests(payload.orion_reply.watch_requests);
      setText("");
      setStatus("Saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    }
  };

  return (
    <main>
      <h1>Chat Orion</h1>
      <p>
        Backend URL: <code>{backendUrl}</code>
      </p>
      <p>Status: {status}</p>

      <div className="chat-box">
        {parsedMessages.length === 0 ? (
          <p>No messages yet.</p>
        ) : (
          parsedMessages.map((message) => (
            <div key={message.id} className={`chat-message chat-${message.role}`}>
              <strong>{message.role === "user" ? "You" : "Orion"}</strong>
              <p>{message.display}</p>
            </div>
          ))
        )}
      </div>

      <form onSubmit={onSend} className="chat-form">
        <input
          type="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Ask Orion..."
        />
        <button type="submit">Send</button>
      </form>

      {watchRequests.length > 0 && (
        <section className="card">
          <h2>Watchlist requests</h2>
          <ul>
            {watchRequests.map((item, idx) => (
              <li key={`${item}-${idx}`}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {error && <p className="status-ko">Error: {error}</p>}
    </main>
  );
}
