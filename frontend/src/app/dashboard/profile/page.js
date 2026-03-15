"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { clearAuthSession, getCurrentUserId, getGoals, getProfile } from "@/lib/api";
import { ROUTES } from "@/lib/constants";

function formatEnum(value, fallback = "Not set") {
  if (!value && value !== 0) return fallback;
  return String(value)
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function MetricTile({ icon, label, value, unit = "" }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/85 p-3.5">
      <div className="mb-2 inline-flex h-8 w-8 items-center justify-center rounded-lg bg-white text-emerald-600 shadow-sm">
        <Icon name={icon} className="text-lg" />
      </div>
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-black tracking-tight text-slate-900">
        {value}
        {unit ? <span className="ml-1 text-sm font-bold text-slate-500">{unit}</span> : null}
      </p>
    </div>
  );
}

function TagList({ values, fallback }) {
  if (!Array.isArray(values) || values.length === 0) {
    return <p className="text-sm font-semibold text-slate-500">{fallback}</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((item) => (
        <span
          key={item}
          className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700"
        >
          {formatEnum(item, item)}
        </span>
      ))}
    </div>
  );
}

export default function ProfilePage() {
  const userId = getCurrentUserId();
  const [profile, setProfile] = useState(null);
  const [goals, setGoals] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useToastFeedback({ error });

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [profileRes, goalsRes] = await Promise.all([
          getProfile(userId),
          getGoals(userId),
        ]);
        if (!active) return;
        setProfile(profileRes);
        setGoals(goalsRes);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load profile");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [userId]);

  const shortUserId = String(profile?.user_id || userId || "").slice(-8);

  return (
    <div className="mx-auto w-full max-w-[760px] flex flex-col gap-5 py-7 px-4 sm:px-5">
      <section className="hero-reveal hero-delay-1 relative overflow-hidden rounded-3xl border border-emerald-200/80 bg-gradient-to-br from-emerald-950 via-slate-900 to-emerald-800 p-5 text-white shadow-[0_26px_70px_-36px_rgba(6,95,70,0.85)] sm:p-6">
        <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-emerald-300/20 blur-3xl" aria-hidden />
        <div className="absolute -bottom-24 left-14 h-56 w-56 rounded-full bg-cyan-300/20 blur-3xl" aria-hidden />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-white/18 text-2xl font-black uppercase text-white ring-1 ring-white/25">
              {shortUserId ? shortUserId.slice(-2) : "U"}
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-200">Personal Profile</p>
              <h1 className="text-3xl font-black tracking-tight">Account & Nutrition</h1>
            </div>
          </div>
          <span className="rounded-full border border-white/25 bg-white/10 px-3 py-1 text-xs font-semibold tracking-wide text-emerald-100">
            ID · ...{shortUserId || "unknown"}
          </span>
        </div>
        <div className="relative mt-5 grid grid-cols-3 gap-2.5 sm:gap-3">
          <div className="rounded-2xl border border-white/20 bg-white/10 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-100">Daily target</p>
            <p className="mt-1 text-xl font-black">{goals?.calories_target ?? "-"}<span className="ml-1 text-xs font-semibold text-emerald-100">kcal</span></p>
          </div>
          <div className="rounded-2xl border border-white/20 bg-white/10 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-100">Cook time</p>
            <p className="mt-1 text-xl font-black">{goals?.max_cook_time_minutes ?? "-"}<span className="ml-1 text-xs font-semibold text-emerald-100">min</span></p>
          </div>
          <div className="rounded-2xl border border-white/20 bg-white/10 p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-100">Budget</p>
            <p className="mt-1 text-xl font-black">${goals?.budget_limit ?? "-"}</p>
          </div>
        </div>
      </section>

      <div className="hero-reveal hero-delay-2 grid gap-3 sm:grid-cols-2">
        <Link
          href="/onboarding"
          className="group flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-emerald-300 hover:shadow-[0_18px_35px_-26px_rgba(16,185,129,0.9)]"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 transition-colors group-hover:bg-emerald-200">
            <Icon name="edit_note" className="text-[22px]" />
          </div>
          <div className="flex-1 text-left">
            <p className="font-black text-slate-900">Edit profile data</p>
            <p className="text-sm text-slate-500">Update goals, activity, and constraints</p>
          </div>
          <Icon name="arrow_forward_ios" className="text-base text-slate-400 transition-transform group-hover:translate-x-0.5" />
        </Link>

        <button
          type="button"
          onClick={() => {
            clearAuthSession();
            window.location.href = `${ROUTES.auth}?mode=login`;
          }}
          className="flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-700 shadow-sm transition-colors hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700"
        >
          <Icon name="logout" className="text-base" />
          Log out
        </button>
      </div>

      {loading ? (
        <div className="hero-reveal hero-delay-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="space-y-3 animate-pulse">
            <div className="h-4 w-32 rounded bg-slate-200" />
            <div className="grid grid-cols-2 gap-3">
              <div className="h-24 rounded-2xl bg-slate-100" />
              <div className="h-24 rounded-2xl bg-slate-100" />
            </div>
            <div className="h-20 rounded-2xl bg-slate-100" />
          </div>
        </div>
      ) : error ? (
        <div className="hero-reveal hero-delay-3 rounded-3xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800 shadow-sm">
          Profile is temporarily unavailable. Please retry in a moment.
        </div>
      ) : (
        <div className="hero-reveal hero-delay-3 grid gap-4">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-black tracking-tight text-slate-900">Body metrics</h2>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-500">
                User ID: {profile?.user_id || userId}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              <MetricTile icon="event" label="Age" value={profile?.age ?? "-"} />
              <MetricTile icon="wc" label="Sex at birth" value={formatEnum(profile?.biological_sex, "-")} />
              <MetricTile icon="directions_run" label="Activity" value={formatEnum(profile?.activity_level, "-")} />
              <MetricTile icon="straighten" label="Height" value={profile?.height_cm ?? "-"} unit="cm" />
              <MetricTile icon="monitor_weight" label="Weight" value={profile?.weight_kg ?? "-"} unit="kg" />
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-black tracking-tight text-slate-900">Diet and constraints</h2>
            <div className="mt-4 space-y-4">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Dietary preferences</p>
                <TagList values={profile?.dietary_preferences} fallback="None selected" />
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Allergies</p>
                <TagList values={profile?.allergies} fallback="None selected" />
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-lg font-black tracking-tight text-slate-900">Goal targets</h2>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <MetricTile icon="local_fire_department" label="Daily target" value={goals?.calories_target ?? "-"} unit="kcal" />
              <MetricTile icon="timer" label="Max cook time" value={goals?.max_cook_time_minutes ?? "-"} unit="min" />
              <MetricTile icon="egg_alt" label="Protein target" value={goals?.protein_g_target ?? "-"} unit="g" />
              <MetricTile icon="grain" label="Carbs target" value={goals?.carbs_g_target ?? "-"} unit="g" />
              <MetricTile icon="opacity" label="Fat target" value={goals?.fat_g_target ?? "-"} unit="g" />
              <MetricTile icon="savings" label="Budget" value={goals?.budget_limit ?? "-"} unit="USD" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
