# Changelog

## 5.0.0

**The daily caps are gone.** `MAX_PER_DAY` and `MAX_USD_PER_DAY` are removed, and
with them the ledger the duty kept in its own log to count them: no `requested` /
`released` lines, no re-reading `duty.log` / `duty.log.1`, and no buy skipped
because the rotated log starts after midnight UTC. What a duty may spend without
asking is the pocket the owner funds in the app, and bevo-server enforces it.

- A catch-up of a slot is still one buy: the idempotency key is unchanged
  (`buy:<duty>:slot:<slot>`), so bevo-server's ledger answers the second `replay`.
- A `pocket_empty` / `wallet_short` refusal is reported like any other refusal.
- `recipe.json` goes to version 5 and supersedes `dca@4`. A duty already filed from
  `dca@3` or `dca@4` keeps its stored code, and with it both caps; re-file it to
  pick this up.

## 4.0.0

**A buy the server refuses before executing it no longer counts toward the daily
caps.** bevo-server now refuses a buy DEFINITIVELY — nothing executed, nothing
reserved — when the pocket the owner funded is used up (`code: "pocket_empty"`) or,
next, when the owner's wallet can't cover a buy the pocket could (`code:
"wallet_short"`). The duty's ledger line is still written *before* the buy is sent
(unchanged — the other order double-spends), so without this the day's count or
dollar cap could be burned by refusals alone, and a same-day top-up would not resume
buying until the next UTC day.

- New ledger line, `released <UTC time> key=<idempotency key>`, written only for a
  refusal whose `code` is one of `pocket_empty` / `wallet_short` — never for a 409
  (in flight, outcome unknown), a timeout, or an unparseable answer, any of which may
  already have landed.
- `requested()` walks the log in order and pops a key on its `released` line, so a
  key released this way is free to count again if it is re-requested.
- `recipe.json` goes to version 4 and supersedes `dca@3`. A duty already filed from
  `dca@3` keeps its stored code; re-file it to pick this up.

## 3.0.0

**Daily caps, counted from the duty's own log.** Before each buy the duty logs
`requested <UTC time> key=<idempotency key> route=buy usd=<size>` through `bevo.log()`,
and the caps count the distinct keys on today's (UTC) lines of `duty.log` /
`duty.log.1`, which the supervisor writes on the duty's volume. `bevo.allow()`'s
counter in `bevo.state` is no longer used.

- New `MAX_USD_PER_DAY` (unset by default): a dollar ceiling on the day's buys,
  beside `MAX_PER_DAY`. A buy that would cross it is skipped — the size is fixed.
- A catch-up of a slot already requested is re-sent under the same key (the ledger
  answers `replay`) and no longer spends a second allowance.
- Written before the buy is sent, as before: a refused buy still counts, and a crash
  between the rail answering and the line landing cannot double-spend.
- When the rotated log starts after midnight UTC, today's earliest lines may be gone,
  so the duty skips the buy instead of undercounting.
- Every other log line is flattened onto one line, so text the rail echoes back can
  never write a ledger entry.
- `recipe.json` goes to version 3 and supersedes `dca@2`. A duty already filed from
  `dca@2` keeps its stored code; re-file it to pick this up.

## 2.0.0

