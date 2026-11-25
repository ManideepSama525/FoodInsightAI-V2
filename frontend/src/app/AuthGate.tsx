"use client";
import Link from "next/link";

import { FormEvent, useEffect, useState } from "react";
import { Activity, ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole, Mail, ShieldCheck, UserRound } from "lucide-react";
import { api, session, type User } from "@/lib/api";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const token = session.getToken();

    if (!token) {
      setChecking(false);
      return;
    }

    api.me()
      .then((current) => {
        if (active) setUser(current);
      })
      .catch(() => {
        session.clear();
      })
      .finally(() => {
        if (active) setChecking(false);
      });

    const handleUnauthorized = () => {
      session.clear();
      setUser(null);
    };
    window.addEventListener("foodinsightai:unauthorized", handleUnauthorized);

    return () => {
      active = false;
      window.removeEventListener("foodinsightai:unauthorized", handleUnauthorized);
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);

    try {
      if (mode === "register") {
        await api.register({ display_name: name, email, password });
      }
      const result = await api.login({ email, password });
      session.setToken(result.access_token);
      setUser(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    session.clear();
    setUser(null);
    setPassword("");
    setMode("login");
  }

  if (checking) {
    return (
      <main className="auth-loading">
        <div className="auth-brand-mark">F</div>
        <LoaderCircle className="spin" size={22} />
        <span>Restoring your workspace</span>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="auth-screen">
        <section className="auth-story">
          <Link className="auth-brand" href="/">
            <span className="auth-brand-mark">F</span>
            <span>FoodInsight<span>AI</span></span>
          </Link>
          <div className="auth-story-content">
            <p className="eyebrow">A MORE INFORMED WAY TO EAT</p>
            <h1>Understand<br />what&apos;s on <em>your plate.</em></h1>
            <p>Food composition, meal tracking and practical nutrition insights in one considered workspace.</p>
            <div className="auth-proof">
              <span><ShieldCheck size={17} /> Source-aware food data</span>
              <span><Activity size={17} /> Personal nutrition tracking</span>
            </div>
          </div>
          <span className="auth-story-foot">FOODINSIGHTAI V2 · NUTRITION INTELLIGENCE</span>
        </section>

        <section className="auth-form-side">
          <form className="auth-card" onSubmit={submit}>
            <p className="eyebrow">{mode === "login" ? "WELCOME BACK" : "GET STARTED"}</p>
            <h2>{mode === "login" ? "Sign in to your workspace" : "Create your account"}</h2>
            <p className="auth-subtitle">
              {mode === "login"
                ? "Your food journal and saved recipes are waiting."
                : "Start building a clearer picture of your nutrition."}
            </p>

            {mode === "register" && (
              <label className="auth-field">
                <span>Your name</span>
                <div><UserRound size={17} /><input value={name} onChange={e => setName(e.target.value)} placeholder="Display name" minLength={2} maxLength={80} required autoComplete="name" /></div>
              </label>
            )}

            <label className="auth-field">
              <span>Email address</span>
              <div><Mail size={17} /><input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required autoComplete="email" /></div>
            </label>

            <label className="auth-field">
              <span>Password</span>
              <div>
                <LockKeyhole size={17} />
                <input type={showPassword ? "text" : "password"} value={password} onChange={e => setPassword(e.target.value)} placeholder={mode === "register" ? "At least 10 characters" : "Enter your password"} minLength={mode === "register" ? 10 : 1} maxLength={128} required autoComplete={mode === "login" ? "current-password" : "new-password"} />
                <button className="password-toggle" type="button" onClick={() => setShowPassword(v => !v)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}</button>
              </div>
            </label>

            {error && <p className="auth-error" role="alert">{error}</p>}

            <button className="auth-submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={18}/> : <>{mode === "login" ? "Sign in" : "Create account"} <ArrowRight size={17}/></>}
            </button>

            <p className="auth-switch">
              {mode === "login" ? "New to FoodInsightAI?" : "Already have an account?"}
              <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
                {mode === "login" ? "Create an account" : "Sign in"}
              </button>
            </p>
            <p className="auth-security"><ShieldCheck size={14}/> Your account is protected by authenticated access.</p>
          </form>
        </section>
      </main>
    );
  }

  return (
    <>
      <div className="session-bar">
        <span><span className="session-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span><span className="session-name">{user.display_name}</span></span>
        <button onClick={logout}>Sign out</button>
      </div>
      {children}
    </>
  );
}