"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { cn } from "cn";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import Logo from "@/components/Logo";
import { Input } from "@/components/ui/input";
import { api, ApiError, clearToken, setToken } from "@/lib/api";

function LoginForm({ className, ...props }: React.ComponentProps<"div">) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      const { token } = await api<{ token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(token);
      await api("/companies");
      router.replace("/home");
    } catch (err) {
      clearToken();
      setError(
        err instanceof ApiError && (err.status === 401 || err.status === 403)
          ? "Sign-in was not accepted."
          : "Could not reach the server. Check that the API is running.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-8", className)} {...props}>
      <Card className="gap-6 py-8 text-base [--card-spacing:--spacing(6)]">
        <CardHeader className="gap-2">
          <CardTitle className="text-2xl">Login to your account</CardTitle>
          <CardDescription className="text-base">
            Enter your email below to login to your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit}>
            <FieldGroup className="gap-6">
              <Field className="gap-2.5">
                <FieldLabel htmlFor="email" className="text-base">
                  Email
                </FieldLabel>
                <Input
                  id="email"
                  type="email"
                  placeholder="m@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  className="h-12 px-4 text-base md:text-base"
                />
              </Field>
              <Field className="gap-2.5">
                <div className="flex items-center">
                  <FieldLabel htmlFor="password" className="text-base">
                    Password
                  </FieldLabel>
                  <a
                    href="#"
                    className="ml-auto inline-block text-base underline-offset-4 hover:underline"
                  >
                    Forgot your password?
                  </a>
                </div>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="h-12 px-4 text-base md:text-base"
                />
              </Field>
              {error && (
                <Alert variant="destructive" role="alert">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Field className="gap-3">
                <Button
                  type="submit"
                  disabled={pending}
                  className="h-12 text-base"
                >
                  {pending ? "Signing in…" : "Login"}
                </Button>
                <FieldDescription className="text-center text-base">
                  Demo sign-in: any email and password works.
                </FieldDescription>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-svh w-full items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-lg space-y-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex size-16 items-center justify-center rounded-full bg-accent">
            <Logo label={false} className="p-2.5" />
          </div>
          <div className="text-3xl font-semibold tracking-tight">Lokibots</div>
          <div className="text-base text-muted-foreground">CHRO Copilot</div>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
