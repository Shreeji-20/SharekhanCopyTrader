# Sharekhan API Postman Study

This document records the Sharekhan API behavior observed from the user's Postman workspace, the local Postman exports in `PostmanCollection/`, and `sample.py`.

No Postman API key or live credential value is stored here. Environment values are intentionally described by variable name only.

## Postman Inventory

Workspace fetched from Postman API:

| Workspace | Type |
| --- | --- |
| `My Workspace` | `personal` |

Collections visible through the Postman API:

| Collection | Notes |
| --- | --- |
| `Sharekhan Api` | Main REST collection used for this project. |
| `Solidus Global` | Not part of this Sharekhan integration pass. |
| `Enterprise RAG App` | Not part of this Sharekhan integration pass. |
| `FastApi` | Not part of this Sharekhan integration pass. |
| `NuvamaAPI` | Not part of this Sharekhan integration pass. |

Environment visible through the Postman API:

| Environment | Variables |
| --- | --- |
| `Sharekhan API` | `apiKey`, `reqToken`, `state`, `versionId`, `customerId`, `FinalEncryptedToken`, `accessToken`, `loginId` |

WebSocket finding:

- The Postman API did not expose a separate collection named `Websockets`.
- The local exported `Sharekhan Api` collection contains a folder named `Websocket`, but that folder is empty.
- The shared Postman WebSocket link provided for workspace `cca20dec-b44f-4741-8610-58eeee2f4830` and request `6a2023306530dbd1d6928994` is not retrievable from this environment:
  - Direct `web.postman.co` access returned an authenticated-page error.
  - Postman API request, collection/request, workspace/request, and websocket-request URL shapes returned `404`.
  - The collection-like id in the shared link, `69368cce5a3b852710769b39`, is not exposed as a collection through the Postman API key used for this study.
- The Sharekhan WebSocket protocol was later supplied manually. The confirmed socket URL requires both `ACCESS_TOKEN` and `API_KEY` query parameters.
- The project WebSocket manager now appends both `ACCESS_TOKEN` and `API_KEY`, sends the Sharekhan module `subscribe` frame, sends `feed` frames, and sends `ack` subscription when `customerId` is available.

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `apiKey` | Sharekhan API key. Sent in access-token body and most authenticated request headers. |
| `reqToken` | Raw request token returned by Sharekhan to the callback URL after browser login. |
| `state` | Numeric state sent during login/access-token calls. Used by our app to match callback to account. |
| `versionId` | Sent in the access-token request body. Current project default is `1005`. |
| `customerId` | Sharekhan customer id. Required in account/order/report/holding/trade routes. |
| `FinalEncryptedToken` | Result of decrypting `reqToken`, swapping payload order, and encrypting again. Sent as `requestToken` to get `accessToken`. |
| `accessToken` | Token returned by Sharekhan access-token endpoint. Used in `access-token` header for later API calls. |
| `loginId` | Sharekhan login/channel user. Used as `channelUser` in order payloads. |

## Authentication Flow

### 1. Start Browser Login

Postman request:

```http
GET https://api.sharekhan.com/skapi/auth/login.html?api_key={{apiKey}}
```

Project behavior should include `state` in the login URL so the callback can be tied back to the correct account:

```http
GET https://api.sharekhan.com/skapi/auth/login.html?api_key={{apiKey}}&state={{state}}
```

After successful Sharekhan login, Sharekhan redirects to the configured callback URL with a request token. The app should save the raw returned request token first.

### 2. Convert Raw Request Token

`sample.py` shows the required conversion before calling the access-token endpoint:

1. URL-decode the raw request token.
2. Replace spaces with `+` because URL encoding can alter base64 tokens.
3. Add base64 padding if missing.
4. Decode using URL-safe base64.
5. Split decoded bytes into `ciphertext` and a 16-byte GCM tag.
6. Decrypt using AES-GCM:
   - Key: Sharekhan Secure Key encoded as UTF-8.
   - IV: `base64.b64decode("AAAAAAAAAAAAAAAAAAAAAA==")`.
   - Tag length: `16`.
7. Decrypted text is in this format:

```text
key|customerId
```

8. Swap the order:

```text
customerId|key
```

