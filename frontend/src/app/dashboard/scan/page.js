"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import CameraFrame from "@/components/scan/CameraFrame";
import DetectedIngredientList from "@/components/scan/DetectedIngredientList";
import FreshnessLegend from "@/components/scan/FreshnessLegend";
import Icon from "@/components/ui/Icon";
import {
  createRecommendation,
  getCurrentUserId,
  getPantry,
  getSpoilageAlerts,
  pollInputJob,
  submitFridgeScan,
  submitMealScan,
  submitReceiptScan,
} from "@/lib/api";

const TAB_FRIDGE = "fridge";
const TAB_MEAL = "meal";
const TAB_RECEIPT = "receipt";
const SCAN_TABS = [
  { id: TAB_FRIDGE, label: "Scan Fridge", icon: "kitchen" },
  { id: TAB_MEAL, label: "Scan Meal", icon: "photo_camera" },
  { id: TAB_RECEIPT, label: "Scan Receipt", icon: "receipt" },
];
const SCAN_JOB_TIMEOUT_MS = 120000;

function resolveTab(value) {
  if (value === TAB_FRIDGE || value === TAB_MEAL || value === TAB_RECEIPT) {
    return value;
  }
  return TAB_FRIDGE;
}

function statusFromDays(days) {
  if (days == null) return "fresh";
  if (days <= 1) return "critical";
  if (days <= 3) return "expiring_soon";
  return "fresh";
}

function statusText(item) {
  if (item.expires_in_days == null) return item.quantity ? `Qty: ${item.quantity}` : "Fresh";
  if (item.expires_in_days <= 0) return "Use immediately";
  return `Expires in ${item.expires_in_days} day(s)`;
}

function iconForIngredient(name) {
  const value = (name || "").toLowerCase();
  if (value.includes("egg")) return "egg";
  if (value.includes("milk") || value.includes("yogurt")) return "water_drop";
  if (value.includes("chicken") || value.includes("meat")) return "restaurant";
  if (value.includes("berry") || value.includes("fruit")) return "nutrition";
  return "eco";
}

function normalizeIngredientName(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function dedupePantryItems(items) {
  const byIngredient = new Map();

  for (const row of Array.isArray(items) ? items : []) {
    const key = normalizeIngredientName(row?.ingredient);
    if (!key) continue;

    const current = byIngredient.get(key);
    if (!current) {
      byIngredient.set(key, { ...row, ingredient: key });
      continue;
    }

    const merged = { ...current };
    if (!merged.quantity && row.quantity) {
      merged.quantity = row.quantity;
    }

    if (row.expires_in_days != null) {
      if (merged.expires_in_days == null || row.expires_in_days < merged.expires_in_days) {
        merged.expires_in_days = row.expires_in_days;
      }
    }

    const currentUpdated = Date.parse(current.updated_at || "") || 0;
    const rowUpdated = Date.parse(row.updated_at || "") || 0;
    if (rowUpdated > currentUpdated) {
      merged.updated_at = row.updated_at;
      merged.source = row.source || merged.source;
      merged.item_id = row.item_id;
    }

    byIngredient.set(key, merged);
  }

  return Array.from(byIngredient.values()).sort((a, b) => {
    const aDays = a.expires_in_days;
    const bDays = b.expires_in_days;
    if (aDays == null && bDays == null) return a.ingredient.localeCompare(b.ingredient);
    if (aDays == null) return 1;
    if (bDays == null) return -1;
    if (aDays !== bDays) return aDays - bDays;
    return a.ingredient.localeCompare(b.ingredient);
  });
}

function toDetectedItems(items) {
  return items.map((item) => ({
    id: String(item.item_id || item.ingredient),
    name: item.ingredient,
    icon: iconForIngredient(item.ingredient),
    status: statusFromDays(item.expires_in_days),
    statusText: statusText(item),
  }));
}

function ImagePlaceholder({ title, description }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-slate-100/85 text-center text-slate-500 px-6">
      <Icon name="image" className="text-4xl" />
      <p className="text-sm font-semibold">{title}</p>
      <p className="text-xs">{description}</p>
    </div>
  );
}

