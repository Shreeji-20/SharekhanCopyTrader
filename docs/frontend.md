# Frontend

The frontend lives in `apps/web`. It is a Next.js App Router application for operators to manage accounts, copy groups, risk settings, order views, portfolio views, and logs.

## Runtime

| Item | Value |
| --- | --- |
| Framework | Next.js 15, React 19 |
| Package | `@copytrading/web` |
| Dev command | `npm --workspace apps/web run dev` |
| Build command | `npm --workspace apps/web run build` |
| Compose port | `3000` |
| API base env | `NEXT_PUBLIC_API_URL`, default `http://localhost:8000` |

## App Structure

| Path | Purpose |
| --- | --- |
| `app/layout.tsx` | Root layout, providers, global CSS. |
| `app/page.tsx` | Redirects `/` to `/dashboard`. |
| `app/login/page.tsx` | Login/register form that stores JWT in `localStorage`. |
| `app/dashboard/page.tsx` | Live metric cards from `/dashboard/metrics` plus an empty state for copy-flow events. |
| `app/accounts/page.tsx` | Live account accordion with edit, delete, refresh, item login, selected/all login, stored Sharekhan login/token details, and credential recovery states. |
| `app/accounts/new/page.tsx` | Account creation form that calls `POST /accounts` and redirects to the account list. |
| `app/sharekhan/callback/page.tsx` | Sharekhan redirect target that saves the returned raw request token for the matching account and triggers access-token/profile exchange. |
| `app/copy-groups/page.tsx` | Live copy groups table from `/copy-groups`. |
| `app/copy-groups/[id]/page.tsx` | Live copy group metadata view with an empty member-table state. |
| `app/live-copy/page.tsx` | Live copy session console with dry-run/live switch, session controls, stream diagnostics, master events, and copied order attempts. |
| `app/orders/master/page.tsx` | Live master order table from `/orders/master`. |
| `app/orders/copy/page.tsx` | Live copy order table from `/orders/copy`. |
| `app/positions/page.tsx` | Live positions table from `/positions`. |
| `app/holdings/page.tsx` | Live holdings table from `/holdings`. |
| `app/trades/page.tsx` | Live trades table from `/trades`. |
| `app/risk-settings/page.tsx` | Client-side risk settings UI scaffold. |
| `app/settings/page.tsx` | Client-side security/order-mode settings scaffold. |
| `app/logs/page.tsx` | Live audit log table from `/logs`. |

## Shared Components

| Component | Purpose |
| --- | --- |
| `components/layout/app-shell.tsx` | Sidebar, mobile nav overlay, sticky header, theme toggle. |
| `components/layout/page.tsx` | Page wrapper with title/actions inside `AppShell`. |
| `components/data-table.tsx` | Generic searchable, status-filterable, paginated table with detail drawer. |
| `components/ui/button.tsx` | Button variants and sizes using `class-variance-authority`. |
| `components/ui/card.tsx` | Card primitives. |
| `components/ui/badge.tsx` | Status/type badge tones. |
| `components/ui/input.tsx` | Input primitive. |
| `components/ui/table.tsx` | Table primitives. |

## Providers

`components/layout/providers.tsx` installs:

- `ThemeProvider` from `next-themes`.
- `QueryClientProvider` from TanStack React Query.
- `Toaster` from Sonner.

## API Client

`lib/api.ts` exports `apiFetch<T>`.

Behavior:

1. Uses `NEXT_PUBLIC_API_URL` or `http://localhost:8000`.
2. Sets `Content-Type: application/json`.
3. On the client, reads `access_token` from `window.localStorage`.
4. Adds `Authorization: Bearer {token}` when present.
5. Parses structured API errors and clears the stored token on `401`.

There is no refresh token flow.

## Navigation

The sidebar includes:

- Dashboard
- Accounts
- New Account
- Copy Groups
- Live Copy
- Master Orders
- Copy Orders
- Positions
- Holdings
- Trades
- Risk Settings
- Settings
- Logs

The root path redirects to dashboard.

## Live Data Status

| Screen | Current data source |
| --- | --- |
| Login | Live API: `POST /auth/login` and `POST /auth/register` |
| Dashboard | Live API: `GET /dashboard/metrics`; no demo fallback |
| New Account | Live API: `POST /accounts` |
| Accounts | Live API: `GET/PATCH/DELETE /accounts`, `POST /accounts/{id}/sharekhan/login-url` |
| Sharekhan callback | Live API: `POST /accounts/sharekhan/callback` |
| Copy Groups | Live API: `GET /copy-groups` |
| Copy Group Detail | Live API: `GET /copy-groups/{id}` |
| Live Copy | Live API: `GET/POST/DELETE /copy-sessions`, `POST /copy-groups/validate`, stream status through `GET /copy-sessions/{id}/stream-status` |
| Master Orders | Live API: `GET /orders/master` |
| Copy Orders | Live API: `GET /orders/copy` |
| Positions | Live API: `GET /positions` |
| Holdings | Live API: `GET /holdings` |
| Trades | Live API: `GET /trades` |
| Risk Settings | Local state and toast only |
| Settings | Local state, browser confirm, and toast only |
| Logs | Live API: `GET /logs` |

