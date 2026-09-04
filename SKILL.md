---
name: butler-dca
description: Trade one asset in slices on a repeating schedule — spot or perp, flat or % size, with price-band, weekday and stop conditions. DCA, ladder in, scale out.
version: 1.1.0
metadata: {"openclaw":{"emoji":"🪜","requires":{"bins":["acp","bevo-read","bevo-automation"]}},"butler":{"tier":"on-demand","modes":["one-off","duty"],"moneyMoving":true,"keywords":["dca","dollar cost average","average in","average out","ladder in","ladder out","scale in","scale out","accumulate","recurring","scheduled","periodic","tranches","drip","every hour","every day","every week","every month","weekly","daily","hourly"],"requires":{"routes":["GET /butler-read/user-assets","GET /butler-read/token-search","POST /butler-exec/trade","POST /butler-exec/services"],"features":["tradeIdempotency","execRequestStatus"],"gates":["canSwap"],"bins":["acp","bevo-read","bevo-automation"]},"params":[{"name":"DCA_TOKEN","type":"string","required":true,"ask":"which asset should I average — the token's contract address for a spot swap, or its Hyperliquid symbol (BTC, ETH) for a perp?"},{"name":"DCA_ACTION","type":"enum","values":["buy","sell","perp-open","perp-reduce"],"default":"buy"},{"name":"DCA_CHAIN_ID","type":"chainId","default":8453,"help":"spot legs only; ignored on perps"},{"name":"DCA_USD_PER_RUN","type":"usd","default":25,"min":2,"max":10000,"help":"USD per run for a buy, a perp open and a perp reduce; also sizes a sell when DCA_SELL_QTY_PER_RUN is 0"},{"name":"DCA_BUY_PCT_OF_CASH","type":"number","default":0,"min":0,"max":100,"help":"buy this % of available spot cash each run instead of a flat figure; 0 = use DCA_USD_PER_RUN"},{"name":"DCA_SELL_QTY_PER_RUN","type":"number","default":0,"min":0,"max":1000000000,"help":"token quantity per sell; 0 = fall through to DCA_SELL_PCT_PER_RUN, then to DCA_USD_PER_RUN at the live price"},{"name":"DCA_SELL_PCT_PER_RUN","type":"number","default":0,"min":0,"max":100,"help":"sell this % of the holding each run; used when DCA_SELL_QTY_PER_RUN is 0"},{"name":"DCA_PERP_SIDE","type":"enum","values":["long","short"],"default":"long"},{"name":"DCA_LEVERAGE","type":"number","default":2,"min":1,"max":20},{"name":"DCA_INTERVAL_SECONDS","type":"int","default":86400,"min":3600,"max":2592000},{"name":"DCA_DAILY_AT","type":"string","default":"","help":"HH:MM in the owner's local time; when set it is used instead of the interval"},{"name":"DCA_DAYS","type":"string","default":"","help":"run only on these days — weekday names and/or month-days, e.g. \"mon,fri\" or \"1,15\"; empty = every tick"},{"name":"DCA_TIMEZONE","type":"string","default":"","help":"IANA zone the day filter reads the calendar in, e.g. Asia/Kuala_Lumpur; empty = UTC"},{"name":"DCA_MAX_PRICE","type":"number","default":0,"min":0,"max":100000000,"help":"price CEILING — act only at or below it; 0 = off. Applies to buy, sell and perp-reduce"},{"name":"DCA_MIN_PRICE","type":"number","default":0,"min":0,"max":100000000,"help":"price FLOOR — act only at or above it; 0 = off. Applies to buy, sell and perp-reduce"},{"name":"DCA_MIN_CASH_USD","type":"usd","default":25,"min":0,"max":1000000,"help":"skip a buy that would leave less spot stablecoin cash than this"},{"name":"DCA_MAX_RUNS","type":"int","default":0,"min":0,"max":10000,"help":"stop after this many filed runs; 0 = no stop"},{"name":"DCA_TOTAL_BUDGET_USD","type":"usd","default":0,"min":0,"max":1000000,"help":"stop once this much USD has moved across all runs; 0 = no stop"},{"name":"DCA_ESCALATE","type":"bool","default":false,"help":"hand each eligible run to the duty's judgment text instead of trading directly"}],"dutyTemplate":"duty.py"}}
---

## When to use

The owner wants the same asset traded in slices on a schedule: "DCA $50 of X every week",
"sell 0.2 ETH every Friday", "add $100 to my BTC long every Monday", "trim my short daily",
"put 10% of my cash into X monthly", "sell 5% of my bag on the 1st and the 15th", "buy X
hourly but only under $80k" — or only *over* a level, which is the same knob the other way.
One asset, one direction, one cadence per duty. A single "buy $50 of X now" is a plain trade,
not this skill.

## Before you start

Pin the asset once, here, at authoring time — a standing duty must trade the same asset every
run, so never leave a bare ticker for the schedule to re-resolve:

```bash
bevo-read token-search --q '$TICKER'
```