**The skill became a template.** `SKILL.md` — the prose playbook, its numbered
`[FIXED]`/`[ADAPT]` steps, and its 21 declared params — is gone. `duty.py` is now the
whole execution: a duty filed from this repo runs this code directly, with no model
turn interpreting a procedure around it. The bundle is `recipe.json` (id `dca`,
version 2), `duty.py`, and this README; there is no frontmatter and nothing else at
the root. (The old `1.4.2` version number counted the prose playbook, a different
artefact — this reset starts the template's own line at `2.0.0`.)

- Params drop from 21 (`DCA_TOKEN`, `DCA_ESCALATE`, …) to five: `TOKEN`, `CHAIN_ID`,
  `SIZING`, `SIZE_USD`, `MAX_PER_DAY`. The rest configured a playbook a model read;
  a program does not need them.
- The retired `bevo.trade(command=…, idempotency_key=…)` and `bevo.escalate(...)`
  calls — deleted from `bevo.py` on 2026-09-21 with no shim — are replaced by
  `subprocess.run(["acp", "trade", …, "--idempotency-key", key])` and
  `bevo.prompt()`.
- A duty already filed from the old bundle keeps running its old stored code
  unchanged; it does not auto-migrate. Re-file it (`duty_create` with
  `recipe: "dca@2"`) to pick this up.

## 1.4.2

**Trimmed to just enough context.** SKILL.md is read into a fast model's prompt, where
every char of explanation competes with a rule for attention. The capped body drops
11,956 -> 9,858 chars (-17.5%), turning 44 chars of headroom under the 12,000 cap into
2,142. Only explanation was cut — every knob, gate, refusal condition and command shape
is unchanged, and all fenced command lines are byte-identical.

- Cut WHY-clauses behind rules that already stated themselves absolutely, background
  restated from AGENTS.md, and two real duplications: One-off step 3 re-listed the whole
  Failure handling table, and Limits re-argued rules already carried by Customize.
- `sendable()`'s docstring no longer explains itself by naming SDK functions that no
  longer exist; the rule stands on its own.

## 1.4.1

**A sell smaller than 8 decimal places went on the wire as `--amount-in 0`.** `fmt()`
renders a CLI number at 8dp, so a positive quantity below `0.00000001` — a dust holding,
or a small `DCA_SELL_PCT_PER_RUN` of one — became the literal string `0`, and the server
answered with a parse error instead of a reason. `NaN` rendered as `nan` the same way. The
SDK's own money verbs used to refuse this before building a command; those verbs are gone,
so the duty refuses it itself.

- New `sendable()` guards the two sizes the duty computes at runtime: the sell quantity and
  the perp-reduce size. Both now skip the run with the reason they already carried
  ("nothing left to sell", "no value left to reduce") instead of filing an unparseable
  command. `0.00000001` still sends — the guard refuses what renders as nothing, not what
  is merely small.
- The buy and perp-open paths are unchanged: their spot and perp minimums already floor
  them well above 8dp.

## 1.4.0

**The Duty procedure now offers the fork it promised.** "Customize" has said since
1.2.0 that a mechanical condition — a candle close, an indicator, a second asset's
price — is a fork. The numbered steps Butler actually walks never said so: step 1
offered a strict binary (a knob, or `judgment` via `DCA_ESCALATE`) and step 5 ended
at "never hand-write the duty's code". So "buy $5k of BTC when the 15m candle closes
above $85k" landed on `DCA_ESCALATE` — an LLM wake every run — instead of the fork
that computes it in code.

- Step 1 splits the leftover condition three ways: knob, fork when mechanical,
  `judgment` only when it needs a brain.
- Step 5 keeps "do not hand-write a duty" but names the fork as the other thing
  `--from-skill` accepts.
- "Limits" drops the scope line "When to use" already states verbatim, paying for the
  body-length budget (the body is capped at 12,000 chars and was at 11,995).

## 1.3.1

- **The pocket was sized for one run, not one day.** The duty procedure set
  `requestedDailyLimitUsdc` to "one run's USD (never less)" and "Say to the owner" promised
  "a pocket of one run's size". A pocket meters a DAY, so "$100 of BTC every hour" armed $100
  and only the first run of each day could spend it — a duty that looks armed and healthy and
  buys once. Both now size the pocket at a day of the cadence (hourly $100 is $2400).
- **The weekly example taught the shape the rest of the skill forbids.** Step 1 says a named
  weekday is `DCA_DAYS`, and "Customize" says a 7-day interval drifts where a day filter does
  not — but the trigger JSON underneath offered `{"intervalSeconds": 604800}` as the first
  example to copy. Replaced with `dailyAt`, and `intervalSeconds` is shown on an hourly
  cadence, where it belongs.
- **`--from-skill butler-dca@1.2.1` was stale on arrival.** The worked example hard-pinned the
  previous version, so a duty created by copying it was built from 1.2.1 once 1.3.0 shipped.
  The pin is gone — `--from-skill butler-dca` uses the installed version, and
  `bevo-automation` records the exact commit in `sourceSkillSha256` either way.
- **Pinning the asset used the wrong read.** "Before you start" sent the author to
  `bevo-read token-search`, a lookalike-prone index with no alias table: "DCA $200 of BTC
  weekly" has no exact-symbol row to take, because the asset is cbBTC. It now uses
  `bevo-read token <SYMBOL>` — the verified list, which resolves BTC to cbBTC on Base — and
  falls back to the search only on a 404.
- **The price band never said whose price it reads.** It compares `DCA_TOKEN`'s own price,
  but the `DCA_MIN_PRICE` / `DCA_MAX_PRICE` help said only "price FLOOR" / "price CEILING".
  "Buy VIRTUAL when BTC clears 80k" set as `DCA_MIN_PRICE: 80000` gates on VIRTUAL, which
  never reaches $80k — the duty arms, takes a pocket and silently never fires. Both knobs and
  the "Customize" bullet now name the asset, and point a cross-asset condition at a fork.
- **The fork path named the case but not the tool.** "Customize" lists "a second asset's
  price" as a mechanical condition to fork for — "buy VIRTUAL when BTC clears 80k" — but the
  how-to only offered `bevo.rpc` and "any public HTTPS source". It now names
  `bevo.read("/token-stats", ...)`, which is the rails read for another asset's price.
- Trimmed the chain paragraph, the fork paragraph and "Limits" where they restated
  "Customize", to stay inside the 12,000-char body budget.

## 1.3.0

- **A chain is optional, and pinning one broke every plain DCA.** `DCA_CHAIN_ID` defaulted to
  `8453`, so a duty always passed `--chain-out` / `--chain-in` — even when the owner said only
  "buy $200 of BTC every week". The chain flags on `acp trade` are optional, and AGENTS.md § 7
  is explicit: "If your owner did not name a chain, add no chain flag of any kind", because the
  trading agent resolves the token's own chain and the same ticker on another chain is a
  different asset. The knob now has NO default: leave it out and a buy carries no chain flag;
  set it only when the owner named a chain.
- **The pin also made the duty unfileable.** `bevo-automation`'s chain guard refuses a duty
  whose chain narrowing the owner never asked for, so `create --from-skill butler-dca` was
  refused outright for every plain "asset + amount + cadence" ask — the owner got no duty at
  all. With the default gone there is nothing to refuse.
- **A sell now carries the chain of the row it spends.** A sell settles on ONE chain, so the
  quantity and the chain must agree. With `DCA_CHAIN_ID` set, `holding()` takes the row on that
  chain as before. With it unset, it takes the LARGEST row and the sell passes that row's own
  `chainId` — read off the data, never chosen for the owner.

## 1.2.1

- **An hourly duty ran once a day.** `slot_for()` bucketed by `DCA_INTERVAL_SECONDS`, so a
  trigger of `{"kind":"timer","intervalSeconds":3600}` left with the 86400 default mapped all
  24 ticks of a day to ONE slot; 23 were skipped as already done, silently. The slot key now
  takes the cadence from the TICK — a timer event carries the trigger's own `dailyAt` /
  `intervalSeconds`, which is what the schedule actually fires on — and falls back to the env
  only when the tick carries neither. Replayed: 3 hourly ticks now file 3 trades, where 1.2.0
  filed 1.
- **A skip could notify every tick.** `Notes.once` deduped on the reason TEXT, which embeds the
  live price, so each tick minted a new id. An hourly duty parked under its floor pushed 24
  times a day. The id is now the reason SHAPE with the digits stripped.
- **The Limits section contradicted Customize on the exact ask this skill is for.** Customize
  says a candle close is mechanical, so fork and compute it; Limits still said
  `"when the 15m closes above X"` is a `judgment` condition with `DCA_ESCALATE`. Limits now
  agrees: fork for arithmetic, escalate for judgment.
- **`networkId` is not a chain id.** "Before you start" said to take it into `DCA_CHAIN_ID`;
  AGENTS.md says outright that it is a search-index id and NEVER a trade chain id. Map the
  row's `networkLabel` through the chain-id table instead.
- The duty procedure now says the trigger and `DCA_INTERVAL_SECONDS` / `DCA_DAILY_AT` must
  agree, since a disagreement is what produced the first bug above.

## 1.2.0

- A condition the knobs cannot express now points at FORKING, not only at escalation.
  `DCA_ESCALATE` costs a wake per eligible run and suits a condition that needs judgment; a
  mechanical one — a candle close, a moving average, a second asset's price, an on-chain
  reading — is code, and code is free and runs every tick. `bevo-hub fork butler-dca` makes the
  owner's own copy, `duty.py` is theirs to edit, and forking changes nothing that guards the
  money: same sandbox, same signing policy, same approval cards, same pocket.

## 1.1.0

- The price gate is now a two-sided BAND on every gated action. `DCA_MAX_PRICE` is a ceiling
  and `DCA_MIN_PRICE` a floor, and either may be set on a buy or a sell — so "buy only when it
  breaks above X", "sell only when it drops below X" and "only between X and Y" are knobs
  instead of escalations. Before, a buy could only take a ceiling and a sell only a floor.
- Size a run as a share instead of a flat figure: `DCA_BUY_PCT_OF_CASH` ("10% of my cash each
  month", re-read every run) and `DCA_SELL_PCT_PER_RUN` ("trim 5% a week"). Sizing order for a
  sell, most explicit first: quantity, percentage, then USD at the live price.
- `DCA_DAYS` thins the cadence to named weekdays and month-days ("fri", "1,15", "mon,thu"),
  read in `DCA_TIMEZONE` (IANA, default UTC). "Every Friday" no longer has to be a 7-day
  interval, which drifts from whenever the duty happened to be created.
- Description and keywords rewritten for how owners actually ask. The hub scores names,
  keywords and description only — never the SKILL.md body — so recurring/scheduled/periodic
  phrasings and cadence words now match, while a plain one-line trade scores zero.
- Duty procedure: rehearse before create (AGENTS.md section 5's ritual applies to a
  `--from-skill` create too), and name any non-zero default gate left in place.
- The frontmatter namespace key is `metadata.butler`, not `metadata.bevo`. No field inside
  the block changed. Requires a container image that reads `metadata.butler`; an older image
  reads the block as empty and loses `dutyTemplate`, `params` and `modes`.

## 1.0.0

- Initial release: scheduled DCA in one asset — spot buy, spot sell, perp open and perp
  reduce — with per-run sizing, a cadence, price / cash-floor / run-count / total-USD
  conditions, an escalation path for conditions the knobs cannot express, and one
  idempotency key per schedule slot.
