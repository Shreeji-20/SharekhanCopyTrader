# Script Master Search And Watchlist

This feature lets an authenticated operator search the normalized Sharekhan Script Master cache and save instruments to a watchlist for a selected broker account. The UI is available at `/script-master`.

## Data Scope

Script Master instruments and watchlist entries have different ownership rules:

- `script_master_instruments` is the existing exchange-scoped cache populated by login warm-up or manual refresh. It is not duplicated per broker account.
- Search validates that the selected `account_id` belongs to the current user, then queries the shared normalized cache.
- `script_master_watchlist_items` is scoped by both application user and broker account.
- The database unique constraint on `(user_id, account_id, exchange, scrip_code)` prevents duplicate watchlist entries.
- Administrators may select accounts allowed by the existing account authorization helper, but watchlist rows still belong to the authenticated application user who created them.

Script Master refresh deletes and reinserts exchange rows, so cache-row UUIDs are not durable identifiers. A watchlist entry therefore stores `exchange`, `scrip_code`, and a JSON instrument snapshot. Watchlist reads join the current cache by `(exchange, scrip_code)` and fall back to the saved snapshot if the cache row is temporarily missing.

## Search API

```http
GET /script-master/search?query=idea&account_id={account_id}&limit=50
Authorization: Bearer {token}
```

Behavior:

- Search terms shorter than two trimmed characters return an empty list.
- Default result limit is `50`; accepted values are `1` through `100`.
- Matching is case-insensitive across trading symbol, symbol/company name, underlying symbol, scrip code/token, and ISIN.
- Results are ordered by trading symbol, exchange, expiry, and strike.
- When `account_id` is supplied, each row includes `is_watchlisted` and `watchlist_id` for that account.
- The response includes normalized fields plus `raw_payload_json`, so provider-specific Script Master fields remain inspectable.

Normalized fields include exchange, segment, scrip code, trading symbol, symbol name, underlying, instrument type, option type, strike, expiry, lot size, tick size, ISIN, refresh timestamps, and the raw row.

## Watchlist API

Add an instrument:

```http
POST /script-master/watchlist
Authorization: Bearer {token}
Content-Type: application/json

{
  "account_id": "{account_id}",
  "instrument_id": "{script_master_instrument_id}"
}
```

Adding an existing `(user, account, exchange, scrip_code)` returns the existing watchlist item and does not create a duplicate.

List the selected account's watchlist:

```http
GET /script-master/watchlist?account_id={account_id}
Authorization: Bearer {token}
```

Delete an item:

```http
DELETE /script-master/watchlist/{watchlist_item_id}
Authorization: Bearer {token}
```

Deletion only succeeds for a watchlist item owned by the current application user. Add and remove operations write `script_master.watchlist_add` and `script_master.watchlist_remove` audit events.

## Frontend Workflow

1. Open `/script-master` from the Script Master sidebar item.
2. Select an active broker account. The first active account is selected automatically when available.
3. Enter at least two characters, for example `idea`. Input is debounced by 350 ms.
4. Review the horizontally scrollable results table. Expand `Fields` to inspect the raw Script Master payload.
5. Click `Add`. The button progresses through `Add`, `Loading`, and `Added` states.
6. Switch to the `Watch List` tab to review saved instruments for the selected account.
7. Use the trash action to remove an entry.

Both views include loading, empty, and error states. The wide instrument table scrolls horizontally on smaller screens and preserves all available fields rather than hiding derivative metadata.

## Migration

Migration `0010_script_master_watchlist`:

- adds nullable `tick_size NUMERIC(18, 6)` to `script_master_instruments`;
- creates `script_master_watchlist_items` with user/account foreign keys;
- creates user/account and exchange/scrip-code indexes;
- adds the duplicate-prevention unique constraint.

Apply migrations with:

```bash
docker compose exec api alembic upgrade head
```

## Verification

Automated coverage lives in `apps/api/tests/test_script_master_watchlist.py` and the Script Master normalization tests in `apps/api/tests/test_live_copy.py`.

Manual smoke test:

1. Complete Sharekhan login or manually refresh an exchange so Script Master rows exist.
2. Search for a known symbol such as `idea`.
3. Add a result and confirm it appears as `Added`.
4. Add it again and confirm no duplicate row appears.
5. Switch accounts and confirm watchlists are independent.
6. Refresh Script Master and confirm the saved entry still appears.
7. Remove the entry and confirm it disappears from both the watchlist and the search result's added state.
