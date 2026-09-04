---
name: _template
description: TODO one-sentence trigger description, start with the phrases an owner would say, <=160 chars
version: 0.1.0
metadata: {"openclaw":{"emoji":"TODO","requires":{"bins":["bevo-read"]}},"bevo":{"tier":"on-demand","modes":["one-off"],"moneyMoving":false,"keywords":["TODO"],"requires":{"routes":["GET /butler-read/TODO"],"features":[],"gates":[],"bins":["bevo-read"]},"params":[{"name":"TODO_PARAM","type":"string","required":true,"ask":"TODO ask phrase"}]}}
---

## When to use

TODO: the one sentence a Butler reads to decide this skill applies. Everywhere below, write only
the delta over what the container already teaches (AGENTS.md and the bundled skills): never
restate command grammar, safety invariants, budgets or routing — if you must point at one,
cite the AGENTS.md section.

## Before you start

TODO: reads/ids to resolve before doing anything (e.g. `bevo-read user <@handle>` -> principalId).

## Customize

TODO: walk through each `params` entry — what it changes, its default, its range, and which
numbered steps below are `[FIXED]` vs `[ADAPT]` because of it.

## One-off procedure

1. [FIXED] TODO first fixed step (a read).
2. [ADAPT] TODO an adapt step (apply the owner's wording).

## Duty procedure

TODO: trigger JSON, env mapping from params, the exact `bevo-automation create --from-skill _template@0.1.0 '<json>'`
call, and what to say about pending -> arm -> pocket.

1. [FIXED] TODO
2. [ADAPT] TODO

## Idempotency and retries

TODO: only required when `moneyMoving:true`. The key formula (from the source event id, never a
timestamp) plus one sentence — "any error or uncertainty: `bevo-read request <key>` first — do
not re-run". Do not list the 409 codes; the shim and AGENTS.md's money rule handle them.
Must contain the phrase: do not re-run.

## Failure handling

TODO: only the rows specific to this skill — not the generic idempotency / 4xx / pocket rows.

| Outcome | What to do |
| --- | --- |
| TODO | TODO |

## Limits

TODO: what this skill will not do — its own scope only, never the container's global rules.

## Say to the owner

TODO: the exact words to report success, in the owner's language.