9. Encrypt the swapped text with the same AES-GCM key/IV settings.
10. Concatenate `ciphertext + tag`.
11. URL-safe base64 encode and strip `=` padding.
12. Store the result as `FinalEncryptedToken`.

Implementation note: the project stores the raw callback `request_token`, then converts it inside broker-router immediately before access-token exchange. The `FinalEncryptedToken` is used as the Sharekhan request body value and is not stored as a separate credential.

### 3. Fetch Access Token

Postman request:

```http
POST https://api.sharekhan.com/skapi/services/access/token
Content-Type: application/json
```

Body:

```json
{
  "apiKey": "{{apiKey}}",
  "requestToken": "{{FinalEncryptedToken}}",
  "state": "{{state}}",
  "versionId": "{{versionId}}"
}
```

Expected project storage after success:

| Response value | Project storage |
| --- | --- |
| `data.token` or equivalent access-token value | encrypted `broker_accounts.access_token` |
| `data.customerId` when present | `broker_accounts.customer_id` |
| `data.loginId` when present | `broker_accounts.login_id` |
| expiry when present | `broker_accounts.token_expires_at` |

### 4. Use Access Token Everywhere

All subsequent account/order/portfolio requests use:

```http
api-key: {{apiKey}}
access-token: {{accessToken}}
Content-Type: application/json
```

Some collection requests omit `Content-Type`, but using it consistently for JSON endpoints is safe.

## Endpoint Summary

Base URL:

```text
https://api.sharekhan.com
```

### Auth

| Name | Method | Path | Auth | Purpose |
| --- | --- | --- | --- | --- |
| `GetRequestToken` | `GET` | `/skapi/auth/login.html?api_key={{apiKey}}` | No access token | Opens Sharekhan browser login and eventually returns raw request token to callback. |
| `GetAccessToken` | `POST` | `/skapi/services/access/token` | No access token | Exchanges `FinalEncryptedToken` for `accessToken`. |

### Orders

All order mutation requests use:

```http
POST /skapi/services/orders
api-key: {{apiKey}}
access-token: {{accessToken}}
Content-Type: application/json
```

Common order fields:

| Field | Notes |
| --- | --- |
| `orderId` | Required for `MODIFY` and `CANCEL`; absent for normal `NEW`. |
| `customerId` | Sharekhan customer id. |
| `scripCode` | Numeric instrument code. |
| `tradingSymbol` | Symbol, for example `ONGC` or `NIFTY`. |
| `exchange` | Examples in collection: `NC`, `NF`. |
| `transactionType` | `B` for buy, `S` for sell. |
| `quantity` | Integer quantity. |
| `disclosedQty` | Collection uses `0`. |
| `price` | String/number. `0` used for market-like derivative example. |
| `triggerPrice` | Collection uses `"0"`. |
| `rmsCode` | Collection uses `ANY`. |
| `afterHour` | `Y` or `N`; collection uses `N`. |
| `orderType` | Collection uses `NORMAL`. |
| `channelUser` | `{{loginId}}`. |
| `validity` | Collection uses `GFD`. |
| `requestType` | `NEW`, `MODIFY`, or `CANCEL`. |
| `productType` | Collection uses `INVESTMENT`. |

#### New Cash/Equity Order

```json
{
  "customerId": "{{customerId}}",
  "scripCode": 2475,
  "tradingSymbol": "ONGC",
  "exchange": "NC",
  "transactionType": "B",
  "quantity": 1,
  "disclosedQty": 0,
  "price": "250",
  "triggerPrice": "0",
  "rmsCode": "ANY",
  "afterHour": "N",
  "orderType": "NORMAL",
  "channelUser": "{{loginId}}",
  "validity": "GFD",
  "requestType": "NEW",
  "productType": "INVESTMENT"
}
```

#### Modify Order

Same endpoint as new order, with `orderId` and `requestType: "MODIFY"`.

#### Cancel Order

Same endpoint as new order, with `orderId` and `requestType: "CANCEL"`.

#### Derivatives Order

The derivative example adds:

| Field | Example |
| --- | --- |
| `expiry` | `09/06/2026` |
| `instrumentType` | `FI` |
| `optionType` | `CE` |
| `strikePrice` | `23400` |
| `exchange` | `NF` |
| `scripCode` | `60530` |
| `tradingSymbol` | `NIFTY` |

