"""Buy a fixed dollar amount of one token on a schedule.

Dollar-cost averaging: the same size every fire, whatever the price. Each buy
is keyed on the schedule SLOT rather than on the instant it fired, so a
catch-up after a restart and the scheduled fire it is catching up on are one
buy — bevo-server's ledger answers the second one `replay`.

The log is the duty's ledger. Every buy is written to it as a `requested`
line, with its dollar value, BEFORE it is sent, and the daily caps are counted
from those lines: `MAX_PER_DAY` buys and `MAX_USD_PER_DAY` dollars per UTC
day. The log is on the duty's volume, so a duty that restarted does not get a
fresh allowance. A buy bevo-server refuses definitively, before executing it
(a used-up pocket, a wallet that cannot cover it), writes a `released` line
that takes its `requested` line back out of the count.

Settings: TOKEN (an address, or a symbol the rail can resolve), CHAIN_ID,
SIZE_USD, MAX_PER_DAY, MAX_USD_PER_DAY.
"""

import bevo
import json
import os
import re
import subprocess
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

TOKEN = PARAMS.get("TOKEN")
CHAIN_ID = PARAMS.get("CHAIN_ID")
SIZE_USD = PARAMS.get("SIZE_USD") or 0
MAX_PER_DAY = PARAMS.get("MAX_PER_DAY") or 24
MAX_USD_PER_DAY = PARAMS.get("MAX_USD_PER_DAY") or 0

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
    if answer.get("status") == "refused" and answer.get("code") in RELEASED_BY:
        release(key)
        return False, "%s — refused: %s (not counted toward today's caps)" % (
            sentence,
            answer.get("error") or answer.get("code"),
        )
    return False, "%s — refused: %s" % (sentence, answer.get("error") or answer.get("status"))


#: `code`s bevo-server documents as a DEFINITIVE, pre-execution refusal: nothing
#: executed and nothing reserved, so the ledger line this duty wrote before sending
#: can be released. Never a 409 (in flight), a timeout, or an unparseable answer —
#: those may have landed, and releasing one of those could double-spend.
RELEASED_BY = frozenset({"pocket_empty", "wallet_short"})


# ── the ledger: what this duty has asked for, from its own log ───────────────

#: The supervisor appends every line this program prints to `duty.log` in its
#: working directory, and renames it to `duty.log.1` once it passes 1 MB (one
#: generation kept). Oldest first.
LOG_FILES = ("duty.log.1", "duty.log")

#: A ledger line, only ever written by `record()`. Anchored at the start of
#: the line (after the supervisor's stamp, when the line got one), which is
#: why `say()` keeps every other line on one line.
REQUESTED = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}T[\d:.]+Z )?requested (\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z"
    r" key=(\S+) route=(\S+) usd=(\d+(?:\.\d+)?)\s*$"
)

#: A ledger line, only ever written by `release()`. Marks a `requested` key as
#: refused before it executed, so `requested()` must not count it.
RELEASED = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}T[\d:.]+Z )?released (\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z"
    r" key=(\S+)\s*$"
)

#: The supervisor's stamp at the start of a log line.
LOG_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})T")

#: Buys this process has requested: {key: (utc day, route, usd)}. The
#: supervisor writes a line down a moment after it is printed; this covers
#: that moment.
SENT = {}


def say(text):
    """`bevo.log()`, flattened onto one line.

    An error the rail echoed is untrusted text, and a newline inside it would
    start a line of its own — one that could read as a ledger entry. Only
    `record()` may begin a line with `requested`, and only `release()` may
    begin a line with `released`.
    """
    bevo.log(" ".join(str(text).split()))


def utc_day(now=None):
    return time.strftime("%Y-%m-%d", now or time.gmtime())


