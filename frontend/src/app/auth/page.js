"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Icon from "@/components/ui/Icon";
import {
  getCurrentUser,
  hasAuthSession,
  requestEmailCode,
  saveAuthSession,
  verifyEmailCode,
} from "@/lib/api";
import { ROUTES } from "@/lib/constants";

const STEP_EMAIL = "email";
const STEP_CODE = "code";

export default function AuthPage() {
  const router = useRouter();
  const [step, setStep] = useState(STEP_EMAIL);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [session, setSession] = useState("");
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    async function boot() {
      if (!hasAuthSession()) {
        if (active) setBooting(false);
        return;
      }
      try {
        await getCurrentUser();
        if (!active) return;
        router.replace(ROUTES.dashboard);
      } catch {
        if (active) setBooting(false);
      }
    }
    boot();
    return () => { active = false; };
  }, [router]);

  async function handleRequestCode(event) {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const data = await requestEmailCode(email);
      setSession(data.session);
      setNotice("A sign-in code has been sent to your email.");
      setStep(STEP_CODE);
    } catch (err) {
      setError(err.message || "Failed to send code. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyCode(event) {
    event.preventDefault();
    if (loading) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const tokens = await verifyEmailCode(email, code, session);
      saveAuthSession(tokens);
      router.replace(ROUTES.onboarding);
    } catch (err) {
      setError(err.message || "Invalid or expired code. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    if (loading) return;
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const data = await requestEmailCode(email);
      setSession(data.session);
      setCode("");
      setNotice("A new code has been sent to your email.");
    } catch (err) {
      setError(err.message || "Failed to resend code.");
    } finally {
      setLoading(false);
    }
  }

  if (booting) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background-light px-4">
        <div className="text-sm text-slate-500">Checking session...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background-light flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-[460px] rounded-3xl border border-slate-200 bg-white shadow-sm p-6 md:p-8 space-y-6">

        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <Icon name={step === STEP_EMAIL ? "mail" : "pin"} className="text-2xl" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">Passwordless</p>
            <h1 className="text-2xl font-black tracking-tight">
              {step === STEP_EMAIL ? "Sign in" : "Enter code"}
            </h1>
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        {notice && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {notice}
          </div>
        )}

        {step === STEP_EMAIL ? (
          <form onSubmit={handleRequestCode} className="space-y-4">
            <label className="block space-y-1.5">
              <span className="text-sm font-semibold text-slate-700">Email address</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </label>
            <p className="text-xs text-slate-500">
              New users are registered automatically. No password needed.
            </p>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-primary text-white font-bold py-3 disabled:opacity-60 transition-opacity"
            >
              {loading ? "Sending..." : "Send sign-in code"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyCode} className="space-y-4">
            <p className="text-sm text-slate-600">
              Code sent to <span className="font-semibold">{email}</span>
            </p>
            <label className="block space-y-1.5">
              <span className="text-sm font-semibold text-slate-700">6-digit code</span>
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm tracking-widest text-center text-lg focus:outline-none focus:ring-2 focus:ring-primary/30"
                placeholder="00000000"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
              />
            </label>
            <button
              type="submit"
              disabled={loading || code.length < 8}
              className="w-full rounded-xl bg-primary text-white font-bold py-3 disabled:opacity-60 transition-opacity"
            >
              {loading ? "Verifying..." : "Sign in"}
            </button>
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                onClick={() => { setStep(STEP_EMAIL); setError(""); setNotice(""); setCode(""); }}
                className="text-slate-500 hover:text-slate-700"
              >
                ← Change email
              </button>
              <button
                type="button"
                onClick={handleResend}
                disabled={loading}
                className="text-primary font-semibold disabled:opacity-60"
              >
                Resend code
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
