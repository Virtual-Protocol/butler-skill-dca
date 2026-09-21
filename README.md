Buys a fixed dollar amount of one token on a schedule, and nothing else.

Each fire buys `SIZE_USD` of `TOKEN` at whatever the price is, then leaves a quiet
note in the duty's thread. Dollar-cost averaging: the same size every time, so the
size is the decision and the timing is not.

## What it will not do

- **Look at the price.** There is no dip check, no condition, no "only if". An owner
  who wants one is asking for a different duty — a `timer` whose code fetches the
  figure itself and decides.
- **Buy twice for one slot.** Every buy is keyed on the schedule *slot*, not the
  instant it fired, so a catch-up after a restart and the fire it is catching up on
  are one buy. The ledger answers the second one `replay`.
- **Exceed `MAX_PER_DAY`**, however often the schedule fires. The cap is counted in
  UTC days inside the duty's own state and survives a restart, so a duty that
  restarted does not get a fresh allowance.
- **Sell, ever.** It only buys.
- **Spend before the owner funds it.** It spends through the pocket, which starts
  empty; until it is funded every buy becomes an approval card.

## Settings

| Name | Unit | Default | Means |
| --- | --- | --- | --- |
| `TOKEN` | address or symbol | required | what to buy. An address is exact; a bare symbol is resolved by the rail and may land on a wrapper |
| `SIZE_USD` | US dollars per buy | required | minimum 2 — the swap route's own floor, below which the leg comes back as a wire error |
| `CHAIN_ID` | chain id | unset | which chain to buy on. Omit to let the rail choose |
| `MAX_PER_DAY` | buys per UTC day | 24 | a ceiling the duty keeps on itself, independent of the schedule |
| `SIZING` | — | `fixed` | fixed-size by definition; it takes no other value |

`TOKEN` and `SIZE_USD` are the only two an owner must decide. `CHAIN_ID` is worth
setting only when they named a chain, and `MAX_PER_DAY` only when they asked for a
ceiling tighter than the schedule.

## Trigger

One `timer` — either a time of day in the owner's zone, or an interval:

```json
{ "kind": "timer", "dailyAt": "09:00", "timezone": "Asia/Singapore" }
```

A `dailyAt` whose slot has already passed today fires today.
