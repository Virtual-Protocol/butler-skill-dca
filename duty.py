"""Buy a fixed dollar amount of one token or tokenized stock on a schedule.

Dollar-cost averaging: the same size every fire, whatever the price. Each buy
is keyed on the schedule SLOT rather than on the instant it fired, so a
catch-up after a restart and the scheduled fire it is catching up on are one
buy — bevo-server's ledger answers the second one `replay`.

It resolves nothing itself: every buy is one exact shape read from the
settings — a contract on a chain, a chain's own coin, or a tokenized stock.
Anything looser buys nothing — see `order()`.

The program keeps no count of its own. What it may spend without asking is
the pocket the owner funds in the app, and bevo-server holds that line.

Settings: TOKEN (as the owner named it — a ticker or an address), ADDRESS
(a crypto ticker's contract), CHAIN_ID, SIZE_USD.
"""

import bevo
import json
import os
import re
import subprocess

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

TOKEN = PARAMS.get("TOKEN")
ADDRESS = PARAMS.get("ADDRESS")
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


def order(token, address, chain, size):
    """The `acp trade` arguments for one buy, as (args, None) — or (None, why not).

    Exactly one of three shapes, so the rail never picks the token:

    - a contract (ADDRESS, or TOKEN when it is an address) on CHAIN_ID, of
      its own kind: a mint lives on Solana and needs no CHAIN_ID, and a 0x
      address never lives on Solana.
    - a chain's own coin (ETH, BNB, SOL), on a chain whose coin it is.
    - a tokenized stock: any other ticker, with no ADDRESS and no CHAIN_ID.
      Bought in the stock shape, which the rail routes to whichever venue
      returns the most shares.

    A ticker with a chain and no address is refused. On that chain the rail
    would buy whichever deployment it ranks first (a wrapper or a lookalike,
    and not always the same one), and an explicit chain also switches off
    the server's own alias and verified-ticker checks.
    """
    name = str(token or "").strip()
    pin = str(address or "").strip()
    if not name:
        return None, "no TOKEN set"
    if EVM_ADDRESS.match(name) or SOLANA_ADDRESS.match(name):
        if pin and token_ref(pin) != token_ref(name):
            return None, "TOKEN %s and ADDRESS %s are different contracts" % (name, pin)
        pin = name
    if pin:
        if SOLANA_ADDRESS.match(pin):
            if chain not in (None, SOLANA_CHAIN_ID):
                return None, "%s is a Solana mint, but CHAIN_ID is %s" % (pin, chain)
            chain = SOLANA_CHAIN_ID
        elif not EVM_ADDRESS.match(pin):
            return None, "ADDRESS %s is not a contract address" % pin
        elif chain is None:
            return None, "%s has no CHAIN_ID, and a 0x address can live on any EVM chain" % pin
        elif chain == SOLANA_CHAIN_ID:
            return None, "%s is an EVM address, but CHAIN_ID is Solana" % pin
        ref = token_ref(pin)
    else:
        ref = token_ref(name)
        chains = NATIVE_CHAINS.get(ref)
        if chains is None:
            if chain is not None:
                return None, "TOKEN %s is a ticker with a CHAIN_ID but no ADDRESS" % ref
            return ["--token", ref, "--amount-usdc", fmt(size)], None
        if chain is None and len(chains) == 1:
            chain = chains[0]
        if chain not in chains:
            where = " / ".join(str(c) for c in chains)
            if chain is None:
                return None, "%s needs a CHAIN_ID — it is the own coin of chain %s" % (ref, where)
            return None, "%s is the own coin of chain %s, not of chain %s" % (ref, where, chain)
    args = ["--token-in", "usdc", "--amount-in", fmt(size)]
    return args + ["--token-out", ref, "--chain-out", str(chain)], None


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


ARGS, PROBLEM = order(TOKEN, ADDRESS, CHAIN_ID, SIZE_USD)
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
    # Named the way the title names it: TOKEN, the ticker or the address the
    # owner gave, never the ADDRESS behind a ticker.
    ok, summary = filed(ARGS, key, "Buy %s" % token_ref(TOKEN))
    if ok:
        bevo.notify(("%s: %s" % (NAME, summary))[:500], quiet=True)
    else:
        say("skipped %s: %s" % (tick.slot, summary))
