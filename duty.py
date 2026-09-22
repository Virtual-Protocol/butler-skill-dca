"""Buy a fixed dollar amount of one token on a schedule.

Dollar-cost averaging: the same size every fire, whatever the price. Each buy
is keyed on the schedule SLOT rather than on the instant it fired, so a
catch-up after a restart and the scheduled fire it is catching up on are one
buy — bevo-server's ledger answers the second one `replay`.

It buys exactly the token the owner confirmed, on the chain they confirmed,
and resolves nothing itself: TOKEN is a contract address and every buy
carries CHAIN_ID. A ticker buys nothing — see `unconfirmed()`.

The program keeps no count of its own. What it may spend without asking is
the pocket the owner funds in the app, and bevo-server holds that line.

Settings: TOKEN (a contract address, or ETH / BNB / SOL for a chain's own
coin), CHAIN_ID, SIZE_USD.
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

NAME = os.environ.get("BEVO_SERVICE_NAME") or "dca"

#: The swap route's own minimum. A smaller leg comes back as a wire error the
#: loop would read as an outage rather than as a decision.
SPOT_MIN_USD = 2.0

EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

#: Solana's id on the rail — the one chain a mint can live on.
SOLANA_CHAIN_ID = 1151111081099710

#: A chain's own coin has no contract address, so it goes by its ticker — but
#: only on a chain where that ticker IS the native coin. On any other chain the
#: same ticker is a bridged token, which has an address of its own.
NATIVE_CHAINS = {
    "ETH": (1, 8453, 42161, 4663),
    "BNB": (56,),
    "SOL": (SOLANA_CHAIN_ID,),
}


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


def unconfirmed(token, chain):
    """Why TOKEN on CHAIN_ID is not one exact token, or None when it is.

    A ticker is not a token: the rail resolves one to whichever deployment it
    ranks first, which can be a wrapper or a lookalike, and can change from
    one fire to the next. An address names one deployment, and only on a
    chain of its own kind — a mint lives on Solana, a 0x address never does.
    """
    text = str(token or "").strip()
    if not text:
        return "no TOKEN set"
    if chain is None:
        return "no CHAIN_ID set"
    if EVM_ADDRESS.match(text):
        if chain == SOLANA_CHAIN_ID:
            return "TOKEN %s is an EVM address, but CHAIN_ID is Solana" % text
        return None
    if SOLANA_ADDRESS.match(text):
        if chain != SOLANA_CHAIN_ID:
            return "TOKEN %s is a Solana mint, but CHAIN_ID is %s" % (text, chain)
        return None
    ticker = text.lstrip("$").upper()
    if ticker in NATIVE_CHAINS:
        if chain in NATIVE_CHAINS[ticker]:
            return None
        return "%s is not chain %s's own coin, so it needs its address on that chain" % (
            ticker,
            chain,
        )
    return "TOKEN %s is a ticker, not a contract address" % text


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


def say(text):
    """`bevo.log()`, flattened onto one line.

    An error the rail echoed is untrusted text, and a newline inside it would
    start a line of its own in `duty_logs` — one that reads as if this
    program, or the supervisor, wrote it.
    """
    bevo.log(" ".join(str(text).split()))


def slot_key(slot):
    """The slot, in the grammar an idempotency key allows.

    `@` and `/` appear in a zoned slot (`2026-01-02T09:00@Asia/Singapore`)
    and in nothing bevo-server's key pattern accepts, so they become `-`.
    Every other character the slot can hold is already legal.
    """
    return str(slot).replace("@", "-").replace("/", "-")


PROBLEM = unconfirmed(TOKEN, CHAIN_ID)
if PROBLEM:
    # Said once, when the program starts: every fire would say the same thing,
    # and nothing but a settings change from the owner can fix it.
    bevo.notify(
        "%s buys nothing until its token and chain are confirmed: %s." % (NAME, PROBLEM)
    )

for tick in bevo.ticks():
    if PROBLEM:
        say("skipped %s: %s" % (tick.slot, PROBLEM))
        continue
    if tick.slot is None:
        say("skipped: the fire carried no time, so there is no slot to key on")
        continue
    if SIZE_USD < SPOT_MIN_USD:
        say(
            "skipped %s: spot buys are $%s minimum and SIZE_USD is $%s"
            % (tick.slot, fmt(SPOT_MIN_USD), fmt(SIZE_USD))
        )
        continue

    key = "buy:%s:slot:%s" % (bevo.SERVICE_ID, slot_key(tick.slot))
    ref = token_ref(TOKEN)
    args = [
        "--token-in", "usdc", "--amount-in", fmt(SIZE_USD),
        "--token-out", ref, "--chain-out", str(CHAIN_ID),
    ]
    ok, summary = filed(args, key, "Buy %s" % ref)
    if ok:
        bevo.notify(("%s: %s" % (NAME, summary))[:500], quiet=True)
    else:
        say("skipped %s: %s" % (tick.slot, summary))
