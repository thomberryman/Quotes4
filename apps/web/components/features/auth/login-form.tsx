"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { ApiClientError } from "@quotes4/contracts";

import { createBrowserSession } from "@/lib/api/auth";
import { validateLoginCredentials } from "@/lib/forms/validation";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { SectionCard } from "@/components/ui/section-card";
import { TextInput } from "@/components/forms/text-input";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@quotes4.dev");
  const [password, setPassword] = useState("quotes4-admin-password");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const validationError = validateLoginCredentials(email, password);

  return (
    <SectionCard
      title="Login"
      description="Use your Quotes4 account to access quotes, projects, forecasts, and historical comparisons."
    >
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const validationError = validateLoginCredentials(email, password);
          if (validationError) {
            setError(validationError);
            return;
          }

          setError(null);

          startTransition(() => {
            void createBrowserSession({
              email: email.trim(),
              password
            })
              .then(() => {
                router.replace("/dashboard");
                router.refresh();
              })
              .catch((caughtError: unknown) => {
                if (caughtError instanceof ApiClientError) {
                  setError(caughtError.message);
                  return;
                }

                setError("Login failed. Check the API and try again.");
              });
          });
        }}
      >
        {error ? <ErrorState description={error} title="Authentication failed" /> : null}
        <div className="grid gap-4 md:grid-cols-2">
          <TextInput
            autoComplete="email"
            label="Email"
            onChange={(event) => setEmail(event.target.value)}
            required
            value={email}
          />
          <TextInput
            autoComplete="current-password"
            label="Password"
            minLength={12}
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          The local demo account uses <code>admin@quotes4.dev</code> with password{" "}
          <code>quotes4-admin-password</code>.
        </div>
        <div className="flex flex-wrap gap-2">
          <Button disabled={Boolean(isPending || validationError)} type="submit" variant="primary">
            {isPending ? "Signing in..." : "Sign in"}
          </Button>
        </div>
      </form>
    </SectionCard>
  );
}
