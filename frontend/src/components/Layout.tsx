import { Outlet } from "react-router-dom";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-10 border-b border-surface-800 bg-surface-950/80 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-7 w-7 rounded-md bg-accent-600 grid place-items-center text-white text-sm font-bold">R</div>
            <div className="font-semibold">RMM</div>
            <div className="text-surface-100/50 text-xs hidden sm:block">self-hosted fleet management</div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-surface-100/60">
              {user?.username}
              <span className="ml-2 badge bg-surface-900 border border-surface-800 text-surface-100/70">
                {user?.role}
              </span>
            </span>
            <button className="btn-ghost" onClick={logout}>Sign out</button>
          </div>
        </div>
      </header>
      <main className="flex-1 mx-auto max-w-7xl w-full px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