Example body:

```json
{
  "customerId": "{{customerId}}",
  "scripCode": 60530,
  "tradingSymbol": "NIFTY",
  "exchange": "NF",
  "transactionType": "B",
  "quantity": 75,
  "triggerPrice": "0",
  "price": "0",
  "rmsCode": "ANY",
  "afterHour": "N",
  "orderType": "NORMAL",
  "expiry": "09/06/2026",
  "instrumentType": "FI",
  "optionType": "CE",
  "strikePrice": "23400",
  "channelUser": "{{loginId}}",
  "validity": "GFD",
  "requestType": "NEW",
  "productType": "INVESTMENT"
}
```

### Order Reports

| Name | Method | Path | Purpose |
| --- | --- | --- | --- |
| `RetriveAllOrders` | `GET` | `/skapi/services/reports/{{customerId}}` | Retrieves all orders for customer. |
| `RetriveHistoryOfOrder` | `GET` | `/skapi/services/reports/NC/{{customerId}}/{orderId}` | Retrieves history/details for a specific order. |
| `GetTradeGeneratedByOrder` | `GET` | `/skapi/services/reports/NC/{{customerId}}/{orderId}/trades` | Retrieves trades generated by a specific order. |

Collection examples use literal order IDs such as `254693575`; implementation should accept order id as a path parameter.

### Positions / Trades

The collection folder is named `Positions`, but the request URL is the trades endpoint:

```http
GET /skapi/services/trades/{{customerId}}
api-key: {{apiKey}}
access-token: {{accessToken}}
Content-Type: application/json
```

Collection description says "Retrieves all positions". Integration should verify from live response whether this endpoint returns positions, trades, or both, and name internal models accordingly.

### Accounts / Limits

Postman request:

```http
GET /skapi/services/limitstmt/NSE/{{customerId}}
api-key: {{apiKey}}
access-token: {{accessToken}}
```

Purpose: account details, limits, or fund/limit statement for the selected exchange segment. Existing project routes should keep exchange configurable because the collection uses `NSE`, while other code/examples may use `NC`.

### Holdings

Postman request:

```http
GET /skapi/services/holdings/{{customerId}}
api-key: {{apiKey}}
access-token: {{accessToken}}
Content-Type: application/json
```

The collection also includes a raw GET body:

```json
{
  "apiKey": "{{apiKey}}"
}
```

GET bodies are unusual and may be ignored by some HTTP clients/proxies. Prefer headers first, then keep the body only if live testing proves Sharekhan requires it.

### Historical Data

Postman request:

```http
GET /skapi/services/historical/NC/2475/5minute
api-key: {{apiKey}}
access-token: {{accessToken}}
Content-Type: application/json
```

Path parameters:

| Parameter | Example |
| --- | --- |
| `exchange` | `NC` |
| `scripCode` | `2475` |
| `interval` | `5minute` |

### Scrip Master

Postman request:

```http
GET /skapi/services/master/NC
```

The collection does not include auth headers for this request. Treat the endpoint as possibly public or API-key optional until live testing confirms.

Path parameter:

| Parameter | Example |
| --- | --- |
| `exchange` | `NC` |

Project integration:

- Broker-router exposes this as `GET /sharekhan/master/{exchange}` and can fetch it with `account_id` so the selected account's proxy and credentials are used when required.
- Main API exposes manual cache refresh as `POST /script-master/{exchange}/refresh?account_id={account_id}`.
- Refreshed records are normalized into `script_master_instruments`.
- The live-copy engine uses this cache only when a master WebSocket order acknowledgement is missing `scripCode`.

Normalized fields used by the project:

| Normalized field | Raw aliases accepted |
| --- | --- |
| `scrip_code` | `scripCode`, `ScripCode`, `ScripToken`, `Token`, `ExchangeScripCode`, `securityId` |
| `trading_symbol` | `tradingSymbol`, `TradingSymbol`, `symbol`, `SEM_TRADING_SYMBOL` |
| `exchange` | `exchange`, `Exchange`, `exchangeCode`, `ExchangeCode`, `SEM_EXM_EXCH_ID` |
| `segment` | `segment`, `Segment`, `segmentCode`, `SegmentCode` |
| `instrument_type` | `instrumentType`, `InstrumentType`, `insType`, `SEM_INSTRUMENT_NAME` |
| `option_type` | `optionType`, `OptionType`, `cpType`, `SEM_OPTION_TYPE` |
| `strike_price` | `strikePrice`, `StrikePrice`, `strike`, `SEM_STRIKE_PRICE` |
| `expiry_date` | `expiry`, `Expiry`, `expiryDate`, `SEM_EXPIRY_DATE` |
| `lot_size` | `lotSize`, `LotSize`, `marketLot`, `SEM_LOT_UNITS` |
| `isin` | `isin`, `ISIN`, `isinCode`, `SEM_ISIN_CODE` |

The parser accepts JSON arrays/objects and delimited text with common delimiters such as comma, pipe, tab, and semicolon.

Resolution safety:

- Equity orders resolve mainly by `tradingSymbol` plus exchange/segment, refined by `ISIN` or lot size when present.
- Derivative orders require expiry, strike price, and option type, with instrument type/lot size used when present.
- If multiple Script Master rows resolve to different `scripCode` values, the project logs ambiguity and skips the copy order.
- If no match is found, the project logs an unresolved-symbol error and stores the details in `master_trade_events.raw_payload_json.script_master_resolution`.

## WebSocket Notes

The fetched REST collection does not provide a websocket request. The local collection only has an empty `Websocket` folder.

The user also provided a Postman web link to a WebSocket example:

```text
Workspace: cca20dec-b44f-4741-8610-58eeee2f4830
Collection-like id in URL: 69368cce5a3b852710769b39
Request id in URL: 6a2023306530dbd1d6928994
```

That request could not be fetched through the Postman public API or unauthenticated web access. The protocol below is therefore documented from the manually supplied Sharekhan WebSocket details, not from the fetched Postman JSON.

### Connection URL

Connect to:

```text
wss://stream.sharekhan.com/skstream/api/stream?ACCESS_TOKEN={{accessToken}}&API_KEY={{apiKey}}
```

Required query parameters:

| Parameter | Source | Notes |
| --- | --- | --- |
| `ACCESS_TOKEN` | Auth flow `accessToken` | Returned by `/skapi/services/access/token` after converting `request_token` to `FinalEncryptedToken`. |
| `API_KEY` | Account Sharekhan API key | Same API key used for REST headers and auth payloads. Do not log it. |

Implementation detail:

- Keep `SHAREKHAN_WS_URL` as the base URL `wss://stream.sharekhan.com/skstream/api/stream`.
- Build query params with URL encoding rather than string concatenation.
- Use the selected account's proxy for the WebSocket connection if proxy support is added to the socket client.

### WebSocket Lifecycle

The socket flow is stateful:

1. Open the WebSocket using `ACCESS_TOKEN` and `API_KEY`.
2. Sharekhan may first send a successful `message: "connect"` frame with a session id.
3. Send module subscription for `feed` and `ack`.
4. Wait for a successful `message: "subscribe"` module subscription response.
5. Send feed subscription messages for market data.
6. Send ack subscription message for live order status.
7. On reconnect, repeat module subscription and all active feed/ack subscriptions.

### Module Subscription

Send this immediately after connection:

```json
{
  "action": "subscribe",
  "key": ["feed", "ack"],
  "value": [""]
}
```

Successful response:

```json
{
  "status": 100,
  "message": "subscribe",
  "timestamp": "2021-03-02T11:17:00+05:30",
  "data": "successFEED,successACK"
}
```

The implementation accepts the documented compact format and observed spaced/cased variants such as `successFeed,successAck`, `success Feed, success Ack`, and `success FEED,success ACK`.

Response interpretation:

| Field | Meaning |
| --- | --- |
| `status` | Sharekhan stream application status. `100` indicates success in the supplied examples. |
| `message` | Echoes the action. For module subscription it should be `subscribe`. |
| `data` | Contains comma-separated module results. `successFEED` confirms feed module subscription; `successACK` confirms ack module subscription. |

Do not send feed or ack-specific subscriptions until this module subscription succeeds.

