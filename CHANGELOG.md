# Changelog

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