Take `address` and `networkId` from the match the owner meant into `DCA_TOKEN` and
`DCA_CHAIN_ID` (AGENTS.md § token search decides which match that is). For a perp the
Hyperliquid symbol is the id — put `BTC` / `xyz:AAPL` in `DCA_TOKEN` verbatim, do not search
for it, and leave `DCA_CHAIN_ID` alone.

Then get, in the owner's own words: the action, the size per run, the cadence, and any
condition. Echo all four back before you file anything.

## Customize

- `DCA_TOKEN` (required) — token address (spot) or Hyperliquid symbol (perp).
- `DCA_ACTION` (default `buy`) — `buy` | `sell` | `perp-open` | `perp-reduce`.
- `DCA_CHAIN_ID` (default `8453`) — the spot chain; a sell settles on this one chain.
- `DCA_USD_PER_RUN` (default $25) — USD per buy, perp open and perp reduce.
- `DCA_BUY_PCT_OF_CASH` (default 0 = off) — size a `buy` as a share of live spot cash instead
  of a flat figure ("10% of my cash each month"). It re-reads cash every run, so the slices
  shrink as the cash does.
- `DCA_SELL_QTY_PER_RUN` (default 0) — token quantity per sell.
- `DCA_SELL_PCT_PER_RUN` (default 0 = off) — size a `sell` as a share of the holding
  ("trim 5% a week"). Sizing order, most explicit first: quantity, then percentage, then
  `DCA_USD_PER_RUN` converted at the live price.
- `DCA_PERP_SIDE` (default `long`) — the side a `perp-open` run adds to. A `perp-reduce` run
  takes the opposite of the side the position is actually on, read at run time.
- `DCA_LEVERAGE` (default 2) — `perp-open` only.
- `DCA_INTERVAL_SECONDS` (default 86400) / `DCA_DAILY_AT` (default empty) — the cadence; set
  one. A bare `DCA_DAILY_AT` is the owner's local time.
- `DCA_DAYS` (default empty = every tick) — thin that cadence to named days: weekday names,
  month-days, or both — `"fri"`, `"1,15"`, `"mon,thu"`. This is how "every Friday" and "the
  1st and the 15th" are expressed; a 7-day interval drifts, a day filter does not.
- `DCA_TIMEZONE` (default empty = UTC) — the IANA zone `DCA_DAYS` reads the calendar in. Set
  it whenever the owner named a weekday, or their Friday may be the duty's Thursday.
- `DCA_MAX_PRICE` / `DCA_MIN_PRICE` (default 0 = off) — a price BAND, and both bounds apply to
  every gated action. `DCA_MAX_PRICE` is a ceiling ("only under $80k"), `DCA_MIN_PRICE` a floor
  ("only over $80k"); set both for "only between". A floor on a buy and a ceiling on a sell are
  ordinary asks, not mistakes. If a gate is set and the price cannot be read, the run is
  skipped — an unverified condition never trades. `perp-open` takes no price knob (there is no
  mark price before the position exists); that condition goes to `judgment` via `DCA_ESCALATE`.
- `DCA_MIN_CASH_USD` (default $25) — skip a `buy` that would leave less spot cash than this.
- `DCA_MAX_RUNS` / `DCA_TOTAL_BUDGET_USD` (default 0 = off) — the stop conditions.
- `DCA_ESCALATE` (default false) — for a condition these knobs cannot express, set it true and
  put the condition in the duty's `judgment` text; each eligible run wakes judgment, which
  decides and places the trade itself.

## One-off procedure

1. [FIXED] Read cash and holdings, and — for a `perp-reduce` — the live position:

   ```bash
   bevo-read assets
   acp trade hl-status
   ```

2. [ADAPT] Take the action, the size and any condition from the owner's words.

3. [FIXED] Refuse the run, and say why, when: `spotUsdcUsd` is null (unknown is never zero);
   a `buy` would leave less than `DCA_MIN_CASH_USD`; a `sell` finds no holding of `DCA_TOKEN`
   on `DCA_CHAIN_ID`; a `perp-reduce` finds no open position on that coin; the size is under
   the venue minimum (spot $2, perp open $15 — a reduce has none); or a price gate is set and
   the price cannot be read.
4. [FIXED] Size it: a `sell` is `DCA_SELL_QTY_PER_RUN`, else `DCA_USD_PER_RUN` ÷ the holding's
   `usdPrice`, clamped to that one chain's `balance`; a `perp-reduce` is `DCA_USD_PER_RUN`
   clamped to the position's `positionValueUsd`.