### Feed Subscription

Use action `feed` to subscribe to market data.

The instrument value format is:

```text
{exchangeCode}{scripCode}
```

Examples:

| Instrument | Meaning |
| --- | --- |
| `NC2885` | Exchange `NC`, scrip code `2885`. |
| `NC22` | Exchange `NC`, scrip code `22`. |

LTP-only request:

```json
{
  "action": "feed",
  "key": ["ltp"],
  "value": ["NC2885"]
}
```

Full feed request:

```json
{
  "action": "feed",
  "key": ["full"],
  "value": ["NC22"]
}
```

Depth request:

```json
{
  "action": "feed",
  "key": ["depth"],
  "value": ["NC22"]
}
```

Supported feed keys from the supplied example:

| Key | Purpose |
| --- | --- |
| `ltp` | Last traded price and core quote fields. |
| `depth` | Market depth / bid-offer view. |
| `full` | Full feed, described as feed, depth, and bid/off combined. |

### Feed Response

Example feed response:

```json
{
  "status": 100,
  "message": "feed",
  "timestamp": "2021-03-02T11:30:01+05:30",
  "data": {
    "exchangeCode": "NC",
    "scripCode": 2885,
    "ltp": 2105.65,
    "ltq": 10,
    "ltt": "03/02/2021 11:29:59",
    "lastUpdatedTime": "03/02/2021 11:30:00",
    "open": 2122,
    "high": 2130,
    "low": 2100.95,
    "close": 2101.7,
    "avgPrice": 2115.79,
    "bidPrice": 2105,
    "bidQty": 427,
    "offPrice": 2105.65,
    "offQty": 51,
    "qty": 3631747,
    "totalBuyQty": 288352,
    "totalSellQty": 772822,
    "perChange": 0.18794078,
    "rsChange": 0.18,
    "upperCkt": 2311.85,
    "lowerCkt": 1891.55,
    "yrHigh": 2369.35,
    "yrLow": 875.65
  }
}
```

Common feed data groups:

| Group | Fields |
| --- | --- |
| Identity | `exchangeCode`, `scripCode`, `tradingSymbol` when present, `insType`, `index` |
| Time | `timestamp`, `lastUpdatedTime`, `ltt` |
| Last trade | `ltp`, `ltq`, `preltq`, `settlementprice` |
| OHLC | `open`, `high`, `low`, `close`, `avgPrice` |
| Bid/offer | `bidPrice`, `bidQty`, `bidCoc`, `offPrice`, `offQty`, `offCoc`, `totalBuyQty`, `totalSellQty` |
| Price limits | `upperCkt`, `lowerCkt`, `priceband`, `ticksize` |
| Change | `perChange`, `rsChange` |
| Volume/turnover | `qty`, `cashturnover`, `foturnover` |
| Open interest | `currentOI`, `oichange`, `oidiff`, `oiDifPer`, `oiHigh`, `oiLow`, `oiTime` |
| Market breadth | `advance`, `decline`, `same` |
| Other | `spotPrice`, `coc`, `yrHigh`, `yrLow` |

Implementation should store or publish the raw payload first, then normalize only the fields required by the application. Sharekhan may include duplicated or missing fields depending on exchange, instrument, and feed key.

### Live Order Status Ack Subscription

After the module subscription succeeds, subscribe to order acknowledgements with the customer id:

```json
{
  "action": "ack",
  "key": [""],
  "value": ["{{customerId}}"]
}
```

The `customerId` is the Sharekhan customer id returned by access-token/profile data or decoded from the request-token flow.

Example ack response:

```json
{
  "status": 100,
  "message": "feed",
  "timestamp": "2021-03-02T11:30:01+05:30",
  "data": {
    "Exchange": "NC",
    "CustomerID": "XXXX",
    "SharekhanOrderID": "245749050",
    "ExchangeOrderID": "1000000000000678",
    "AckState": "NewOrderConfirmation",
    "ExchangeCode": "NSE",
    "SegmentCode": "EQ",
    "TradingSymbol": "ONGC",
    "BuySellString": "B",
    "OrderQty": 1,
    "RemainingQty": 1,
    "TradeQty": 0,
    "DisclosedQty": 0,
    "DisclosedRemainingQty": 0,
    "OrderPrice": "92.50",
    "TriggerPrice": "0",
    "TradePrice": "0",
    "TradeID": 0,
    "ExchangeDateTime": "02/03/2021 12:02:08",
    "ChannelCode": "PWR_TRD",
    "ChannelUser": "XXXX",
    "ErrorMessage": "Success",
    "OrderTrailingPrice": "0",
    "OrderTargetPrice": "0",
    "BookProfitPrice": "0",
    "ChildSLPrice": "0",
    "LimitLossToPrice": "0",
    "OrderType": "NOR",
    "CoverOrderId": "0"
  }
}
```

