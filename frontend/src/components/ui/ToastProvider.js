"use client";

import { createContext, useCallback, useContext, useMemo, useReducer, useRef } from "react";
import Icon from "@/components/ui/Icon";
import { createToast, toastReducer } from "@/lib/toast-store.mjs";

const ToastContext = createContext(null);
const EXIT_DELAY_MS = 220;

const TOAST_STYLES = {
  success: {
    icon: "check_circle",
    shell: "border-emerald-200 bg-white/95",
    iconWrap: "bg-emerald-100 text-emerald-700",
    accent: "bg-emerald-500",
  },
  error: {
    icon: "error",
    shell: "border-rose-200 bg-white/95",
    iconWrap: "bg-rose-100 text-rose-700",
    accent: "bg-rose-500",
  },
  info: {
    icon: "info",
    shell: "border-sky-200 bg-white/95",
    iconWrap: "bg-sky-100 text-sky-700",
    accent: "bg-sky-500",
  },
};

function ToastViewport({ toasts, onDismiss }) {
  return (
    <div className="pointer-events-none fixed inset-x-4 top-4 z-[100] flex flex-col items-end gap-3 sm:left-auto sm:right-4 sm:w-full sm:max-w-sm">
      {toasts.map((toast) => {
        const style = TOAST_STYLES[toast.type] || TOAST_STYLES.info;
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto relative w-full overflow-hidden rounded-2xl border px-4 py-4 shadow-[0_20px_50px_-28px_rgba(15,23,42,0.35)] backdrop-blur transition-all duration-200 ${
              style.shell
            } ${toast.visible ? "translate-y-0 opacity-100" : "-translate-y-2 opacity-0"}`}
            role="status"
            aria-live="polite"
          >
            <div className={`absolute inset-y-0 left-0 w-1.5 ${style.accent}`} />
            <div className="flex items-start gap-3 pl-2">
              <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${style.iconWrap}`}>
                <Icon name={style.icon} className="text-[20px]" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold leading-6 text-slate-900">{toast.message}</p>
              </div>
              <button
                type="button"
                onClick={() => onDismiss(toast.id)}
                className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                aria-label="Dismiss notification"
              >
                <Icon name="close" className="text-[18px]" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ToastProvider({ children }) {
  const [toasts, dispatch] = useReducer(toastReducer, []);
  const timersRef = useRef(new Map());

  const clearTimer = useCallback((key) => {
    const timer = timersRef.current.get(key);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(key);
    }
  }, []);

  const remove = useCallback(
    (id) => {
      clearTimer(`dismiss:${id}`);
      clearTimer(`remove:${id}`);
      dispatch({ type: "remove", id });
    },
    [clearTimer],
  );

  const dismiss = useCallback(
    (id) => {
      clearTimer(`dismiss:${id}`);
      dispatch({ type: "dismiss", id });
      clearTimer(`remove:${id}`);
      timersRef.current.set(
        `remove:${id}`,
        setTimeout(() => {
          dispatch({ type: "remove", id });
          timersRef.current.delete(`remove:${id}`);
        }, EXIT_DELAY_MS),
      );
    },
    [clearTimer],
  );

  const push = useCallback(
    (type, message, options = {}) => {
      const toast = createToast({ type, message, duration: options.duration });
      dispatch({ type: "add", toast });
      timersRef.current.set(
        `dismiss:${toast.id}`,
        setTimeout(() => {
          dismiss(toast.id);
        }, toast.duration),
      );
      return toast.id;
    },
    [dismiss],
  );

  const api = useMemo(
    () => ({
      show: (message, options = {}) => push(options.type || "info", message, options),
      success: (message, options = {}) => push("success", message, options),
      error: (message, options = {}) => push("error", message, options),
      info: (message, options = {}) => push("info", message, options),
      dismiss,
      remove,
    }),
    [dismiss, push, remove],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}
