"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Icon from "@/components/ui/Icon";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { getRecommendation } from "@/lib/api";

export default function RecipeDetailPage() {
  const params = useParams();
  const recommendationId = Array.isArray(params?.slug) ? params.slug[0] : params?.slug;
  const [bundle, setBundle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useToastFeedback({ error });

  useEffect(() => {
    let active = true;
    async function load() {
      if (!recommendationId) return;
      setLoading(true);
      setError("");
      try {
        const payload = await getRecommendation(recommendationId);
        if (!active) return;
        setBundle(payload);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load recipe details");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [recommendationId]);

  const nutrition = bundle?.meal_plan?.nutrition_summary;
  const groceryGap = useMemo(
    () => bundle?.grocery_plan?.missing_ingredients || [],
    [bundle]
  );

  return (
    <div className="mx-auto w-full max-w-[760px] flex flex-col gap-6 py-8 px-4">
      <Link
        href="/dashboard/recipes"
        className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline w-fit"
      >
        <Icon name="arrow_back" className="text-lg" />
        Back to Recipes
      </Link>

      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Loading recipe details...
        </div>
      ) : error ? (
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
          Recipe details are temporarily unavailable.
        </div>
      ) : (
        <>
          <h1 className="text-2xl font-black tracking-tight">
            {bundle?.decision?.recipe_title || "Recipe detail"}
          </h1>

          <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-6 flex flex-col gap-5">
            <section className="space-y-2">
              <h2 className="text-base font-bold">Why this recipe</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {bundle?.decision?.rationale || "Generated from your goals, pantry, and recent chat context."}
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-base font-bold">Steps</h2>
              <ol className="space-y-2 list-decimal list-inside text-sm text-slate-700 dark:text-slate-300">
                {(bundle?.meal_plan?.steps || []).map((step, index) => (
                  <li key={`${index}-${step}`}>{step}</li>
                ))}
              </ol>
            </section>

            {nutrition && (
              <section className="space-y-2">
                <h2 className="text-base font-bold">Nutrition</h2>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-3">
                    <p className="text-slate-500 text-xs">Calories</p>
                    <p className="font-bold">{nutrition.calories}</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-3">
                    <p className="text-slate-500 text-xs">Protein</p>
                    <p className="font-bold">{nutrition.protein_g}g</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-3">
                    <p className="text-slate-500 text-xs">Carbs</p>
                    <p className="font-bold">{nutrition.carbs_g}g</p>
                  </div>
                  <div className="rounded-lg bg-slate-50 dark:bg-slate-900 p-3">
                    <p className="text-slate-500 text-xs">Fat</p>
                    <p className="font-bold">{nutrition.fat_g}g</p>
                  </div>
                </div>
              </section>
            )}

            <section className="space-y-2">
              <h2 className="text-base font-bold">Grocery Gap</h2>
              {groceryGap.length === 0 ? (
                <p className="text-sm text-slate-500">No missing ingredients. You can cook this now.</p>
              ) : (
                <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
                  {groceryGap.map((item) => (
                    <li key={`${item.ingredient}-${item.reason}`}>
                      • {item.ingredient} ({item.reason})
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
