"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BarChart3, LogIn, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, setAccessToken } from "@/lib/api";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(10, "Password must be at least 10 characters")
});

type LoginForm = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const form = useForm<LoginForm>({
    resolver: zodResolver(schema),
    defaultValues: {email: "", password: ""}
  });

  async function onSubmit(values: LoginForm) {
    try {
      if (mode === "register") {
        await apiFetch("/auth/register", {
          method: "POST",
          body: JSON.stringify(values)
        });
      }
      const token = await apiFetch<{access_token: string}>("/auth/login", {
        method: "POST",
        body: JSON.stringify(values)
      });
      setAccessToken(token.access_token);
      toast.success(mode === "register" ? "Account created" : "Signed in");
      router.push("/dashboard");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : mode === "register" ? "Registration failed" : "Login failed");
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            <CardTitle className="text-base text-foreground">{mode === "register" ? "Create Operator" : "Copy Trading"}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3" onSubmit={form.handleSubmit(onSubmit)}>
            <label className="grid gap-1.5">
              <Input type="email" placeholder="Email" autoComplete="email" {...form.register("email")} />
              {form.formState.errors.email ? (
                <span className="text-xs text-destructive">{form.formState.errors.email.message}</span>
              ) : null}
            </label>
            <label className="grid gap-1.5">
              <Input
                type="password"
                placeholder="Password"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                {...form.register("password")}
              />
              {form.formState.errors.password ? (
                <span className="text-xs text-destructive">{form.formState.errors.password.message}</span>
              ) : null}
            </label>
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {mode === "register" ? <UserPlus className="h-4 w-4" /> : <LogIn className="h-4 w-4" />}
              {form.formState.isSubmitting ? "Working..." : mode === "register" ? "Create and sign in" : "Sign in"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              disabled={form.formState.isSubmitting}
              onClick={() => setMode(mode === "register" ? "login" : "register")}
            >
              {mode === "register" ? "Use existing account" : "Create account"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
