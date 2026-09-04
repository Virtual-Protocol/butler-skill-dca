# Changelog

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
