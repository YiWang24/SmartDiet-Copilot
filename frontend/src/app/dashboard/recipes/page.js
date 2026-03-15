"use client";

import { useEffect, useMemo, useState } from "react";
import RecipeCard from "@/components/dashboard/RecipeCard";
import EmptyState from "@/components/ui/EmptyState";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { getCurrentUserId, getRecommendationHistory } from "@/lib/api";
import { getRecipeFallbackImage } from "@/utils/recipeImages";

const FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=800&q=80";

function toRecipeCard(bundle) {
  const tasks = bundle?.execution_plan?.cooking_dag_tasks || [];
  const totalMinutes = tasks.length
    ? tasks.reduce((sum, task) => sum + (task.duration_minutes || 0), 0)
    : Math.max(10, (bundle?.meal_plan?.steps?.length || 2) * 6);
  const title = bundle?.decision?.recipe_title || "Suggested meal";
  const thumbnailUrl = bundle?.recipe_metadata?.thumbnail_url;
  return {
    id: bundle.recommendation_id,
    title,
    kcal: String(bundle?.meal_plan?.nutrition_summary?.calories || 0),
    time: `${totalMinutes}m`,
    imageUrl: thumbnailUrl || getRecipeFallbackImage(title) || FALLBACK_IMAGE,
  };
}

export default function RecipesPage() {
  const userId = getCurrentUserId();
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useToastFeedback({ error });

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const rows = await getRecommendationHistory(userId, 30);
        if (!active) return;
        setHistory(Array.isArray(rows) ? rows : []);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load recipes");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [userId]);

  const cards = useMemo(() => history.map(toRecipeCard), [history]);

  return (
    <div className="mx-auto w-full max-w-[760px] flex flex-col gap-6 py-8 px-4">
      <h1 className="text-2xl font-black tracking-tight">Recipes</h1>
      {loading ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Loading recipe history...
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Recipe history is temporarily unavailable.
        </div>
      ) : cards.length === 0 ? (
        <EmptyState
          icon="menu_book"
          title="No recipes generated yet"
          description="Go to Chat or Scan and generate your first recommendation."
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {cards.map((recipe) => (
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
    </div>
  );
}
