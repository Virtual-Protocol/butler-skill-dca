Buys a fixed dollar amount of one token or tokenized stock on a schedule, and nothing
else.

Each fire buys `SIZE_USD` of it at whatever the price is, then leaves a quiet note in
the duty's thread. Dollar-cost averaging: the same size every time, so the size is the
decision and the timing is not.

## What it buys

It resolves nothing itself. Every buy is one exact shape, read from the settings:

| The owner named | `TOKEN` | `ADDRESS` | `CHAIN_ID` | Bought |
| --- | --- | --- | --- | --- |
| a crypto token by ticker | the ticker | its contract | its chain | that contract, on that chain |
| a crypto token by address | the address | — | its chain (none for a mint) | that contract, on that chain |
| a chain's own coin | `ETH`, `BNB` or `SOL` | — | a chain whose coin it is | that coin |
| a tokenized stock | the ticker | — | — | the stock, on whichever venue returns the most shares |

A mint lives only on Solana, so it needs no `CHAIN_ID`; nor do `BNB` (BSC) and `SOL`.
`ETH` is the own coin of Ethereum, Base, Arbitrum and Robinhood, so it needs one.

When the owner's words fit more than one token or chain, the settings hold the match
they picked, shown to them with its name, chain and address. Anything looser buys
nothing — a ticker with a `CHAIN_ID` but no `ADDRESS`, a mint on an EVM chain, `ETH`
on BSC. The owner gets one note when the program starts, and each fire logs the
reason. A ticker alone on a chain would let the rail buy whichever deployment it ranks
first, which can be a wrapper or a lookalike, and can change between fires.

The title and every note name it by `TOKEN`: the ticker, or the address when the owner
gave one.

## What it will not do

- **Look at the price.** There is no dip check, no condition, no "only if". An owner
  who wants one is asking for a different duty — a `timer` whose code fetches the
  figure itself and decides.
- **Buy twice for one slot.** Every buy is keyed on the schedule *slot*, not the
  instant it fired, so a catch-up after a restart and the fire it is catching up on
  are one buy. The ledger answers the second one `replay`.
- **Sell, ever.** It only buys.
- **Pick a stock's venue.** A stock buy goes to whichever venue returns the most
  shares; the rail takes no venue on a buy.
- **Spend before the owner funds it.** It spends through the pocket, which starts
  empty; until it is funded every buy becomes an approval card. Once funded, the pocket
  is the only limit on what it spends: the duty keeps no daily count of its own, and
  the server refuses a buy the pocket can't cover.

## Settings

| Name | Unit | Default | Means |
| --- | --- | --- | --- |
| `TOKEN` | ticker or address | required | the token as the owner named it |
| `ADDRESS` | contract address | unset | a crypto ticker's exact contract, on `CHAIN_ID` |
| `CHAIN_ID` | numeric chain id | unset | Base `8453`, Ethereum `1`, BSC `56`, Arbitrum `42161`, Robinhood `4663`, Solana `1151111081099710` |
| `SIZE_USD` | US dollars per buy | required | minimum 2 — the swap route's own floor, below which the leg comes back as a wire error |
| `SIZING` | — | `fixed` | fixed-size by definition; it takes no other value |

## Trigger

One `timer` — either a time of day in the owner's zone, or an interval:

```json
{ "kind": "timer", "dailyAt": "09:00", "timezone": "Asia/Singapore" }
```

A `dailyAt` whose slot has already passed today fires today.