## Styling

The app uses Tailwind CSS with CSS variables defined in `app/globals.css`.

Theme tokens include:

- `background`
- `foreground`
- `card`
- `primary`
- `secondary`
- `muted`
- `accent`
- `destructive`
- `border`
- `input`
- `ring`

Border radii are constrained to:

- `lg`: `8px`
- `md`: `6px`
- `sm`: `4px`

## User Workflows Exposed By UI

### Sign In

1. User enters email and password.
2. Frontend calls `POST /auth/login`.
3. Returned access token is stored in `localStorage`.
4. User is sent to `/dashboard`.

### Create Broker Account

1. User opens `/accounts/new`.
2. User fills account name, API key, Secure Key, optional vendor key, optional customer/channel user overrides, and optional proxy scheme/host/port/ID/password fields.
3. User selects `MASTER` or `COPY`.
4. Frontend calls `POST /accounts` and redirects to `/accounts`.

### Manage Broker Accounts

1. User opens `/accounts`.
2. Frontend calls `GET /accounts`.
3. Account rows can be selected for batch actions.
4. Login on an account item calls `POST /accounts/{account_id}/sharekhan/login-url` and opens that account's Sharekhan login URL.
5. Login all/selected calls the same login-url endpoint for either selected rows or every account when no row is selected.
6. Opening an account accordion displays the stored customer ID, login ID, masked request/access/refresh token status, token expiry, and last connection time from the account list response. It does not call Sharekhan's access-token endpoint.
7. Accounts with unreadable encrypted fields show `CREDENTIALS_LOCKED`; edit the account, re-enter the API Key/Secure Key, and re-enter or clear optional vendor/proxy details to recover.
8. Edit opens a drawer and sends `PATCH /accounts/{account_id}`.
9. Delete confirms in the browser and sends `DELETE /accounts/{account_id}`.

### Complete Sharekhan Login

1. Sharekhan redirects the browser to `/sharekhan/callback` after its own login completes.
2. The callback page reads the optional `state`, optional account id, and request token from the query string or hash fragment. It accepts common token keys such as `request_token`, `requestToken`, and `token`.
3. Frontend resolves the pending account id stored before Sharekhan login and calls public endpoint `POST /accounts/sharekhan/callback`.
4. The API saves the raw request token, then immediately asks broker-router to decrypt/convert it, exchange it for an access token, and store the returned profile identity.
5. On success, the callback page returns the user to `/accounts`.
6. The account accordion later shows those stored/masked details without re-running access-token exchange.

Configure the Sharekhan app redirect URL to the deployed frontend callback URL, for example `http://localhost:3000/sharekhan/callback` in local development.

Before navigating to Sharekhan, the Accounts page stores the pending account id in the opened tab and local storage. The backend also stores a random numeric state on the account, so the callback can still identify the account when the browser loses that pending-tab storage.

### Dashboard Monitoring

Dashboard fetches aggregate metrics from the API and displays:

- Master orders today.
- Copied success count.
- Failed copy count.
- Active copy accounts.
- Open positions.
- Total PnL.
- Broker connection status.

The copy-flow panel shows an empty state until a real event series endpoint is added.

### Live Copy Monitoring

1. User opens `/live-copy`.
2. Frontend loads accounts, copy groups, existing copy sessions, and server trading mode.
3. Starting a session validates selected groups, then calls `POST /copy-sessions/start`.
4. Session controls call pause, resume, stop, or delete endpoints.
5. Stream Status polls `GET /copy-sessions/{session_id}/stream-status`.
6. Stream diagnostics display connection state, module readiness, order ack subscription state, message counts, latest error, recent outbound frames, and recent inbound frames. The outbound order-streaming request should appear in sent frames as `{"action":"ack","key":[""],"value":["CUSTOMER_ID"]}`.

## Auth And Routing Notes

- App-shell pages verify `localStorage.access_token` with `/auth/me`, cache the verified token for the current tab, and redirect to `/login` when no valid session exists.
- The login page can create a user through `POST /auth/register`, then immediately signs in.
- Authenticated API calls fail if no token exists or the token is invalid.
- `localStorage` is the only token storage.
- The app exposes a sign-out button in the shell header.

## Implementation Notes

- The demo data module has been removed. Screens with no persisted data show empty states.
- Account list responses include `credentials_readable`; the UI maps `false` to `CREDENTIALS_LOCKED` instead of failing the whole account list.
- Live Copy shows both recent outbound WebSocket frames and recent inbound stream messages so module/ack subscription issues can be diagnosed without opening container logs.
- Copy group member management and risk settings still need full live form workflows.

## Integration Checklist For Future Work

1. Add forms for copy group creation, member management, and copy settings patching.
2. Connect risk settings UI to `GET/PATCH /copy-settings/{copy_account_id}`.
3. Connect `/ws/live` or a future live endpoint for real-time order/tick updates.
4. Add optimistic states and richer loading skeletons for operational screens.
