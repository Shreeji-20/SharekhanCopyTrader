# UI Specification

Use this file as the source UI contract when recreating the Sharekhan copy-trading interface in another project. The design is a dense operational dashboard: quiet, dark, data-first, and built for repeated account/order monitoring.

## Design Principles

- Build an application screen first, not a landing page.
- Prioritize scanning, comparison, and fast operation over illustration.
- Keep surfaces flat and restrained. Avoid marketing hero sections, decorative gradients, glass effects, or nested cards.
- Use shadcn/ui-style primitives with Tailwind CSS variables.
- Use neutral/zinc greys only for the base theme. Do not use slate.
- Use color sparingly for status only: emerald for success/live/connected, red for destructive/error, grey/zinc for pending/inactive/paper.
- Cards are only for repeated items, metric blocks, drawers, callback states, and framed tools.

## Typography

Primary font:

```css
@import url("https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap");

body {
  font-family: "Poppins", sans-serif;
}
```

Text scale:

| Use | Tailwind class |
| --- | --- |
| Page title | `text-2xl font-semibold tracking-normal` |
| Section/card title | `text-sm font-medium text-muted-foreground` |
| Body text | `text-sm` |
| Metadata/helper text | `text-xs text-muted-foreground` |
| Table text | `text-sm`, compact row height |

Rules:

- Letter spacing stays normal.
- Do not scale font size with viewport width.
- Avoid oversized text inside dashboards, cards, tables, and drawers.

## Theme Tokens

Use shadcn-compatible CSS variables. The dark theme must be zinc/neutral, pure black and grey toned.

```css
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  --card: 0 0% 100%;
  --card-foreground: 240 10% 3.9%;
  --primary: 240 5.9% 10%;
  --primary-foreground: 0 0% 98%;
  --secondary: 240 4.8% 95.9%;
  --secondary-foreground: 240 5.9% 10%;
  --muted: 240 4.8% 95.9%;
  --muted-foreground: 240 3.8% 46.1%;
  --accent: 240 4.8% 95.9%;
  --accent-foreground: 240 5.9% 10%;
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 0 0% 98%;
  --border: 240 5.9% 90%;
  --input: 240 5.9% 90%;
  --ring: 240 5.9% 10%;
}

.dark {
  --background: 240 10% 3.9%;        /* zinc-950 */
  --foreground: 240 4.8% 95.9%;      /* zinc-100 */
  --card: 240 5.9% 10%;              /* zinc-900 */
  --card-foreground: 240 4.8% 95.9%;
  --primary: 240 4.8% 95.9%;
  --primary-foreground: 240 5.9% 10%;
  --secondary: 240 3.7% 15.9%;       /* zinc-800 */
  --secondary-foreground: 240 4.8% 95.9%;
  --muted: 240 3.7% 15.9%;
  --muted-foreground: 240 5% 64.9%;
  --accent: 240 3.7% 15.9%;
  --accent-foreground: 240 4.8% 95.9%;
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 240 4.8% 95.9%;
  --border: 240 3.7% 15.9%;          /* zinc-800 */
  --input: 240 3.7% 15.9%;
  --ring: 240 4.9% 83.9%;
}
```

Tailwind color mapping:

```ts
colors: {
  border: "hsl(var(--border))",
  input: "hsl(var(--input))",
  ring: "hsl(var(--ring))",
  background: "hsl(var(--background))",
  foreground: "hsl(var(--foreground))",
  primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
  secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
  muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
  accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
  destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
  card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" }
}
```

Radius:

```ts
borderRadius: {
  lg: "8px",
  md: "6px",
  sm: "4px"
}
```

## App Shell

Desktop layout:

- Left sidebar: `w-64 shrink-0 border-r bg-card`.
- Header: `sticky top-0 z-20 h-14 border-b bg-background/95 backdrop-blur`.
- Content: `mx-auto w-full max-w-7xl p-4 sm:p-6`.
- Main app height: `min-h-screen`.

Mobile layout:

- Sidebar becomes an overlay drawer.
- Use an icon-only navigation button with `PanelLeft`.
- Drawer width: `w-72`, background `bg-card`, overlay `bg-black/30`.

Header content:

- Left: navigation trigger and trading status badge.
- Right: theme toggle and sign-out icon buttons.
- Status text must reflect runtime state, for example `Live trading` or `Paper trading`.

## Navigation

Use lucide icons with text labels. Recommended routes for trading/ops apps:

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

Nav item class pattern:

```tsx
"flex h-9 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
```

Active item:

```tsx
"bg-muted text-foreground"
```

## Components

### Buttons

Base:

```tsx
"inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
```

Variants:

| Variant | Class |
| --- | --- |
| Default | `bg-primary text-primary-foreground hover:bg-primary/90` |
| Secondary | `bg-secondary text-secondary-foreground hover:bg-secondary/90` |
| Outline | `border bg-background hover:bg-muted` |
| Ghost | `hover:bg-muted` |
| Destructive | `bg-destructive text-destructive-foreground hover:bg-destructive/90` |

Sizes:

| Size | Class |
| --- | --- |
| Default | `h-9 px-3` |
| Small | `h-8 px-2` |
| Icon | `h-9 w-9 px-0` |

Use icons for operational actions: login, delete, refresh, edit, save, close, open, theme toggle, sign out.

### Badges

Base:

```tsx
"inline-flex h-6 items-center rounded-sm border px-2 text-xs font-medium"
```

Status tones:

| State | Tone |
| --- | --- |
| `CONNECTED`, `ACTIVE`, `LIVE`, `RUNNING`, `SUCCESS`, `READY` | Emerald border/background/text |
| `PENDING`, `PAPER`, `TOKEN_SAVED`, `SKIPPED`, `PAUSED` | Zinc/grey |
| `INACTIVE`, `DISCONNECTED`, `STOPPED` | Muted grey |
| `FAILED`, `ERROR`, `CREDENTIALS_LOCKED` | Destructive red |
| `MASTER`, `COPY`, `DEGRADED` | Accent/secondary, still restrained |

### Cards

Use:

```tsx
"rounded-lg border bg-card text-card-foreground"
```

Card header:

```tsx
"flex items-center justify-between gap-3 p-4"
```

Card content:

```tsx
"p-4 pt-0"
```

Rules:

- Do not place cards inside cards.
- Do not use cards as generic page sections.
- Keep repeated cards compact and information dense.

### Forms

Field wrapper:

```tsx
"grid gap-1.5"
```

Label:

```tsx
"text-xs font-medium text-muted-foreground"
```

Input:

```tsx
"h-9 rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
```

Forms should use explicit fields for structured data. For example proxy configuration must be separate fields:

- Scheme
- Host
- Port
- ID/username
- Password

### Tables

Tables are compact, searchable when useful, and never filled with dummy rows.

Patterns:

- Header text: `text-xs font-medium text-muted-foreground`.
- Body text: `text-sm`.
- Empty state: quiet bordered area with clear one-line copy.
- Detail drawer for deep row payloads.
- Keep action buttons icon-first and right aligned.

## Page Patterns

### Dashboard

- Metric cards in a responsive grid.
- Empty states instead of demo charts when no data exists.
- Operational statuses should be visible without opening details.

### Accounts

- List accounts as accordions.
- Top actions: refresh, create account, login all/selected.
- Row actions: login, edit, delete.
- Accordion content displays stored/masked credential, token, proxy, and profile details.
- Expanding an account must not trigger expensive broker token exchange.

### Live Copy

- Left/top controls for master account, copy groups, dry-run/live mode, duplicate behavior.
- Session controls: start, pause, resume, stop, delete.
- Stream status panel must show connection, modules, ack subscribe, message counts, customer/proxy presence, and last event time.
- Show recent outbound WebSocket frames and recent inbound stream payloads in compact diagnostic areas. The outbound order-streaming request must be visible as `{"action":"ack","key":[""],"value":["CUSTOMER_ID"]}` after module readiness.

### Callback/Transient Screens

- Center a single compact card.
- Use icon + title + badge at the top.
- Show account, customer, token status, and login id.
- If a callback tab cannot access the app session, stay on the success screen and show a Close button instead of redirecting into the authenticated app.

## Interaction Rules

- API-backed screens must show loading, error, and empty states.
- Mutations should show toast feedback.
- Destructive actions must confirm in the browser or modal.
- React Query default focus refetch is useful for account lists after broker login.
- Keep disabled states visible with opacity and blocked pointer events.
- Runtime state should be reflected in labels, not hardcoded. Example: header must show `Live trading` when live orders are enabled.

## Icons

Use lucide-react icons:

| Action | Icon |
| --- | --- |
| Navigation | `PanelLeft` |
| Theme | `Sun`, `Moon` |
| Sign out | `LogOut` |
| Login/connect | `LogIn`, `RadioTower` |
| Create | `Plus` |
| Refresh | `RefreshCw` |
| Edit | `Edit` |
| Delete | `Trash2` |
| Save | `Save` |
| Close | `X` |
| Open external | `ExternalLink` |
| Expand/collapse | `ChevronDown` |
| Success | `CheckCircle2` |
| Error | `AlertTriangle` |
| Loading | `Loader2` |

## Copy Guidelines

- Use short operational labels: `Login all`, `Login selected`, `Start`, `Pause`, `Resume`, `Stop`, `Delete`.
- Avoid explanatory paragraphs inside the app.
- Use precise error text from the backend when possible.
- Mask secrets and tokens everywhere.

## Implementation Checklist

1. Install Tailwind, shadcn-style primitives, `class-variance-authority`, `lucide-react`, `next-themes`, and Poppins.
2. Add the exact CSS variables above.
3. Set `darkMode: ["class"]` in Tailwind.
4. Build shared primitives: Button, Badge, Card, Input, Table.
5. Build the AppShell first: sidebar, sticky header, status badge, theme toggle, sign-out.
6. Implement screens with live API data, empty states, and no dummy rows.
7. Verify mobile sidebar, table overflow, long token/account text truncation, and dark mode contrast.
8. Keep the UI neutral/zinc. Do not introduce slate or blue-tinted grey surfaces.
