const DEFAULT_BACKEND_ORIGIN = "http://localhost:8000";
const PRODUCTION_BACKEND_ORIGIN = "https://genai.yiw.me";
const DEFAULT_USER_ID = "demo-user";
const AUTH_SESSION_STORAGE_KEY = "agentic_auth_session_v1";

function isLikelyHostedFrontend() {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname || "";
  return host && host !== "localhost" && host !== "127.0.0.1";
}

function normalizeBaseUrl() {
  const configured = (process.env.NEXT_PUBLIC_API_BASE_URL || "").trim();
  if (configured) {
    if (configured.endsWith("/api/v1")) {
      return configured;
    }
    return `${configured.replace(/\/$/, "")}/api/v1`;
  }

  if (process.env.NODE_ENV === "production" || isLikelyHostedFrontend()) {
    return `${PRODUCTION_BACKEND_ORIGIN}/api/v1`;
  }

  return `${DEFAULT_BACKEND_ORIGIN}/api/v1`;
}

export const API_BASE_URL = normalizeBaseUrl();

function decodeJwtClaims(token) {
  if (!token || typeof token !== "string") return null;
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const normalized = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4 || 4)) % 4);
    const json =
      typeof window === "undefined"
        ? Buffer.from(padded, "base64").toString("utf-8")
        : atob(padded);
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function readSessionFromStorage() {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(AUTH_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function writeSessionToStorage(session) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function clearAuthSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
}

export function getAuthSession() {
  const stored = readSessionFromStorage();
  if (!stored) return null;
  if (stored.user_id) return stored;

  const claims = decodeJwtClaims(stored.id_token || stored.access_token || "");
  if (!claims?.sub) return stored;

  const next = {
    ...stored,
    user_id: claims.sub,
    email: claims.email || stored.email || null,
  };
  writeSessionToStorage(next);
  return next;
}

export function hasAuthSession() {
  const session = getAuthSession();
  return Boolean(session?.id_token || session?.access_token);
}

export function saveAuthSession(payload) {
  const idToken = String(payload?.id_token || payload?.idToken || "");
  const accessToken = String(payload?.access_token || payload?.accessToken || "");
  const refreshToken = String(payload?.refresh_token || payload?.refreshToken || "");
  const token = idToken || accessToken;
  if (!token) {
    throw new Error("Missing Cognito token in login response");
  }

  const claims = decodeJwtClaims(token) || {};
  const session = {
    id_token: idToken || null,
    access_token: accessToken || null,
    refresh_token: refreshToken || null,
    token_type: payload?.token_type || "Bearer",
    expires_in: Number(payload?.expires_in || 3600),
    user_id: claims.sub || payload?.user_id || "",
    email: claims.email || payload?.email || null,
  };
  writeSessionToStorage(session);
  return session;
}

function resolveBearerToken() {
  const envBearer = (process.env.NEXT_PUBLIC_API_BEARER_TOKEN || "").trim();
  if (envBearer) return envBearer;
  const session = getAuthSession();
  return session?.id_token || session?.access_token || "";
}

export function getCurrentUserId() {
  const session = getAuthSession();
  if (session?.user_id) return session.user_id;
  return (process.env.NEXT_PUBLIC_DEMO_USER_ID || DEFAULT_USER_ID).trim() || DEFAULT_USER_ID;
}

export function getDemoUserId() {
  return getCurrentUserId();
}

function buildHeaders(hasJsonBody = false) {
  const headers = {};
  if (hasJsonBody) {
    headers["Content-Type"] = "application/json";
  }

  const bearer = resolveBearerToken();
  if (bearer) {
    headers.Authorization = `Bearer ${bearer}`;
    return headers;
  }

  const allowDemoAuth = (process.env.NEXT_PUBLIC_ALLOW_DEMO_AUTH || "").trim() === "true";
  if (allowDemoAuth) {
    const demoUserId = getCurrentUserId();
    headers["X-Demo-User"] = demoUserId;
    headers["X-Demo-User-Id"] = demoUserId;
  }

  return headers;
}

async function request(path, { method = "GET", body, cache = "no-store" } = {}) {
  const hasBody = body !== undefined;
  const url = `${API_BASE_URL}${path}`;
  const timeoutMs = method === "GET" ? 30000 : 120000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      method,
      headers: buildHeaders(hasBody),
      body: hasBody ? JSON.stringify(body) : undefined,
      cache,
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timeout after ${Math.round(timeoutMs / 1000)}s`);
    }
    const detail = error instanceof Error ? error.message : "Unknown network error";
    throw new Error(
      `Failed to fetch. Please verify backend reachability/CORS for ${API_BASE_URL}. ${detail}`
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : null;
  const textPayload = payload ? "" : await response.text().catch(() => "");

  if (!response.ok) {
    const detail =
      (payload && (payload.detail || payload.message)) ||
      textPayload.trim() ||
      `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(detail);
  }

  return payload;
}

