# butler-dca

Dollar-cost average in or out on a schedule — spot buy/sell or perp open/reduce, with the
owner's own size, cadence and conditions. One skill, published through the
[Butler Skill Hub](https://github.com/Virtual-Protocol/butler-skills).

- `SKILL.md` — the playbook (frontmatter + fixed sections; see the hub's
  [SKILL_STANDARD.md](https://github.com/Virtual-Protocol/butler-skills/blob/main/SKILL_STANDARD.md))
- `duty.py` — the code stage a `bevo-automation create --from-skill` duty runs
- `CHANGELOG.md` — one line per version; every change bumps `version` in SKILL.md and is tagged `vX.Y.Z`

## Validate before tagging

No Butler account, container or registry checkout needed:

```bash
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/validate.py
curl -sSLO https://virtual-protocol.github.io/butler-skills/tools/replay.py
python3 validate.py --standalone . --maintainer
python3 replay.py --standalone . --fixture trade-activity-page
```

`replay.py` downloads `stub_bevo.py` and any fixture it needs from the same site. Keep the
downloaded files out of the commit.

The default fixture is a trade feed this duty ignores by design — the "a foreign event never
trades" check. For a real run, replay a timer fixture of your own:

```bash
python3 replay.py --standalone . --fixture dca-timer --fixtures-dir ./local-fixtures \
  --env DCA_TOKEN=0x0b3e328455c4059eeb9e3f84b5543f74e24e7e1b --env DCA_USD_PER_RUN=25
```

In CI both are one step:

```yaml
- uses: Virtual-Protocol/butler-skills/.github/actions/validate@main
  with:
    maintainer: "true"
```
