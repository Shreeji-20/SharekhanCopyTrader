# Frontend

The frontend lives in `apps/web`. It is a Next.js App Router application for operators to manage accounts, copy groups, live copy sessions, Script Master watchlists, risk settings, portfolio views, and logs.

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
| `app/script-master/page.tsx` | Debounced Script Master search with account selection, full instrument details, add states, and an account-specific watchlist tab. |
| `app/positions/page.tsx` | Live positions table from `/positions`. |
| `app/holdings/page.tsx` | Live holdings table from `/holdings`. |
| `app/trades/page.tsx` | Live trades table from `/trades`. |
| `app/risk-settings/page.tsx` | Client-side risk settings UI scaffold. |
| `app/settings/page.tsx` | Runtime security/order-mode status plus admin-only complete user archive export/import controls. |
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
- Script Master
- Copy Groups
- Live Copy
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
| Copy Group Detail | Live API: `GET /copy-groups/{id}`, `POST /copy-groups/{id}/members`, `PATCH /copy-groups/{id}/members/{member_id}`, `DELETE /copy-groups/{id}/members/{member_id}` |
| Live Copy | Live API: `GET/POST/DELETE /copy-sessions`, `POST /copy-groups/validate`, stream status through `GET /copy-sessions/{id}/stream-status` |
| Script Master | Live API: `GET /script-master/search`, `POST/GET/DELETE /script-master/watchlist` |
| Positions | Live API: `GET /positions` |
| Holdings | Live API: `GET /holdings` |
| Trades | Live API: `GET /trades` |
| Risk Settings | Legacy placeholder. Production risk settings are edited per copy account inside `/copy-groups/{id}`. |
| Settings | Live API: `GET /system/trading-mode`, `GET /auth/me`, `GET /users/export`, `POST /users/import` |
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

- Active copy accounts.
- Open positions.
- Total PnL.
- Broker connection status.

The copy-flow panel shows an empty state until a real event series endpoint is added.

### Copy Group Risk Settings

1. User opens `/copy-groups/{id}`.
2. Frontend loads the group detail, member list, group-scoped copy settings, accounts, and validation warnings.
3. Adding a copy account sends `POST /copy-groups/{id}/members` with both `copy_account_id` and initial `copy_setting`.
4. Each member panel edits only that member's `(copy_group_id, copy_account_id)` settings.
5. Saving a member sends `PATCH /copy-groups/{id}/members/{member_id}` with `is_enabled` and `copy_setting`.
6. The UI supports sizing mode, multiplier, fixed quantity, capital percent, min/max quantity, max trades per day, max daily loss, max order value, side filters, product filters, product mapping, symbol allow/block lists, price mode, slippage, setting enabled, member enabled, and auto-squareoff flag.
7. Removing a member sends `DELETE /copy-groups/{id}/members/{member_id}` and the backend deletes the matching settings row.

### Live Copy Monitoring

1. User opens `/live-copy`.
2. Frontend loads accounts, copy groups, existing copy sessions, and server trading mode.
3. Starting a session validates selected groups, then calls `POST /copy-sessions/start`.
4. Session controls call pause, resume, stop, or delete endpoints.
5. Stream Status polls `GET /copy-sessions/{session_id}/stream-status`.
6. Stream diagnostics display connection state, module readiness, order ack subscription state, message counts, latest error, recent outbound frames, and recent inbound frames. The outbound order-streaming request should appear in sent frames as `{"action":"ack","key":[""],"value":["CUSTOMER_ID"]}`.

### Script Master Search And Watchlist

1. User opens `/script-master` and selects an active broker account.
2. Search input is debounced by 350 ms and activates after two characters.
3. Results include normalized Script Master fields and an expandable raw-payload view.
4. Add buttons show `Add`, `Loading`, or `Added` using account-specific watchlist state returned by the API.
5. The Watch List tab loads saved instruments for the selected account and exposes an icon-only remove action.
6. Both tables show loading, error, and empty states and use horizontal scrolling for the full instrument schema on narrow screens.

See [Script Master Search And Watchlist](script-master-search-and-watchlist.md) for backend ownership and persistence behavior.

### User Archive Administration

1. Settings loads `/auth/me` and renders User Archive only for `ADMIN`.
2. Export calls `GET /users/export`, formats the response JSON, and downloads it with a timestamped filename.
3. File selection accepts JSON up to 10 MB and keeps the import action disabled until a file is selected.
4. Import requires a browser confirmation because it can replace password hashes, roles, active state, IDs, and timestamps.
5. A successful import displays Total, Created, Updated, and Unchanged counts.

The exported file contains credential hashes and must not be committed or shared casually. See [User Import And Export](user-import-export.md).

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
- Script Master search keeps the wide instrument schema in one horizontally scrollable table and preserves provider-specific fields through an expandable raw JSON cell.
- Copy group detail uses a responsive member-panel layout with bounded controls instead of a wide table, so risk settings remain editable on smaller screens.

## Integration Checklist For Future Work

1. Connect `/ws/live` or a future live endpoint for real-time order/tick updates.
2. Add optimistic states and richer loading skeletons for operational screens.
3. Replace or redirect the legacy standalone Risk Settings placeholder now that production risk settings are group-member scoped.
