import { Bot, Terminal } from "lucide-react";

import type { JarvisEvent } from "../lib/types";

function compactPayload(payload: Record<string, unknown>) {
  const text = JSON.stringify(payload);
  return text.length > 128 ? `${text.slice(0, 128)}...` : text;
}

export function ConsoleFeed({ events }: { events: JarvisEvent[] }) {
  const assistant = events.find((event) => event.type === "ai.response");
  const assistantText = typeof assistant?.payload.text === "string" ? assistant.payload.text : "Готов к команде.";

  return (
    <section className="panel console-panel">
      <div className="panel-title">
        <Terminal size={18} />
        <span>AI CONSOLE</span>
      </div>
      <div className="assistant-line">
        <Bot size={18} />
        <span>{assistantText}</span>
      </div>
      <div className="console-feed">
        {events.length === 0 ? (
          <div className="console-line muted">Awaiting signal...</div>
        ) : (
          events.map((event) => (
            <div className={`console-line ${event.category} ${event.level}`} key={event.id}>
              <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
              <b>{event.category}</b>
              <strong>{event.type}</strong>
              <span>{compactPayload(event.payload)}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
