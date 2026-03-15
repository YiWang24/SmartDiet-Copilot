"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NutritionCard from "@/components/dashboard/NutritionCard";
import QuickActions from "@/components/dashboard/QuickActions";
import SmartSuggestion from "@/components/dashboard/SmartSuggestion";
import RecipeCard from "@/components/dashboard/RecipeCard";
import EmptyState from "@/components/ui/EmptyState";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { ROUTES } from "@/lib/constants";
import { calculateNutritionTargets, inferGoalType } from "@/lib/nutrition-targets.mjs";
import { getRecipeFallbackImage } from "@/utils/recipeImages";
import {
  createRecommendation,
  getCurrentUserId,
  getGoals,
  getProfile,
  getRecommendationHistory,
  getSpoilageAlerts,
  getTodayNutrition,
} from "@/lib/api";

const FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80";

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
    imageUrl: thumbnailUrl || getRecipeFallbackImage(title) || FALLBACK_IMAGE,
  };
}

export default function DashboardPage() {
  const router = useRouter();
  const userId = getCurrentUserId();
  const [history, setHistory] = useState([]);
  const [goals, setGoals] = useState(null);
  const [profile, setProfile] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [todayNutrition, setTodayNutrition] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  useToastFeedback({
    error,
    clearError: () => setError(""),
  });

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [historyRes, goalsRes, profileRes, alertsRes, todayNutritionRes] = await Promise.all([
          getRecommendationHistory(userId, 8).catch(() => []),
          getGoals(userId).catch(() => null),
          getProfile(userId).catch(() => null),
          getSpoilageAlerts().catch(() => []),
          getTodayNutrition().catch(() => null),
        ]);
        if (!active) return;
        setHistory(Array.isArray(historyRes) ? historyRes : []);
        setGoals(goalsRes);
        setProfile(profileRes);
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

  async function handleGenerate() {
    if (isGenerating || alerts.length === 0) return;
    setIsGenerating(true);
    setError("");
    try {
      const expiringNames = alerts
        .slice(0, 3)
        .map((a) => a.ingredient)
        .join(", ");
      const rec = await createRecommendation({
        user_id: userId,
        constraints: {},
        user_message: `Please use these expiring ingredients: ${expiringNames}`,
      });
      router.push(`/dashboard/recipes/${rec.recommendation_id}`);
    } catch (err) {
      setError(err.message || "Failed to generate recipe. Please try again.");
      setIsGenerating(false);
    }
  }

  const latest = history[0] || null;
  const cards = useMemo(() => history.map(toRecipeCard), [history]);
  const hasTodayMealData = Number(todayNutrition?.meal_count || 0) > 0;
  const goalType = inferGoalType(
    { caloriesTarget: goals?.calories_target },
    {
      age: profile?.age,
      heightCm: profile?.height_cm,
      weightKg: profile?.weight_kg,
      biologicalSex: profile?.biological_sex,
      activityLevel: profile?.activity_level,
    },
  );
  const targetReference = calculateNutritionTargets({
    age: profile?.age,
    heightCm: profile?.height_cm,
    weightKg: profile?.weight_kg,
    biologicalSex: profile?.biological_sex,
    activityLevel: profile?.activity_level,
    goalType,
  });

  const currentCalories = hasTodayMealData
    ? todayNutrition.calories || 0
    : latest?.meal_plan?.nutrition_summary?.calories || 0;
  const targetCalories = goals?.calories_target || Math.max(2000, currentCalories || 0);
  const caloriePercent =
    targetCalories > 0 ? Math.min(100, Math.round((currentCalories / targetCalories) * 100)) : 0;

  const maintenanceCalories = targetReference.ready ? targetReference.maintenanceCalories : targetCalories;
  const adjustmentLabel = targetReference.ready
    ? targetReference.calorieDelta === 0
      ? "Goal adjustment 0 kcal"
      : `Goal adjustment ${targetReference.calorieDelta > 0 ? "+" : ""}${targetReference.calorieDelta} kcal`
    : "Goal adjustment unavailable";

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
      value:
        goals?.protein_g_target > 0
          ? `${proteinCurrent} / ${goals.protein_g_target}g`
          : `${proteinCurrent}g`,
      color: "bg-blue-500",
      width:
        goals?.protein_g_target > 0
          ? Math.min(100, Math.round((proteinCurrent / goals.protein_g_target) * 100))
          : 0,
    },
    {
      name: "Carbs",
      value:
        goals?.carbs_g_target > 0
          ? `${carbsCurrent} / ${goals.carbs_g_target}g`
          : `${carbsCurrent}g`,
      color: "bg-amber-500",
      width:
        goals?.carbs_g_target > 0
          ? Math.min(100, Math.round((carbsCurrent / goals.carbs_g_target) * 100))
          : 0,
    },
    {
      name: "Fats",
      value:
        goals?.fat_g_target > 0
          ? `${fatsCurrent} / ${goals.fat_g_target}g`
          : `${fatsCurrent}g`,
      color: "bg-rose-500",
      width:
        goals?.fat_g_target > 0
          ? Math.min(100, Math.round((fatsCurrent / goals.fat_g_target) * 100))
          : 0,
    },
  ];

  return (
    <div className="mx-auto w-full max-w-[640px] flex flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h2 className="text-2xl font-black tracking-tight">Today&apos;s Nutrition</h2>
        <NutritionCard
          calories={{
            current: currentCalories,
            target: targetCalories,
            percent: caloriePercent,
            maintenance: maintenanceCalories,
            adjustmentLabel,
          }}
          macros={macros}
        />
      </section>

      <QuickActions />
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-bold">Smart Suggestions</h2>
        <SmartSuggestion
          alerts={alerts}
          isGenerating={isGenerating}
          onGenerate={handleGenerate}
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
