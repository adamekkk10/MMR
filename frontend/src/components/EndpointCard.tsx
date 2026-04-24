import type { Endpoint } from "../types";

function formatLastSeen(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function Bar({ label, value }: { label: string; value: number | null | undefined }) {
  const v = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const color =
    v == null ? "bg-surface-800"
      : v > 85 ? "bg-red-500"
      : v > 65 ? "bg-amber-400"
      : "bg-accent-500";
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="text-surface-100/60">{label}</span>
        <span className="font-mono tabular-nums">{v == null ? "—" : `${v.toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-800 overflow-hidden">
        <div
          className={`h-full ${color} transition-all`}
          style={{ width: `${v ?? 0}%` }}
        />
      </div>
    </div>
  );
}

export default function EndpointCard({ endpoint }: { endpoint: Endpoint }) {
  const m = endpoint.latest_metrics;
  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${endpoint.online ? "bg-emerald-400" : "bg-surface-100/30"}`}
              title={endpoint.online ? "online" : "offline"}
            />
            <h3 className="font-semibold truncate">{endpoint.hostname}</h3>
          </div>
          <div className="text-xs text-surface-100/50 truncate">
            {endpoint.os ?? "unknown OS"}
            {endpoint.os_version ? ` · ${endpoint.os_version}` : ""}
            {endpoint.primary_ip ? ` · ${endpoint.primary_ip}` : ""}
          </div>
        </div>
        <div className="text-xs text-surface-100/60 whitespace-nowrap">
          {formatLastSeen(endpoint.last_seen_at)}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Bar label="CPU" value={m?.cpu_percent} />
        <Bar label="Memory" value={m?.mem_percent} />
        <Bar label="Disk" value={m?.disk_percent} />
      </div>

      {endpoint.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {endpoint.tags.map((t) => (
            <span key={t} className="badge bg-surface-800 text-surface-100/80">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}
