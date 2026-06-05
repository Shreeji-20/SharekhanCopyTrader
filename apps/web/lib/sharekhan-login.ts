export type PendingSharekhanLogin = {
  state: string;
  accountId?: string;
  accountName?: string;
  createdAt: number;
};

export type SharekhanCallbackParams = {
  state: string | null;
  accountId: string | null;
  requestToken: string | null;
  detectedKeys: string[];
};

const PENDING_LOGINS_KEY = "sharekhan_pending_logins";
const TAB_PENDING_LOGIN_KEY = "sharekhan_pending_login";
const PENDING_MAX_AGE_MS = 60 * 60 * 1000;

const STATE_KEYS = ["state", "State", "STATE"];
const ACCOUNT_ID_KEYS = ["account_id", "accountId", "AccountId", "ACCOUNT_ID"];
const REQUEST_TOKEN_KEYS = [
  "request_token",
  "requestToken",
  "RequestToken",
  "REQUEST_TOKEN",
  "requesttoken",
  "token",
  "Token",
  "TOKEN",
  "request-token"
];

function safeJsonParse<T>(value: string | null): T | null {
  if (!value) return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

function isFresh(login: PendingSharekhanLogin) {
  return Date.now() - login.createdAt <= PENDING_MAX_AGE_MS;
}

function isSamePendingLogin(current: PendingSharekhanLogin, next: PendingSharekhanLogin) {
  if (current.accountId && next.accountId) return current.accountId === next.accountId;
  return current.state === next.state && current.accountName === next.accountName;
}

function paramsFromText(value: string) {
  const cleaned = value.replace(/^[?#]/, "");
  const queryStart = cleaned.indexOf("?");
  return new URLSearchParams(queryStart >= 0 ? cleaned.slice(queryStart + 1) : cleaned);
}

function getFirst(params: URLSearchParams, keys: string[]) {
  for (const key of keys) {
    const value = params.get(key);
    if (value) return value;
  }
  return null;
}

function collectKeys(params: URLSearchParams) {
  return Array.from(new Set(Array.from(params.keys())));
}

export function extractStateFromLoginUrl(loginUrl: string) {
  try {
    return new URL(loginUrl).searchParams.get("state");
  } catch {
    return null;
  }
}

export function extractSharekhanCallbackParams(href: string): SharekhanCallbackParams {
  const params = new URLSearchParams();
  try {
    const url = new URL(href);
    url.searchParams.forEach((value, key) => params.append(key, value));
    if (url.hash) {
      paramsFromText(url.hash).forEach((value, key) => params.append(key, value));
    }
  } catch {
    paramsFromText(href).forEach((value, key) => params.append(key, value));
  }

  return {
    state: getFirst(params, STATE_KEYS),
    accountId: getFirst(params, ACCOUNT_ID_KEYS),
    requestToken: getFirst(params, REQUEST_TOKEN_KEYS),
    detectedKeys: collectKeys(params)
  };
}

export function rememberPendingSharekhanLogin(login: Omit<PendingSharekhanLogin, "createdAt">) {
  if (typeof window === "undefined") return;
  const pending: PendingSharekhanLogin = {...login, createdAt: Date.now()};
  const current = safeJsonParse<PendingSharekhanLogin[]>(window.localStorage.getItem(PENDING_LOGINS_KEY)) ?? [];
  const next = [pending, ...current.filter((item) => !isSamePendingLogin(item, pending) && isFresh(item))].slice(0, 25);
  window.localStorage.setItem(PENDING_LOGINS_KEY, JSON.stringify(next));
}

export function rememberPendingSharekhanLoginInWindow(
  target: Window | null,
  login: Omit<PendingSharekhanLogin, "createdAt">
) {
  if (!target) return;
  try {
    target.sessionStorage.setItem(TAB_PENDING_LOGIN_KEY, JSON.stringify({...login, createdAt: Date.now()}));
  } catch {
    // Some popup/browser configurations block access to the child tab. The shared localStorage fallback still exists.
  }
}

export function resolvePendingSharekhanLogin(): {login: PendingSharekhanLogin | null; multiple: boolean} {
  if (typeof window === "undefined") return {login: null, multiple: false};

  const tabLogin = safeJsonParse<PendingSharekhanLogin>(window.sessionStorage.getItem(TAB_PENDING_LOGIN_KEY));
  if (tabLogin && isFresh(tabLogin)) return {login: tabLogin, multiple: false};

  const pending = (safeJsonParse<PendingSharekhanLogin[]>(window.localStorage.getItem(PENDING_LOGINS_KEY)) ?? [])
    .filter(isFresh);
  window.localStorage.setItem(PENDING_LOGINS_KEY, JSON.stringify(pending));
  if (pending.length === 1) return {login: pending[0], multiple: false};
  return {login: null, multiple: pending.length > 1};
}

export function forgetPendingSharekhanLogin(state: string | null, accountId?: string | null) {
  if (typeof window === "undefined") return;
  const pending = (safeJsonParse<PendingSharekhanLogin[]>(window.localStorage.getItem(PENDING_LOGINS_KEY)) ?? [])
    .filter((login) => {
      if (accountId) return login.accountId !== accountId;
      return state ? login.state !== state : true;
    });
  window.localStorage.setItem(PENDING_LOGINS_KEY, JSON.stringify(pending));

  const tabLogin = safeJsonParse<PendingSharekhanLogin>(window.sessionStorage.getItem(TAB_PENDING_LOGIN_KEY));
  if (tabLogin && (accountId ? tabLogin.accountId === accountId : tabLogin.state === state)) {
    window.sessionStorage.removeItem(TAB_PENDING_LOGIN_KEY);
  }
}
