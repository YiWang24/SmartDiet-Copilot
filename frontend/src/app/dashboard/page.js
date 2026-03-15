"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import NutritionCard from "@/components/dashboard/NutritionCard";
import QuickActions from "@/components/dashboard/QuickActions";
import SmartSuggestion from "@/components/dashboard/SmartSuggestion";
import RecipeCard from "@/components/dashboard/RecipeCard";
import EmptyState from "@/components/ui/EmptyState";
import { ROUTES } from "@/lib/constants";
import {
  getCurrentUserId,
  getGoals,
  getRecommendationHistory,
  getSpoilageAlerts,
  getTodayNutrition,
} from "@/lib/api";

const FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80";

function fallbackImageByTitle(title) {
  const slug = encodeURIComponent((title || "recipe").trim().toLowerCase().replace(/\s+/g, "-"));
  return `https://picsum.photos/seed/smartdiet-${slug}/800/450`;
}

function toRecipeCard(bundle) {
  const nutrition = bundle?.meal_plan?.nutrition_summary || {};
  const tasks = bundle?.execution_plan?.cooking_dag_tasks || [];
  const totalMinutes = tasks.length
    ? tasks.reduce((sum, task) => sum + (task.duration_minutes || 0), 0)
    : Math.max(10, (bundle?.meal_plan?.steps?.length || 2) * 6);
  const title = bundle.decision?.recipe_title || "Suggested meal";
  const thumbnailUrl = bundle?.recipe_metadata?.thumbnail_url;

  return {
    id: bundle.recommendation_id,
    title,
    kcal: String(nutrition.calories || 0),
    time: `${totalMinutes}m`,
    imageUrl: thumbnailUrl || fallbackImageByTitle(title) || FALLBACK_IMAGE,
  };
}

export default function DashboardPage() {
  const userId = getCurrentUserId();
  const [history, setHistory] = useState([]);
  const [goals, setGoals] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [todayNutrition, setTodayNutrition] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [historyRes, goalsRes, alertsRes, todayNutritionRes] = await Promise.all([
          getRecommendationHistory(userId, 8).catch(() => []),
          getGoals(userId).catch(() => null),
          getSpoilageAlerts().catch(() => []),
          getTodayNutrition().catch(() => null),
        ]);
        if (!active) return;
        setHistory(Array.isArray(historyRes) ? historyRes : []);
        setGoals(goalsRes);
        setAlerts(Array.isArray(alertsRes) ? alertsRes : []);
        setTodayNutrition(todayNutritionRes);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load dashboard data");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [userId]);

  const latest = history[0] || null;
  const cards = useMemo(() => history.map(toRecipeCard), [history]);
  const hasTodayMealData = Number(todayNutrition?.meal_count || 0) > 0;

  const currentCalories = hasTodayMealData
    ? todayNutrition.calories || 0
    : latest?.meal_plan?.nutrition_summary?.calories || 0;
  const targetCalories = goals?.calories_target || Math.max(2000, currentCalories || 0);
  const caloriePercent =
    targetCalories > 0 ? Math.min(100, Math.round((currentCalories / targetCalories) * 100)) : 0;

  const proteinCurrent = hasTodayMealData
    ? todayNutrition.protein_g || 0
    : latest?.meal_plan?.nutrition_summary?.protein_g || 0;
  const carbsCurrent = hasTodayMealData
    ? todayNutrition.carbs_g || 0
    : latest?.meal_plan?.nutrition_summary?.carbs_g || 0;
  const fatsCurrent = hasTodayMealData
    ? todayNutrition.fat_g || 0
    : latest?.meal_plan?.nutrition_summary?.fat_g || 0;

  const macros = [
    {
      name: "Protein",
      value: `${proteinCurrent}g`,
      color: "bg-blue-500",
      width:
        goals?.protein_g_target > 0
          ? Math.min(100, Math.round((proteinCurrent / goals.protein_g_target) * 100))
          : 0,
    },
    {
      name: "Carbs",
      value: `${carbsCurrent}g`,
      color: "bg-amber-500",
      width:
        goals?.carbs_g_target > 0
          ? Math.min(100, Math.round((carbsCurrent / goals.carbs_g_target) * 100))
          : 0,
    },
    {
      name: "Fats",
      value: `${fatsCurrent}g`,
      color: "bg-rose-500",
      width:
        goals?.fat_g_target > 0
          ? Math.min(100, Math.round((fatsCurrent / goals.fat_g_target) * 100))
          : 0,
    },
  ];

  const suggestionTitle =
    alerts.length > 0
      ? `${alerts[0].ingredient} expires in ${alerts[0].expires_in_days} day(s)`
      : "No critical spoilage right now";
  const suggestionDescription =
    alerts.length > 0
      ? "Generated from your pantry scan. Prioritize expiring ingredients to reduce waste."
      : "Run a fridge scan to populate pantry freshness and auto-suggestions.";
  const suggestionRecipes = cards.slice(0, 3).map((item) => ({
    name: item.title,
    icon: "restaurant_menu",
    recommendationId: item.id,
  }));

  return (
    <div className="mx-auto w-full max-w-[640px] flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-2xl font-black tracking-tight">Today&apos;s Nutrition</h2>
        <NutritionCard
          calories={{ current: currentCalories, target: targetCalories, percent: caloriePercent }}
          macros={macros}
        />
      </section>

      <QuickActions />

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Smart Suggestions</h2>
          <Link href="/dashboard/recipes" className="text-sm font-medium text-primary hover:underline">
            View All
          </Link>
        </div>
        <SmartSuggestion
          title={suggestionTitle}
          description={suggestionDescription}
          recipes={suggestionRecipes.length ? suggestionRecipes : undefined}
        />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-bold">Recommended for You</h2>
        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
            Loading recommendations...
          </div>
        ) : cards.length === 0 ? (
          <EmptyState
            icon="restaurant"
            title="No recommendations yet"
            description="Scan your fridge or send a message in Chat to generate your first plan."
            action={
              <Link href={ROUTES.scanFridge} className="text-primary font-semibold text-sm hover:underline">
                Scan Fridge
              </Link>
            }
          />
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {cards.slice(0, 4).map((recipe) => (
              <RecipeCard
                key={recipe.id}
                title={recipe.title}
                kcal={recipe.kcal}
                time={recipe.time}
                imageUrl={recipe.imageUrl}
                href={`/dashboard/recipes/${recipe.id}`}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
