export interface User {
  id: string;
  username: string;
  role: "admin" | "operator" | "readonly";
  totp_enabled: boolean;
}

export interface EndpointMetrics {
  cpu_percent?: number;
  mem_percent?: number;
  disk_percent?: number;
  mem_total?: number;
  mem_used?: number;
  loadavg?: [number | null, number | null, number | null];
  uptime_seconds?: number;
  observed_at?: number;
}

export interface Endpoint {
  id: string;
  hostname: string;
  os: string | null;
  os_version: string | null;
  arch: string | null;
  agent_version: string | null;
  primary_ip: string | null;
  tags: string[];
  notes: string | null;
  last_seen_at: string | null;
  enrolled_at: string;
  latest_metrics: EndpointMetrics | null;
  online: boolean;
}
