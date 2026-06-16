import { useEffect, useMemo, useRef, useState } from "react";
import { WS_BASE, api, getToken } from "../api";
import type { Endpoint, EndpointMetrics } from "../types";
import EndpointCard from "../components/EndpointCard";

interface UIMessage {
  type: string;
  endpoint_id?: string;
  endpoint_ids?: string[];
  last_seen_at?: string;
  metrics?: EndpointMetrics;
}

export default function Dashboard() {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api<Endpoint[]>("/api/v1/endpoints");
        if (!cancelled) setEndpoints(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load endpoints");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;

    let stopped = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      if (stopped) return;
      const ws = new WebSocket(`${WS_BASE}/api/v1/ws?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as UIMessage;
          applyUIMessage(msg);
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        wsRef.current = null;
        if (!stopped) {
          reconnectTimer = window.setTimeout(connect, 2000);
        }
      };
      ws.onerror = () => ws.close();
    };

    const applyUIMessage = (msg: UIMessage) => {
      setEndpoints((prev) => {
        if (msg.type === "online.snapshot" && msg.endpoint_ids) {
          const online = new Set(msg.endpoint_ids);
          return prev.map((e) => ({ ...e, online: online.has(e.id) }));
        }
        if (!msg.endpoint_id) return prev;
        if (msg.type === "endpoint.online") {
          return prev.map((e) => (e.id === msg.endpoint_id ? { ...e, online: true } : e));
        }
        if (msg.type === "endpoint.offline") {
          return prev.map((e) => (e.id === msg.endpoint_id ? { ...e, online: false } : e));
        }
        if (msg.type === "endpoint.heartbeat") {
          return prev.map((e) =>
            e.id === msg.endpoint_id
              ? {
                  ...e,
                  online: true,
                  last_seen_at: msg.last_seen_at ?? e.last_seen_at,
                  latest_metrics: msg.metrics ?? e.latest_metrics,
                }
              : e,
          );
        }
        return prev;
      });
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return endpoints;
    return endpoints.filter((e) =>
      e.hostname.toLowerCase().includes(q) ||
      (e.os ?? "").toLowerCase().includes(q) ||
      (e.primary_ip ?? "").toLowerCase().includes(q) ||
      e.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [endpoints, query]);

  const onlineCount = endpoints.filter((e) => e.online).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Endpoints</h1>
          <div className="text-sm text-surface-100/60">
            {endpoints.length} total · {onlineCount} online
          </div>
        </div>
        <div className="w-full sm:w-80">
          <input
            className="input"
            placeholder="Search hostname, OS, IP, tag…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {loading && <div className="text-sm text-surface-100/60">Loading…</div>}
      {error && <div className="card p-4 text-sm text-red-400">{error}</div>}

      {!loading && !error && filtered.length === 0 && (
        <div className="card p-8 text-center">
          <div className="font-medium">No endpoints yet</div>
          <p className="text-sm text-surface-100/60 mt-1">
            Create an enrollment token, bake it into an installer, and run it on a machine to see it here.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {filtered.map((e) => <EndpointCard key={e.id} endpoint={e} />)}
      </div>
    </div>
  );
}
