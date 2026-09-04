# butler-skill-template

Start here to build a Butler skill. Click **Use this template** on GitHub (or
`gh repo create <you>/butler-skill-<name> --template Virtual-Protocol/butler-skill-template --public`),
then hand your Claude the hub README and the task:

> Read https://github.com/Virtual-Protocol/butler-skills/blob/main/README.md — now build this skill: …

The files here are the scaffold the hub's validator expects: `SKILL.md` (every
section and `[FIXED]`/`[ADAPT]` marker pre-filled with a `TODO` the validator
rejects), `duty.py` (delete it if the skill has no `duty` mode), `CHANGELOG.md`,
and a CI workflow. A skill is the delta over what the Butler container already
teaches its agent — never restate command grammar, safety invariants, budgets or
routing; write only what is specific to this task.

## Validate

No Butler account, container or registry checkout needed — the hub publishes its
validator and replay harness as standalone files:

```bash
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/replay.py
python3 validate.py --standalone .
python3 replay.py --standalone . --fixture trade-activity-page
```

`replay.py` downloads `stub_bevo.py` and any fixture it needs from the same site when
they are not already next to it (when there is no `duty.py` it prints "nothing to
replay" and exits 0). The downloaded files are in this template's `.gitignore` — they
are never part of the skill.

CI runs the same two checks on every push through one step,
`.github/workflows/validate.yml`:

```yaml
- uses: Virtual-Protocol/butler-skills/.github/actions/validate@main
```

## Ship

When it validates: tag `v1.0.0`, then open a PR to
[Virtual-Protocol/butler-skills](https://github.com/Virtual-Protocol/butler-skills)
adding your repo as a submodule under `skills/<name>` at that tag. Maintainers
review the pinned commit; Butler containers clone exactly that commit. Names
starting with `butler-` are reserved for the Butler team; names starting with
`bevo-` are refused (that prefix is the container's own bundled-skill namespace).