function TabButton({ active, icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-3xl border p-5 text-left transition-all ${
        active
          ? "border-primary bg-primary text-white shadow-lg shadow-primary/20"
          : "border-primary/30 bg-white text-slate-900 hover:border-primary/60 hover:bg-primary/5"
      }`}
    >
      <div className="flex items-center gap-3">
        <Icon name={icon} className="text-3xl" />
        <span className="text-xl font-black tracking-tight">{label}</span>
      </div>
    </button>
  );
}

function ActionButton({ disabled, busy, idleText, busyText, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl bg-primary text-white font-bold shadow-lg disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Icon name={busy ? "hourglass_top" : "camera_alt"} />
      {busy ? busyText : idleText}
    </button>
  );
}

export default function UnifiedScanPage() {
  const router = useRouter();

  const fridgeFileRef = useRef(null);
  const mealFileRef = useRef(null);
  const receiptFileRef = useRef(null);

  const [activeTab, setActiveTab] = useState(TAB_FRIDGE);
  const [fridgeImageUrl, setFridgeImageUrl] = useState("");
  const [mealImageUrl, setMealImageUrl] = useState("");
  const [receiptImageUrl, setReceiptImageUrl] = useState("");
  const [mealName, setMealName] = useState("Logged meal");
  const [pantry, setPantry] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [receiptItems, setReceiptItems] = useState([]);
  const [latestMeal, setLatestMeal] = useState(null);
  const [loadingPantry, setLoadingPantry] = useState(true);
  const [scanningFridge, setScanningFridge] = useState(false);
  const [scanningMeal, setScanningMeal] = useState(false);
  const [scanningReceipt, setScanningReceipt] = useState(false);
  const [generatingRecipe, setGeneratingRecipe] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    setActiveTab(resolveTab(params.get("tab")));
  }, []);

  async function loadInventory() {
    const [pantryRes, alertsRes] = await Promise.all([
      getPantry().catch(() => []),
      getSpoilageAlerts().catch(() => []),
    ]);
    const pantryRows = dedupePantryItems(Array.isArray(pantryRes) ? pantryRes : []);
    setPantry(pantryRows);
    setAlerts(Array.isArray(alertsRes) ? alertsRes : []);
    setReceiptItems(pantryRows.filter((item) => item.source === "receipt_scan"));
  }

  useEffect(() => {
    let active = true;
    async function init() {
      setLoadingPantry(true);
      setError("");
      try {
        await loadInventory();
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load scan context");
      } finally {
        if (active) setLoadingPantry(false);
      }
    }
    init();
    return () => {
      active = false;
    };
  }, []);

  const detectedItems = useMemo(() => toDetectedItems(pantry), [pantry]);

  function updateTab(tab) {
    setActiveTab(tab);
    router.replace(`/dashboard/scan?tab=${tab}`, { scroll: false });
  }

  function readFileToDataUrl(file, onDone) {
    const reader = new FileReader();
    reader.onload = () => onDone(String(reader.result || ""));
    reader.readAsDataURL(file);
  }

  function handleUpload(tab, event) {
    const file = event.target.files?.[0];
    if (!file) return;

    readFileToDataUrl(file, (dataUrl) => {
      if (tab === TAB_FRIDGE) {
        setFridgeImageUrl(dataUrl);
      } else if (tab === TAB_MEAL) {
        setMealImageUrl(dataUrl);
      } else {
        setReceiptImageUrl(dataUrl);
      }
      setError("");
      setNotice("Image uploaded. You can now run scan.");
    });

    event.target.value = "";
  }

  async function handleScanFridge() {
    if (!fridgeImageUrl || scanningFridge) return;
    setScanningFridge(true);
    setError("");
    setNotice("");
    try {
      const envelope = await submitFridgeScan({ image_url: fridgeImageUrl, detected_items: [] });
      const job = await pollInputJob(envelope.job_id, {
        timeoutMs: SCAN_JOB_TIMEOUT_MS,
        intervalMs: 700,
      });
      if (job.status !== "COMPLETED") {
        throw new Error("Fridge scan failed");
      }
      await loadInventory();
      setNotice("Fridge scan completed and inventory updated.");
    } catch (err) {
      setError(err.message || "Failed to scan fridge");
    } finally {
      setScanningFridge(false);
    }
  }

  async function handleScanMeal() {
    if (!mealImageUrl || scanningMeal) return;
    setScanningMeal(true);
    setError("");
    setNotice("");
    try {
      const envelope = await submitMealScan({
        image_url: mealImageUrl,
        meal_name: mealName || "Logged meal",
      });
      const job = await pollInputJob(envelope.job_id, {
        timeoutMs: SCAN_JOB_TIMEOUT_MS,
        intervalMs: 700,
      });
      if (job.status !== "COMPLETED") {
        throw new Error("Meal scan failed");
      }
      setLatestMeal(job.result || null);
      setNotice("Meal logged successfully and nutrition updated.");
    } catch (err) {
      setError(err.message || "Failed to log meal");
    } finally {
      setScanningMeal(false);
    }
  }

  async function handleScanReceipt() {
    if (!receiptImageUrl || scanningReceipt) return;
    setScanningReceipt(true);
    setError("");
    setNotice("");
    try {
      const envelope = await submitReceiptScan({ image_url: receiptImageUrl, items: [] });
      const job = await pollInputJob(envelope.job_id, {
        timeoutMs: SCAN_JOB_TIMEOUT_MS,
        intervalMs: 700,
      });
      if (job.status !== "COMPLETED") {
        throw new Error("Receipt scan failed");
      }
      await loadInventory();
      setNotice("Receipt parsed and pantry synced.");
    } catch (err) {
      setError(err.message || "Failed to process receipt");
    } finally {
      setScanningReceipt(false);
    }
  }

  async function handleGenerateRecipe() {
    if (generatingRecipe) return;
    setGeneratingRecipe(true);
    setError("");
    setNotice("");
    try {
      const requestUserId = getCurrentUserId();
      const rec = await createRecommendation({ user_id: requestUserId, constraints: {} });
      if (!rec?.recommendation_id) {
        throw new Error("Recipe generated, but recommendation id is missing");
      }
      setNotice("Recipe generated. Redirecting to details...");
      router.push(`/dashboard/recipes/${rec.recommendation_id}`);
    } catch (err) {
      setError(err.message || "Failed to generate recipe");
    } finally {
      setGeneratingRecipe(false);
    }
  }

  return (
    <div className="max-w-[960px] mx-auto flex flex-1 flex-col gap-6 py-8 px-4 w-full">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4" role="tablist" aria-label="Scan types">
        {SCAN_TABS.map((tab) => (
          <TabButton
            key={tab.id}
            active={activeTab === tab.id}
            icon={tab.icon}
            label={tab.label}
            onClick={() => updateTab(tab.id)}
          />
        ))}
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

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {activeTab === TAB_FRIDGE && (
          <>
            <section className="lg:col-span-7 flex flex-col gap-4">
              <CameraFrame imageUrl={fridgeImageUrl}>
                {!fridgeImageUrl && (
                  <ImagePlaceholder
                    title="Upload a fridge image first"
                    description="Scan button is disabled until an image is uploaded."
                  />
                )}
              </CameraFrame>
              <div className="flex gap-3">
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  ref={fridgeFileRef}
                  onChange={(event) => handleUpload(TAB_FRIDGE, event)}
                />
                <button
                  type="button"
                  onClick={() => fridgeFileRef.current?.click()}
                  className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm font-semibold"
                >
                  Upload image
                </button>
                <ActionButton
                  disabled={!fridgeImageUrl}
                  busy={scanningFridge}
                  idleText="Scan My Fridge"
                  busyText="Scanning..."
                  onClick={handleScanFridge}
                />
              </div>
              <FreshnessLegend />
              <button
                type="button"
                onClick={handleGenerateRecipe}
                disabled={generatingRecipe}
                className="self-start bg-primary text-white px-4 py-2 rounded-xl text-sm font-bold disabled:cursor-not-allowed disabled:opacity-60"
              >
                {generatingRecipe ? "Generating..." : "Generate Recipes Now"}
              </button>
            </section>
            <aside className="lg:col-span-5">
              {loadingPantry ? (
                <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500">
                  Loading pantry...
                </div>
              ) : (
                <DetectedIngredientList items={detectedItems} />
              )}
            </aside>
          </>
        )}

        {activeTab === TAB_MEAL && (
          <>
            <section className="lg:col-span-7 flex flex-col gap-4">
              <CameraFrame imageUrl={mealImageUrl}>
                {!mealImageUrl && (
                  <ImagePlaceholder
                    title="Upload a meal image first"
                    description="Confirm button is disabled until an image is uploaded."
                  />
                )}
              </CameraFrame>
              <label className="flex flex-col gap-2">
                <span className="text-sm font-semibold">Meal Name (optional)</span>
                <input
                  type="text"
                  value={mealName}
                  onChange={(event) => setMealName(event.target.value)}
                  className="rounded-lg border border-slate-200 bg-slate-50 p-3"
                />
              </label>
              <div className="flex gap-3">
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  ref={mealFileRef}
                  onChange={(event) => handleUpload(TAB_MEAL, event)}
                />
                <button
                  type="button"
                  onClick={() => mealFileRef.current?.click()}
                  className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm font-semibold"
                >
                  Upload meal
                </button>
                <ActionButton
                  disabled={!mealImageUrl}
                  busy={scanningMeal}
                  idleText="Confirm & Log Meal"
                  busyText="Logging..."
                  onClick={handleScanMeal}
                />
              </div>
            </section>
            <aside className="lg:col-span-5 flex flex-col gap-4">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
                <h3 className="text-base font-bold">Latest Meal Result</h3>
                {!latestMeal ? (
                  <p className="text-sm text-slate-500">No meal parsed in this session yet.</p>
                ) : (
                  <>
                    <ul className="space-y-2 text-sm">
                      <li className="flex justify-between">
                        <span className="text-slate-500">Meal</span>
                        <strong className="text-right max-w-[60%]">{latestMeal.meal_name || "-"}</strong>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-slate-500">Calories</span>
                        <strong>{latestMeal.calories || 0} kcal</strong>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-slate-500">Protein</span>
                        <strong>{latestMeal.protein_g || 0} g</strong>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-slate-500">Carbs</span>
                        <strong>{latestMeal.carbs_g || 0} g</strong>
                      </li>
                      <li className="flex justify-between">
                        <span className="text-slate-500">Fat</span>
                        <strong>{latestMeal.fat_g || 0} g</strong>
                      </li>
                    </ul>

                    {latestMeal.highlights?.length > 0 && (
                      <div className="pt-3 border-t border-slate-100 space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
                          What&apos;s Great
                        </p>
                        <ul className="space-y-1.5">
                          {latestMeal.highlights.map((item, i) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                              <Icon name="check_circle" className="text-emerald-500 text-base mt-0.5 shrink-0" />
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {latestMeal.suggestions?.length > 0 && (
                      <div className="pt-3 border-t border-slate-100 space-y-2">
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-600">
                          Suggestions
                        </p>
                        <ul className="space-y-1.5">
                          {latestMeal.suggestions.map((item, i) => (
                            <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                              <Icon name="lightbulb" className="text-amber-500 text-base mt-0.5 shrink-0" />
                              <span>{item}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </div>
            </aside>
          </>
        )}

        {activeTab === TAB_RECEIPT && (
          <>
            <section className="lg:col-span-7 flex flex-col gap-4">
              <CameraFrame imageUrl={receiptImageUrl}>
                {!receiptImageUrl && (
                  <ImagePlaceholder
                    title="Upload a receipt image first"
                    description="Capture button is disabled until an image is uploaded."
                  />
                )}
              </CameraFrame>
              <div className="flex gap-3">
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  ref={receiptFileRef}
                  onChange={(event) => handleUpload(TAB_RECEIPT, event)}
                />
                <button
                  type="button"
                  onClick={() => receiptFileRef.current?.click()}
                  className="px-4 py-3 rounded-xl border border-slate-200 bg-white text-sm font-semibold"
                >
                  Upload receipt
                </button>
                <ActionButton
                  disabled={!receiptImageUrl}
                  busy={scanningReceipt}
                  idleText="Capture Receipt"
                  busyText="Parsing..."
                  onClick={handleScanReceipt}
                />
              </div>
            </section>
            <aside className="lg:col-span-5">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 space-y-3">
                <h3 className="text-base font-bold">Receipt Synced Items</h3>
                {receiptItems.length === 0 ? (
                  <p className="text-sm text-slate-500">No receipt items parsed yet.</p>
                ) : (
                  <ul className="space-y-2 max-h-[420px] overflow-y-auto">
                    {receiptItems.map((item) => (
                      <li
                        key={item.item_id}
                        className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm"
                      >
                        <span className="font-medium">{item.ingredient}</span>
                        <span className="text-slate-500">{item.quantity || "synced"}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
