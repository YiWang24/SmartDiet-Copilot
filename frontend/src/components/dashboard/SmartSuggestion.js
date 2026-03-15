import Icon from "@/components/ui/Icon";

export default function SmartSuggestion({
  alerts = [],
  isGenerating = false,
  onGenerate,
}) {
  const criticalAlerts = alerts.filter((a) => a.expires_in_days <= 1);
  const soonAlerts = alerts.filter((a) => a.expires_in_days > 1 && a.expires_in_days <= 3);
  const hasAlerts = alerts.length > 0;

  const badgeAlerts = criticalAlerts.length > 0 ? criticalAlerts : soonAlerts.slice(0, 2);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${hasAlerts ? "bg-amber-100 text-amber-600" : "bg-slate-100 text-slate-400"}`}>
          <Icon name={hasAlerts ? "warning" : "check_circle"} className="text-lg" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-900 leading-tight">
            {hasAlerts
              ? `${alerts.length} item${alerts.length > 1 ? "s" : ""} expiring soon`
              : "Pantry looks fresh"}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {hasAlerts
              ? "Generate a rescue meal to reduce food waste"
              : "Scan your fridge to track expiry dates"}
          </p>
        </div>
      </div>

      {badgeAlerts.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {badgeAlerts.map((a) => (
            <span
              key={a.ingredient}
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                a.expires_in_days <= 1
                  ? "bg-red-100 text-red-700"
                  : "bg-amber-100 text-amber-700"
              }`}
            >
              <Icon name="schedule" className="text-xs" />
              {a.ingredient}
              <span className="opacity-70">
                {a.expires_in_days <= 1 ? "today" : `${a.expires_in_days}d`}
              </span>
            </span>
          ))}
          {alerts.length > badgeAlerts.length && (
            <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium bg-slate-100 text-slate-500">
              +{alerts.length - badgeAlerts.length} more
            </span>
          )}
        </div>
      )}

      <button
        onClick={onGenerate}
        disabled={isGenerating || !hasAlerts}
        className="flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-all duration-200 hover:bg-primary/90 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100"
      >
        {isGenerating ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            Generating...
          </>
        ) : (
          <>
            <Icon name="auto_awesome" className="text-base" />
            {hasAlerts ? "Generate Rescue Recipe" : "No alerts to rescue"}
          </>
        )}
      </button>
    </div>
  );
}