export function requestEmailCode(email) {
  return request("/auth/request-code", { method: "POST", body: { email } });
}

export function verifyEmailCode(email, code, session) {
  return request("/auth/verify-code", { method: "POST", body: { email, code, session } });
}

export function registerWithEmail(payload) {
  return request("/auth/register", { method: "POST", body: payload });
}

export function confirmEmailCode(payload) {
  return request("/auth/confirm-email", { method: "POST", body: payload });
}

export function resendEmailCode(payload) {
  return request("/auth/resend-code", { method: "POST", body: payload });
}

export async function loginWithEmail(payload) {
  const response = await request("/auth/login", { method: "POST", body: payload });
  saveAuthSession(response);
  return response;
}

export async function refreshAuthToken() {
  const session = getAuthSession();
  if (!session?.refresh_token) {
    throw new Error("Missing refresh token");
  }
  const response = await request("/auth/refresh", {
    method: "POST",
    body: {
      refresh_token: session.refresh_token,
      email: session.email || undefined,
    },
  });
  return saveAuthSession({
    ...session,
    ...response,
    refresh_token: response.refresh_token || session.refresh_token,
  });
}

export function getCurrentUser() {
  return request("/auth/me");
}

export function getProfile(userId) {
  return request(`/profiles/${encodeURIComponent(userId)}`);
}

export function upsertProfile(userId, payload) {
  return request(`/profiles/${encodeURIComponent(userId)}`, { method: "PUT", body: payload });
}

export function getGoals(userId) {
  return request(`/goals/${encodeURIComponent(userId)}`);
}

export function upsertGoals(userId, payload) {
  return request(`/goals/${encodeURIComponent(userId)}`, { method: "PUT", body: payload });
}

export function submitFridgeScan(payload) {
  return request("/inputs/fridge-scan", { method: "POST", body: payload });
}

export function submitMealScan(payload) {
  return request("/inputs/meal-scan", { method: "POST", body: payload });
}

export function submitReceiptScan(payload) {
  return request("/inputs/receipt-scan", { method: "POST", body: payload });
}

export function getInputJob(jobId) {
  return request(`/inputs/jobs/${encodeURIComponent(jobId)}`);
}

export function getPantry() {
  return request("/inputs/pantry");
}

export function getSpoilageAlerts() {
  return request("/inputs/spoilage-alerts");
}

export function getTodayNutrition() {
  return request("/inputs/nutrition/today");
}

export function deletePantryItem(itemId) {
  return request(`/inputs/pantry/${itemId}`, { method: "DELETE" });
}

export function sendChatMessage(message, { autoReplan = true } = {}) {
  const query = autoReplan ? "?auto_replan=true" : "?auto_replan=false";
  return request(`/inputs/chat-message${query}`, { method: "POST", body: { message } });
}

export function getLatestChatMessages(limit = 20) {
  return request(`/inputs/chat-messages/latest?limit=${limit}`);
}

export function createRecommendation(payload) {
  return request("/planner/recommendations", { method: "POST", body: payload });
}

export function getLatestRecommendation(userId) {
  return request(`/planner/recommendations/latest/${encodeURIComponent(userId)}`);
}

export function getRecommendation(recommendationId) {
  return request(`/planner/recommendations/${encodeURIComponent(recommendationId)}`);
}

export function getRecommendationHistory(userId, limit = 20) {
  return request(
    `/planner/recommendations/history/${encodeURIComponent(userId)}?limit=${limit}`
  );
}

export async function pollInputJob(jobId, { timeoutMs = 10000, intervalMs = 500 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const job = await getInputJob(jobId);
    if (job.status === "COMPLETED" || job.status === "FAILED") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Input processing timeout. Please retry.");
}