Ack data groups:

| Group | Fields |
| --- | --- |
| Account/order identity | `CustomerID`, `SharekhanOrderID`, `ExchangeOrderID`, `TradeID`, `CoverOrderId` |
| Market identity | `Exchange`, `ExchangeCode`, `SegmentCode`, `TradingSymbol` |
| Status | `AckState`, `ErrorMessage`, `ExchangeDateTime` |
| Side/quantity | `BuySellString`, `OrderQty`, `RemainingQty`, `TradeQty`, `DisclosedQty`, `DisclosedRemainingQty` |
| Prices | `OrderPrice`, `TriggerPrice`, `TradePrice`, `OrderTrailingPrice`, `OrderTargetPrice`, `BookProfitPrice`, `ChildSLPrice`, `LimitLossToPrice` |
| Channel | `ChannelCode`, `ChannelUser` |
| Order type | `OrderType` |

The sample ack response has `message: "feed"` even though the request action is `ack`. Integration should route ack messages by the shape of `data` and subscription context, not only by the top-level `message` field.

### Broker-Router Implementation Gap

Current project behavior:

1. Broker-router opens a WebSocket connection with `ACCESS_TOKEN` and `API_KEY` in the query string.
2. Broker-router sends module subscription for `feed` and `ack` after connection.
3. Broker-router treats `successFEED` and `successACK` as the readiness signal.
4. Broker-router sends `feed` frames when users subscribe to symbols.
5. Broker-router sends an `ack` frame for account `customerId` when available.
6. Incoming messages are published to Redis channel `sharekhan:ticks` with a message `type`.
7. Stream errors are published to Redis channel `sharekhan:stream_errors`.
8. Unsubscribe currently updates local subscription state only because the confirmed Sharekhan unsubscribe frame is not yet known.

## Integration Implications For This Project

Implemented integration behavior:

1. Keep saving raw callback `request_token`.
2. Convert request token from `sample.py` in broker-router:
   - decrypt raw request token,
   - parse `key|customerId`,
   - swap to `customerId|key`,
   - encrypt to `FinalEncryptedToken`.
3. Call `/skapi/services/access/token` using `FinalEncryptedToken`, `apiKey`, `state`, and `versionId`.
4. Store returned `accessToken` and use it on every order/account/holding/history request.
5. Store or update `customerId` and `loginId`.
6. Keep account-scoped proxy support because all Sharekhan HTTP requests should continue to route through the account proxy when configured.
7. Update order/report/data endpoint mappings to match the Postman collection names and paths exactly.
8. Use Sharekhan WebSocket handling:
   - connect with both `ACCESS_TOKEN` and `API_KEY`,
   - send module subscription for `feed` and `ack`,
   - send `feed` requests for selected instruments,
   - send `ack` request for live order status by `customerId`,
   - replay subscriptions after reconnect.

## Open Questions Before Coding

| Question | Why it matters |
| --- | --- |
| Does Sharekhan require the same `state` used in login when exchanging access token? | The collection sends `state`; current project stores per-login state and can reuse it. |
| Does holdings truly require a GET body with `apiKey`? | GET bodies can be fragile; live behavior should decide. |
| Is `Positions / RetriveAllPositions` actually positions or trades? | The collection URL is `/trades/{customerId}`. |
| Does Sharekhan accept multiple instruments in one `feed` frame? | The sample uses one value, but the schema shape is an array. Live testing should confirm batching behavior. |
| What exact unsubscribe frame does Sharekhan expect for market feed and ack streams? | Supplied details confirm subscription requests but do not include unsubscribe examples. |
