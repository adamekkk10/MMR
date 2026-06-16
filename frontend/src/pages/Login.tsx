import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password, totp || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-full grid place-items-center p-4">
      <form onSubmit={onSubmit} className="card w-full max-w-sm p-6 flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-accent-600 grid place-items-center text-white font-bold">R</div>
          <div>
            <div className="font-semibold">RMM</div>
            <div className="text-xs text-surface-100/50">Sign in to your panel</div>
          </div>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-surface-100/70">Username</span>
          <input className="input" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-surface-100/70">Password</span>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs text-surface-100/70">TOTP code (if enabled)</span>
          <input className="input font-mono tracking-widest" inputMode="numeric" maxLength={6}
                 value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, ""))} />
        </label>

        {error && <div className="text-xs text-red-400">{error}</div>}

        <button className="btn-primary" disabled={submitting || !username || !password}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
