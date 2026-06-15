"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Zap, Loader2, LogIn } from "lucide-react";
import { login, register, isAuthenticated } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated()) {
      router.push("/");
    }
  }, [router]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDemo() {
    setDemoLoading(true);
    setError(null);
    const demoEmail = "demo@xeno.ai";
    const demoPass = "demo1234";
    try {
      try {
        await register(demoEmail, demoPass, "Demo User");
      } catch {
        // Account may already exist
      }
      await login(demoEmail, demoPass);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demo login failed");
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-brand-icon">
            <Zap />
          </div>
          <h1>Xeno AI</h1>
          <p>Campaign Copilot — AI-native CRM</p>
        </div>

        <form className="login-form" onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </div>

          {error && <p className="error-box">{error}</p>}

          <button type="submit" className="btn-primary" disabled={loading} style={{ width: "100%" }}>
            {loading ? <Loader2 className="spin" /> : <LogIn />}
            Sign in
          </button>

          <div className="login-divider">
            <span>or</span>
          </div>

          <button
            type="button"
            onClick={handleDemo}
            disabled={demoLoading}
            style={{ width: "100%" }}
          >
            {demoLoading ? <Loader2 className="spin" /> : <Zap />}
            Try Demo Mode
          </button>
        </form>
      </div>
    </div>
  );
}
