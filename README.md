# butler-skill-dca — buy a fixed amount of one token on a schedule

**This duty spends your money.** Every buy goes through the pocket you arm it
with; a buy over that pocket's limit becomes an approval card instead.

## What it does

One trigger, `timer` — either a time of day in your zone, or an interval:

```json
{ "kind": "timer", "dailyAt": "09:00", "timezone": "Asia/Singapore" }
```

On each fire it buys `SIZE_USD` of `TOKEN`, then notes it quietly in this
duty's thread. Nothing else: no price check, no "only if it dipped". If you
want a condition, ask Butler to write the duty as code instead.

## Settings

| Name | Type | Default | Meaning |
| --- | --- | --- | --- |
| `TOKEN` | string | — (required) | an address, or a symbol the rail can resolve |
| `CHAIN_ID` | integer | — | the chain to buy on; omit to let the rail choose |
| `SIZING` | `"fixed"` | `fixed` | dollar-cost averaging is fixed-size by definition |
| `SIZE_USD` | number | — (required) | dollars per buy |
| `MAX_PER_DAY` | integer | `24` | at most this many buys a day, whatever the schedule says |

## How it is used

An owner asks their butler for recurring buys, and the butler files
`duty_create {recipe: "dca@2", params: {...}}`.

## What it will not do

- Buy twice for one slot. Every buy is keyed on the schedule's **slot**, so a
  catch-up fire after a restart and the fire it is catching up on are one buy,
  never two.
- Keep buying past `MAX_PER_DAY`, even if the schedule keeps firing — the cap
  is a limit the duty keeps on itself in its own state, and it survives a
  restart.
- Spend anything before it is funded. The duty spends through the owner's
  **pocket**, which starts empty and only the owner can fund — so an unfunded
  duty asks before it buys.