def requested(today):
    """Every buy the log says was requested: {key: (utc day, route, usd)}.

    A key is counted on the day it was FIRST requested; the same key sent
    again later is a replay, not a second buy. None when the log cannot vouch
    for the whole of `today`: the rotated file starts today, so today's
    earliest lines may have been rotated out of both files.
    """
    ledger = {}
    for name in LOG_FILES:
        try:
            with open(name, encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle):
                    if number == 0 and name == LOG_FILES[0]:
                        stamp = LOG_STAMP.match(line)
                        if stamp is None or stamp.group(1) >= today:
                            return None
                    match = REQUESTED.match(line)
                    if match:
                        day, key, route, usd = match.groups()
                        ledger.setdefault(key, (day, route, float(usd)))
                        continue
                    match = RELEASED.match(line)
                    if match:
                        _, key = match.groups()
                        ledger.pop(key, None)
        except OSError:
            continue
    for key, row in SENT.items():
        ledger.setdefault(key, row)
    return ledger


def cap_reached(key, usd):
    """Why this buy may not be requested today, or None.

    A key already in the ledger is a catch-up of a buy already counted: it
    goes out again under the same key (the ledger answers `replay`, or places
    it if the first attempt never landed) and is not counted twice.
    """
    today = utc_day()
    ledger = requested(today)
    if ledger is None:
        return (
            "the log no longer reaches back to the start of today, so the daily "
            "caps cannot be counted"
        )
    if key in ledger:
        return None
    buys = [row for row in ledger.values() if row[0] == today]
    if len(buys) >= MAX_PER_DAY:
        return "%d per day reached" % MAX_PER_DAY
    spent = sum(row[2] for row in buys)
    if MAX_USD_PER_DAY > 0 and spent + usd > MAX_USD_PER_DAY:
        return "$%s of the $%s MAX_USD_PER_DAY already requested today" % (
            fmt(spent),
            fmt(MAX_USD_PER_DAY),
        )
    return None


def record(key, usd):
    """Write the buy down BEFORE it is sent. Returns why it may not be, or None.

    The other order double-spends whenever the container dies between the
    rail answering and the line being written, so a refused buy still counts.
    A key the ledger could not read back is refused here rather than sent
    uncounted.
    """
    if not re.fullmatch(r"\S+", key):
        return "the idempotency key %r could not be written to the ledger" % key
    now = time.gmtime()
    SENT.setdefault(key, (utc_day(now), "buy", float(fmt(usd))))
    bevo.log(
        "requested %s key=%s route=buy usd=%s"
        % (time.strftime("%Y-%m-%dT%H:%M:%SZ", now), key, fmt(usd))
    )
    return None


def release(key):
    """Undo `record()`: the server refused the buy before executing it.

    Only called for a code in `RELEASED_BY` — a refusal the server documents as
    definitive and pre-execution, so nothing was spent and nothing reserved. The
    key is free to count again if it is re-requested (on its new day).
    """
    if not re.fullmatch(r"\S+", key):
        return
    bevo.log(
        "released %s key=%s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), key)
    )
    SENT.pop(key, None)


def slot_key(slot):
    """The slot, in the grammar an idempotency key allows.

    `@` and `/` appear in a zoned slot (`2026-01-02T09:00@Asia/Singapore`)
    and in nothing bevo-server's key pattern accepts, so they become `-`.
    Every other character the slot can hold is already legal.
    """
    return str(slot).replace("@", "-").replace("/", "-")


for tick in bevo.ticks():
    if not TOKEN:
        say("skipped: no TOKEN set")
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
    why = cap_reached(key, SIZE_USD) or record(key, SIZE_USD)
    if why:
        say("skipped %s: %s" % (tick.slot, why))
        continue

    ref = token_ref(TOKEN)
    args = ["--token-in", "usdc", "--amount-in", fmt(SIZE_USD), "--token-out", ref]
    if CHAIN_ID is not None:
        args += ["--chain-out", str(CHAIN_ID)]
    ok, summary = filed(args, key, "Buy %s" % ref)
    if ok:
        bevo.notify(("%s: %s" % (NAME, summary))[:500], quiet=True)
    else:
        say("skipped %s: %s" % (tick.slot, summary))
