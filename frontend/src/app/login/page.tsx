"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, setToken } from "@/lib/api";

// Interim sign-in: paste a JWT issued by the backend. Replace with OIDC/SSO (Phase 0).
export default function Login() {
  const [token, setTok] = useState("");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setToken(token.trim());
    try {
      await api("/companies");
      router.replace("/");
    } catch (err) {
      localStorage.removeItem("chro_token");
      // A rejected token and an unreachable server need different fixes, so say which it is.
      setError(err instanceof ApiError && (err.status === 401 || err.status === 403)
        ? "That token was not accepted."
        : "Could not reach the server. Check that the API is running and that its CORS settings allow this site.");
    }
  }

  return (
    <div className="mx-auto mt-32 max-w-md rounded-lg border border-slate-200 bg-white p-6">
      <h1 className="text-xl font-semibold">Sign in</h1>
      <form onSubmit={submit} className="mt-4 space-y-3">
        <label className="block text-sm" htmlFor="token">Access token</label>
        <textarea id="token" value={token} onChange={(e) => setTok(e.target.value)} rows={4}
          className="w-full rounded border border-slate-300 p-2 font-mono text-xs" required />
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <button className="rounded bg-slate-900 px-4 py-2 text-sm text-white">Continue</button>
      </form>
    </div>
  );
}
