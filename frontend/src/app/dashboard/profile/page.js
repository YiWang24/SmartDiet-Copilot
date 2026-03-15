"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { clearAuthSession, getCurrentUserId, getGoals, getProfile } from "@/lib/api";
import { ROUTES } from "@/lib/constants";

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

  return (
    <div className="mx-auto w-full max-w-[640px] flex flex-col gap-6 py-8 px-4">
      <h1 className="text-2xl font-black tracking-tight">Profile</h1>

      <Link
        href="/onboarding"
        className="flex items-center gap-4 p-4 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm hover:border-primary/30 hover:bg-primary/5 transition-colors"
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon name="edit" className="text-2xl" />
        </div>
        <div className="flex-1 text-left">
          <p className="font-bold text-slate-900 dark:text-slate-100">Edit onboarding profile</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">Update goals and constraints</p>
        </div>
        <Icon name="chevron_right" className="text-slate-400" />
      </Link>

      <button
        type="button"
        onClick={() => {
          clearAuthSession();
          window.location.href = `${ROUTES.auth}?mode=login`;
        }}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 hover:border-primary/40 hover:text-primary transition-colors"
      >
        Log out
      </button>

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Loading profile...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Profile is temporarily unavailable. Please retry in a moment.
        </div>
      ) : (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5 space-y-4">
          <div>
            <p className="text-xs text-slate-500">User ID</p>
            <p className="font-semibold">{profile?.user_id || userId}</p>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-slate-500">Age</p>
              <p className="font-semibold">{profile?.age ?? "-"}</p>
            </div>
            <div>
              <p className="text-slate-500">Sex at Birth</p>
              <p className="font-semibold">
                {profile?.biological_sex
                  ? profile.biological_sex.charAt(0).toUpperCase() + profile.biological_sex.slice(1)
                  : "-"}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Activity</p>
              <p className="font-semibold">{profile?.activity_level || "-"}</p>
            </div>
            <div>
              <p className="text-slate-500">Height</p>
              <p className="font-semibold">{profile?.height_cm ?? "-"} cm</p>
            </div>
            <div>
              <p className="text-slate-500">Weight</p>
              <p className="font-semibold">{profile?.weight_kg ?? "-"} kg</p>
            </div>
          </div>
          <div>
            <p className="text-xs text-slate-500">Dietary Preferences</p>
            <p className="font-semibold">
              {(profile?.dietary_preferences || []).join(", ") || "None"}
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Allergies</p>
            <p className="font-semibold">{(profile?.allergies || []).join(", ") || "None"}</p>
          </div>
          <hr className="border-slate-200 dark:border-slate-700" />
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-slate-500">Daily Target</p>
              <p className="font-semibold">{goals?.calories_target ?? "-"} kcal</p>
            </div>
            <div>
              <p className="text-slate-500">Max Cook Time</p>
              <p className="font-semibold">{goals?.max_cook_time_minutes ?? "-"} min</p>
            </div>
            <div>
              <p className="text-slate-500">Macro Targets</p>
              <p className="font-semibold">
                {goals?.protein_g_target ?? "-"} / {goals?.carbs_g_target ?? "-"} /{" "}
                {goals?.fat_g_target ?? "-"} g
              </p>
            </div>
            <div>
              <p className="text-slate-500">Budget</p>
              <p className="font-semibold">${goals?.budget_limit ?? "-"}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
