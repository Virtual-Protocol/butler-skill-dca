Buys a fixed dollar amount of one exact token, on one chain, on a schedule — and
nothing else.

Each fire buys `SIZE_USD` of `TOKEN` on `CHAIN_ID` at whatever the price is, then
leaves a quiet note in the duty's thread. Dollar-cost averaging: the same size every
time, so the size is the decision and the timing is not.

## The token is confirmed, not looked up

`TOKEN` and `CHAIN_ID` are one decision, made by the owner before the duty is filed:
the token they picked from its matches, each shown with its name, chain and address.
The program resolves nothing itself. It buys only

- a contract address whose kind matches `CHAIN_ID` — `0x…` on an EVM chain, a mint
  (verbatim, case and all) on Solana — or
- a chain's own coin by its ticker, on that chain: `ETH` on Ethereum, Base, Arbitrum
  or Robinhood, `BNB` on BSC, `SOL` on Solana.

Anything else — a ticker such as `VIRTUAL` or `BTC`, a mint with an EVM chain — buys
nothing: the owner gets one note when the program starts, and each fire logs the
reason. A ticker resolves on the rail to whichever deployment ranks first, which can
be a wrapper or a lookalike, and can change from one fire to the next.

## What it will not do

- **Look at the price.** There is no dip check, no condition, no "only if". An owner
  who wants one is asking for a different duty — a `timer` whose code fetches the
  figure itself and decides.
- **Buy twice for one slot.** Every buy is keyed on the schedule *slot*, not the
  instant it fired, so a catch-up after a restart and the fire it is catching up on
  are one buy. The ledger answers the second one `replay`.
- **Sell, ever.** It only buys.
- **Buy a tokenized stock on its venue.** An address pins the buy to an on-chain
  token, so the stock venues are never used.
- **Spend before the owner funds it.** It spends through the pocket, which starts
  empty; until it is funded every buy becomes an approval card. Once funded, the pocket
  is the only limit on what it spends: the duty keeps no daily count of its own, and
  the server refuses a buy the pocket can't cover.

## Settings

| Name | Unit | Default | Means |
| --- | --- | --- | --- |
| `TOKEN` | contract address, or a native coin's ticker | required | the exact token the owner confirmed — see above |
| `CHAIN_ID` | numeric chain id | required | the chain it is on: Base `8453`, Ethereum `1`, BSC `56`, Arbitrum `42161`, Robinhood `4663`, Solana `1151111081099710` |
| `SIZE_USD` | US dollars per buy | required | minimum 2 — the swap route's own floor, below which the leg comes back as a wire error |
| `SIZING` | — | `fixed` | fixed-size by definition; it takes no other value |

`TOKEN`, `CHAIN_ID` and `SIZE_USD` are the three an owner decides. `{TOKEN}` in a
title renders the full address.

## Trigger

One `timer` — either a time of day in the owner's zone, or an interval:

```json
{ "kind": "timer", "dailyAt": "09:00", "timezone": "Asia/Singapore" }
```

A `dailyAt` whose slot has already passed today fires today.
