"""Buy a fixed dollar amount of one token on a schedule.

Dollar-cost averaging: the same size every fire, whatever the price. Each buy
is keyed on the schedule SLOT rather than on the instant it fired, so a
catch-up after a restart and the scheduled fire it is catching up on are one
buy — bevo-server's ledger answers the second one `replay`.

`MAX_PER_DAY` is a cap this duty keeps on itself, counted in UTC days inside
its own state and surviving a restart. A duty that restarted should not get a
fresh allowance.

Settings: TOKEN (an address, or a symbol the rail can resolve), CHAIN_ID,
SIZE_USD, MAX_PER_DAY.
"""

import bevo
import json
import os
import re
import subprocess

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

TOKEN = PARAMS.get("TOKEN")
CHAIN_ID = PARAMS.get("CHAIN_ID")
SIZE_USD = PARAMS.get("SIZE_USD") or 0
MAX_PER_DAY = PARAMS.get("MAX_PER_DAY") or 24

NAME = os.environ.get("BEVO_SERVICE_NAME") or "dca"

#: The swap route's own minimum. A smaller leg comes back as a wire error the
#: loop would read as an outage rather than as a decision.
SPOT_MIN_USD = 2.0

EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def fmt(number):
    """Trim a float to something the CLI parses and a human can read."""
    return ("%.8f" % float(number)).rstrip("0").rstrip(".")


def token_ref(value):
    """What identifies the token on the wire.

    An EVM address is lowercased, because two spellings of one address would
    derive two idempotency keys — one intent becoming two buys. A Solana mint
    is base58 and case-SENSITIVE, so it goes through verbatim.
    """
    text = str(value or "").strip()
    if EVM_ADDRESS.match(text):
        return text.lower()
    if SOLANA_ADDRESS.match(text):
        return text
    return text.lstrip("$").upper()


def answer_of(text):
    """The JSON `acp` printed, or None. None is NOT a refusal — see `filed()`."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except ValueError:
        start = text.find("{")
        if start < 0:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(text, start)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def filed(args, key, sentence):
    """Run one `acp trade` and read what it answered. Returns (ok, summary).

    `--idempotency-key` is the last pair of the argv and is written out
    literally, which is what makes a catch-up fire a replay the ledger
    recognises rather than a second buy.

    An unparseable answer is `unknown_outcome`, never "refused": the request
    may have landed. `bevo.exec_status(key)` is the one way to find out, and
    re-running with a NEW key is how one buy becomes two.
    """
    done = subprocess.run(
        ["acp", "trade", *args, "--idempotency-key", key],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    answer = answer_of(done.stdout)
    if answer is None:
        state = (bevo.exec_status(key) or {}).get("state")
        return False, (
            "%s — outcome UNKNOWN, the rail said nothing readable (exec_status: %s). "
            "Never re-run this with a new key." % (sentence, state)
        )
    if answer.get("executed"):
        return True, "%s — executed" % sentence
    if answer.get("asked"):
        return True, "%s — waiting for your owner's approval" % sentence
    if answer.get("ok"):
        return True, "%s — accepted, executing now" % sentence
    if answer.get("unrecognized"):
        return False, (
            "%s — the server answered %r, which this container does not recognise. "
            "Do NOT report it as done." % (sentence, answer.get("status"))
        )
    return False, "%s — refused: %s" % (sentence, answer.get("error") or answer.get("status"))


def slot_key(slot):
    """The slot, in the grammar an idempotency key allows.

    `@` and `/` appear in a zoned slot (`2026-01-02T09:00@Asia/Singapore`)
    and in nothing bevo-server's key pattern accepts, so they become `-`.
    Every other character the slot can hold is already legal.
    """
    return str(slot).replace("@", "-").replace("/", "-")


for tick in bevo.ticks():
    if not TOKEN:
        bevo.log("skipped: no TOKEN set")
        continue
    if tick.slot is None:
        bevo.log("skipped: the fire carried no time, so there is no slot to key on")
        continue
    if SIZE_USD < SPOT_MIN_USD:
        bevo.log(
            "skipped %s: spot buys are $%s minimum and SIZE_USD is $%s"
            % (tick.slot, fmt(SPOT_MIN_USD), fmt(SIZE_USD))
        )
        continue

    # Consumed here, before the buy is attempted: the other order
    # double-spends whenever the container dies between the rail answering
    # and the counter being written.
    if not bevo.allow("dca", per_day=MAX_PER_DAY, usd=SIZE_USD):
        bevo.log("skipped %s: %d per day reached" % (tick.slot, MAX_PER_DAY))
        continue

    ref = token_ref(TOKEN)
    args = ["--token-in", "usdc", "--amount-in", fmt(SIZE_USD), "--token-out", ref]
    if CHAIN_ID is not None:
        args += ["--chain-out", str(CHAIN_ID)]
    ok, summary = filed(args, "buy:%s:slot:%s" % (bevo.SERVICE_ID, slot_key(tick.slot)), "Buy %s" % ref)
    if ok:
        bevo.notify(("%s: %s" % (NAME, summary))[:500], quiet=True)
    else:
        bevo.log("skipped %s: %s" % (tick.slot, summary))
