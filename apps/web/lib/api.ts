const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "access_token";
const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

function parseBody(text: string) {
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorMessage(status: number, body: unknown, fallback: string) {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as {detail?: unknown}).detail;
    if (detail === "Not authenticated") return "Please sign in before continuing.";
    if (detail === "Could not validate credentials") return "Your session expired. Please sign in again.";
    if (typeof detail === "string") return detail;
    return JSON.stringify(detail);
  }
  if (typeof body === "string" && body) return body;
  if (status === 401) return "Please sign in before continuing.";
  return fallback;
}

export async function apiFetch<T>(path: string, init: RequestInit & {timeoutMs?: number} = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const timeoutMs = init.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  init.signal?.addEventListener("abort", () => controller.abort(), {once: true});
  const fetchInit: RequestInit = {...init};
  delete (fetchInit as RequestInit & {timeoutMs?: number}).timeoutMs;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {...fetchInit, headers, signal: controller.signal});
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(408, "API request timed out. Please try again.");
    }
    if (error instanceof TypeError) {
      throw new ApiError(0, `Could not reach the API at ${API_URL}. Check that the backend is running.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
  const text = await response.text();
  const body = parseBody(text);
  if (!response.ok) {
    if (response.status === 401) clearAccessToken();
    throw new ApiError(response.status, errorMessage(response.status, body, response.statusText), body);
  }
  return body as T;
}
