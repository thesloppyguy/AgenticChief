"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
    <Card className="mx-auto mt-32 max-w-md">
      <CardHeader><CardTitle className="text-xl"><h1>Sign in</h1></CardTitle></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <Label htmlFor="token">Access token</Label>
          <Textarea id="token" value={token} onChange={(e) => setTok(e.target.value)} rows={4}
            className="font-mono text-xs" required />
          {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
          <Button type="submit">Continue</Button>
        </form>
      </CardContent>
    </Card>
  );
}