5. [FIXED] Echo asset, chain, size and the conditions you checked to the owner, then file the
   one leg for the action, keyed by the slot (today's date for a daily cadence):

   ```bash
   acp trade --token-in usdc --amount-in <usd> --token-out <DCA_TOKEN> --chain-out <DCA_CHAIN_ID> --idempotency-key dca:chat:buy:<slot>
   acp trade --token-in <DCA_TOKEN> --chain-in <DCA_CHAIN_ID> --amount-in <qty> --token-out usdc --idempotency-key dca:chat:sell:<slot>
   acp trade --side <DCA_PERP_SIDE> --token <DCA_TOKEN> --amount-usdc <usd> --leverage <n> --idempotency-key dca:chat:perp-open:<slot>
   acp trade --side <opposite of the position> --token <DCA_TOKEN> --amount-usdc <usd> --reduce-only --idempotency-key dca:chat:perp-reduce:<slot>
   ```

6. [FIXED] On `accepted`, `executed` or `manual_signing_required`, stop and report; on anything
   else, see "Idempotency and retries".

## Duty procedure

1. [ADAPT] Confirm the trigger is the cadence the owner said, and that every condition they
   named is either a knob above or written into `judgment` with `DCA_ESCALATE` true. A named
   weekday or month-day is `DCA_DAYS` (plus `DCA_TIMEZONE`), not a hand-computed interval; a
   one-sided price condition is one bound of the band, in either direction; a size given as a
   share is `DCA_BUY_PCT_OF_CASH` or `DCA_SELL_PCT_PER_RUN`. Only a condition none of those can
   express goes to `judgment`.
2. [FIXED] Trigger JSON — exactly one of these, never both:

   ```json
   [{"kind": "timer", "intervalSeconds": 604800}]
   [{"kind": "timer", "dailyAt": "09:00"}]
   ```

3. [FIXED] `env` = the params above (skill defaults, then the owner's saved `bevo-hub set`
   prefs, then this ask's own values). A price gate with `DCA_ACTION` `perp-open` is refused:
   the mark price needs an open position, so that condition goes in `judgment` instead.
   Name any non-zero default you are leaving in place — `DCA_MIN_CASH_USD` is $25 and will
   skip runs the owner expected — or set it to 0 when they did not ask for a floor.
4. [ADAPT] `requestedDailyLimitUsdc` = one run's USD (never less), and for a `sell` name the
   token and quantity the pocket must cover; `yardstick` = "One `<action>` of `<size>` in
   `<asset>` per `<cadence>`, only when `<condition>`, never twice for the same slot."
5. [FIXED] Rehearse, then create — never hand-write the duty's code, the shim loads this
   skill's `duty.py`. The rehearse step is AGENTS.md section 5's ritual and applies to a
   `--from-skill` create like any other:

   ```bash
   bevo-automation rehearse '<json>'
   bevo-automation create --from-skill butler-dca@1.1.0 '<json>'
   ```

6. [FIXED] Report as in "Say to the owner".

## Idempotency and retries

Key: `dca:chat:<action>:<slot>` (one-off), `dca:{SERVICE_ID}:<action>:<slot>` (duty, see
`duty.py`) — `<slot>` is the schedule slot the run belongs to (the UTC date for a daily
cadence, `tick epoch ÷ interval` otherwise), never `now()`, so a redelivered tick or a
restarted duty maps to the key already used. Any error or uncertainty: `bevo-read request
<key>` first — do not re-run.

## Failure handling

| Outcome | What to do |
| --- | --- |
| `spot.available` false or `spotUsdcUsd` null | Skip the run and log it; never read unknown as zero. |
| `sell` and `DCA_TOKEN` is not held on `DCA_CHAIN_ID` | Skip; tell the owner the ladder has nothing left to sell on that chain. |
| `perp-reduce` and no open position on that coin | Skip and notify once; the ladder is finished. |
| Price gate set and the price cannot be read | Skip the run — an unverified condition never trades. |
| Run size under the venue minimum | Do not file; tell the owner the minimum ($2 spot, $15 perp open). |
| A perp leg refused for a permission gate | Perps are not available to this owner; offer the spot modes instead. |
| `DCA_MAX_RUNS` / `DCA_TOTAL_BUDGET_USD` reached | Notify once and stop trading; the duty keeps running until the owner disables it. |

## Limits

One asset, one direction, one cadence per duty — a second asset is a second duty. The band
compares a spot price (or a mark, reducing a perp) against a fixed number: it knows nothing
about candles, averages or indicators, so "when the 15m closes above X" is a `judgment`
condition with `DCA_ESCALATE`, not a knob. `DCA_DAYS` thins a cadence, it cannot create one —
the trigger still has to fire that day. No price gate on `perp-open` (there is no position to read a mark price from; use `judgment`). Stocks
are not covered. With `DCA_ESCALATE` on, a woken run counts against `DCA_MAX_RUNS` but a trade
judgment places does not count against `DCA_TOTAL_BUDGET_USD` — that ceiling only meters what
this skill's own code files. It never moves funds between the spot and perp accounts, and it never
disables itself. Yanking this skill does not stop a duty already created from it (the duty
keeps its own copy of `duty.py`).

## Say to the owner

One-off: "Filed one slice: `<action>` `<size>` of `<asset>` on `<chain/venue>`. `<n>` slices
and `$<x>` to go if this is a ladder." Duty: "Created, pending — arm it in Approvals; the card
proposes a pocket of one run's size, and nothing runs until then. It fires `<cadence>`, skips
a run when `<condition>` is not met, and stops after `<stop condition>`."
