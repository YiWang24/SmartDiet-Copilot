"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/ui/Icon";
import { useToastFeedback } from "@/hooks/useToastFeedback";
import { getPantry, getSpoilageAlerts } from "@/lib/api";
import { ROUTES } from "@/lib/constants";

const FRIDGE_IMAGE =
  "https://images.unsplash.com/photo-1586201375761-83865001e31c?auto=format&fit=crop&w=1400&q=80";

function urgencyClass(days) {
  if (days == null) return "bg-primary/10 text-primary";
  if (days <= 1) return "bg-red-100 text-red-700";
  if (days <= 3) return "bg-orange-100 text-orange-700";
  return "bg-primary/10 text-primary";
}

export default function LivelarderPage() {
  const [pantry, setPantry] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
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
        const [pantryRes, alertsRes] = await Promise.all([getPantry(), getSpoilageAlerts()]);
        if (!active) return;
        setPantry(Array.isArray(pantryRes) ? pantryRes : []);
        setAlerts(Array.isArray(alertsRes) ? alertsRes : []);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load LiveLarder data");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="max-w-[1200px] mx-auto flex flex-1 flex-col gap-8 py-8 px-4 w-full">
      <nav className="flex items-center gap-6 border-b border-primary/5 pb-2">
        <span className="text-primary border-b-2 border-primary pb-2 font-semibold text-sm flex items-center gap-2">
          <Icon name="visibility" className="text-sm" /> LiveLarder
        </span>
        <Link
          href={ROUTES.scanFridge}
          className="text-slate-500 pb-2 font-medium text-sm flex items-center gap-2 hover:text-primary transition-colors"
        >
          <Icon name="camera_alt" className="text-sm" /> Scan
        </Link>
        <Link
          href="/dashboard/recipes"
          className="text-slate-500 pb-2 font-medium text-sm flex items-center gap-2 hover:text-primary transition-colors"
        >
          <Icon name="menu_book" className="text-sm" /> Recipes
        </Link>
      </nav>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl overflow-hidden border border-slate-200 bg-slate-100 relative min-h-[320px]">
          <div
            className="absolute inset-0 bg-cover bg-center opacity-90"
            style={{ backgroundImage: `url("${FRIDGE_IMAGE}")` }}
          />
          <div className="absolute inset-0 bg-black/25" />
          <div className="absolute inset-0 p-4 flex flex-wrap content-start gap-2">
            {alerts.map((alert, index) => (
              <div
                key={`${alert.item_id}-${index}`}
                className="px-3 py-1.5 rounded-full bg-red-600/90 text-white text-xs font-bold"
              >
                {alert.ingredient} • {alert.expires_in_days}d left
              </div>
            ))}
          </div>
          <div className="absolute bottom-4 left-4 text-white text-xs uppercase tracking-widest bg-black/50 px-2 py-1 rounded">
            LiveLarder Stream
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
          <h2 className="text-base font-bold">Inventory Snapshot</h2>
          {loading ? (
            <p className="text-sm text-slate-500">Loading inventory...</p>
          ) : pantry.length === 0 ? (
            <p className="text-sm text-slate-500">No items yet. Run a fridge or receipt scan.</p>
          ) : (
            <ul className="space-y-2 max-h-[420px] overflow-y-auto">
              {pantry.map((item) => (
                <li
                  key={item.item_id}
                  className="border border-slate-100 rounded-lg p-3 flex items-center justify-between gap-3"
                >
                  <div>
                    <p className="font-semibold text-sm">{item.ingredient}</p>
                    <p className="text-xs text-slate-500">{item.quantity || item.source}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full font-semibold ${urgencyClass(item.expires_in_days)}`}>
                    {item.expires_in_days == null ? "fresh" : `${item.expires_in_days}d`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
