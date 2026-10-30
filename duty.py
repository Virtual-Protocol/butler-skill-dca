"""Buy a fixed dollar amount of one token or tokenized stock on a schedule.

Dollar-cost averaging: the same size every fire, whatever the price. Each buy
is keyed on the schedule SLOT rather than on the instant it fired, so a
catch-up after a restart and the scheduled fire it is catching up on are one
buy — bevo-server's ledger answers the second one `replay`.

It resolves nothing itself: every buy is one exact shape read from the
settings — a contract on a chain, a chain's own coin, or a tokenized stock.
Anything looser buys nothing — see `order()`.

Without BUYS it buys until the owner pauses it, and keeps no count. With
BUYS it finishes itself after that many turns, and a turn is counted only once
it resolved: a buy that EXECUTED, or one declined or failed, which uses up its
turn and is never placed again. An approval card that is still up, or an
order accepted but not yet executed, is placed, not bought — it can still
fail. The count lives in `bevo.state` under the settings it was made for, so
a re-run (a new RUN) or any changed setting starts from zero.

What it may spend without asking is the pocket the owner funds in the app,
and bevo-server holds that line.

Settings: TOKEN (as the owner named it — a ticker or an address), ADDRESS
(a crypto ticker's contract), CHAIN_ID, SIZE_USD, BUYS, RUN.
"""

import bevo
import json
import os
import re
import subprocess
import time

PARAMS = json.loads(os.environ.get("PARAMS", "{}"))

TOKEN = PARAMS.get("TOKEN")
ADDRESS = PARAMS.get("ADDRESS")
CHAIN_ID = PARAMS.get("CHAIN_ID")
SIZE_USD = PARAMS.get("SIZE_USD") or 0
BUYS = PARAMS.get("BUYS") or 0
RUN = PARAMS.get("RUN")

NAME = os.environ.get("BEVO_SERVICE_NAME") or "dca"

#: The swap route's own minimum. A smaller leg comes back as a wire error the
#: loop would read as an outage rather than as a decision.
SPOT_MIN_USD = 2.0

#: What `/stock-limits` answers when it cannot say, and what a failed read
#: falls back to — bevo-server's own default for a tokenized stock.
STOCK_MIN_DEFAULT_USD = 5.0

#: How long a fire waits for the buy it just placed to settle, so a buy that
#: executes in seconds is counted on the fire that placed it.
SETTLE_WAIT_S = 20
LEDGER_POLL_S = 4

#: What a declined or failed buy is, in the approval column of the ledger.
DROPPED_APPROVALS = ("rejected", "superseded", "expired", "failed")

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
    """Run one `acp trade` and read what it answered. Returns (kind, summary),
    kind one of:

    - `executed`: the trade went through.
    - `asked`: an approval card is in front of the owner; nothing bought yet.
    - `placed`: accepted and in flight; nothing bought yet, and it can fail.
    - `wait`: not filed, because the pocket card is unanswered or the pocket is
      empty. A wait, not a failure.
    - `refused`: turned down; nothing was bought.
    - `unknown`: the answer was unreadable, so the buy may or may not have
      landed.

    `--idempotency-key` is the last pair of the argv and is written out
    literally, which is what makes a catch-up fire a replay the ledger
    recognises rather than a second buy.

    An unparseable answer is `unknown`, never "refused": the request may have
    landed. `bevo.exec_status(key)` is the one way to find out, and re-running
    with a NEW key is how one buy becomes two.
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
        return "unknown", (
            "%s — outcome UNKNOWN, the rail said nothing readable (exec_status: %s). "
            "Never re-run this with a new key." % (sentence, state)
        )
    if answer.get("executed"):
        return "executed", "%s — executed" % sentence
    if answer.get("asked"):
        return "asked", "%s — waiting for your approval" % sentence
    if answer.get("ok") or answer.get("status") == "accepted":
        return "placed", "%s — placed, executing" % sentence
    if answer.get("code") in ("pocket_pending", "pocket_empty"):
        # bevo-server's 402: the owner has not answered this duty's pocket
        # card yet, or has not funded it, so nothing was filed.
        return "wait", "%s — waiting: %s" % (sentence, answer.get("error") or answer.get("code"))
    if answer.get("unrecognized"):
        # Not a refusal: the server answered something, and it may have filed.
        # The summary reaches the owner's notes, so it says what they can do.
        return "unknown", (
            "%s — unconfirmed: the server answered %r; check Activity before counting it"
            % (sentence, answer.get("status"))
        )
    why = answer.get("error") or answer.get("status")
    return "refused", "%s — refused: %s" % (sentence, why) if why else "%s — refused" % sentence


def ledger_verdict(row):
    """What the ledger row says became of a buy, in `bevo.settled()`'s words.

    `manual` never changes once the owner answers the card; only the approval
    column does, and `confirmed` there is the trade having executed.
    """
    state = row.get("state")
    approval = row.get("approvalStatus")
    if state == "executed" or (state == "manual" and approval == "confirmed"):
        return "executed"
    if state == "refused" or (state == "manual" and approval in DROPPED_APPROVALS):
        return "dropped"
    if state == "manual" and approval == "pending":
        return "approval"
    if state in ("unknown", "not_found"):
        return "unknown"
    return "waiting"


def settled(key, wait=0):
    """executed | approval | waiting | dropped | unknown, for one placed buy.

    The hub index is shared with containers that predate `bevo.settled()`, so
    on those the same verdict is read off `bevo.exec_status()`.
    """
    if hasattr(bevo, "settled"):
        return bevo.settled(key, route="trade", wait=wait)
    verdict = "waiting"
    for attempt in range(1 + int(wait) // LEDGER_POLL_S):
        if attempt:
            time.sleep(LEDGER_POLL_S)
        try:
            verdict = ledger_verdict(bevo.exec_status(key) or {})
        except bevo.BevoError:
            # An unread ledger says nothing about the buy: ask again later.
            verdict = "waiting"
        if verdict != "waiting":
            break
    return verdict


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


def stock_floor(ticker):
    """The smallest buy the venues take for this tokenized stock right now.

    Per listing, not a constant: $5 on most tickers and $22 on the illiquid
    tail, the cost buffer included, and it moves as venues go thin — so it is
    read on every fire. bevo-server computes it with the rule the planner gates
    on. A read that fails falls back to the server's own default and lets the
    rail decide.
    """
    try:
        return float(bevo.read("/stock-limits", {"ticker": ticker})["minUsd"])
    except (bevo.BevoError, KeyError, TypeError, ValueError):
        return STOCK_MIN_DEFAULT_USD


def tally_key():
    """Where the count lives: under the settings it counts for, so a re-run
    with a new RUN, or any changed setting, starts from zero."""
    return "count:" + json.dumps(
        [token_ref(TOKEN), ADDRESS, CHAIN_ID, SIZE_USD, BUYS, RUN], separators=(",", ":")
    )


def load_tally():
    name = tally_key()
    for other in [k for k in bevo.state.keys() if k.startswith("count:") and k != name]:
        del bevo.state[other]
    tally = dict(bevo.state.get(name) or {})
    for field in ("bought", "skipped", "unsure"):
        tally.setdefault(field, 0)
    # `placed` is still being settled; `filed` is every key handed to the rail
    # this run, so a catch-up fire on a slot already filed is never counted twice.
    tally.setdefault("placed", [])
    tally.setdefault("filed", [])
    return tally


def save_tally(tally):
    bevo.state[tally_key()] = tally


def resolved(tally):
    return tally["bought"] + tally["skipped"] + tally["unsure"]


def can_buy(tick):
    """Whether this fire may file a buy — every reason it may not is logged."""
    if tick.slot is None:
        say("skipped: the fire carried no time, so there is no slot to key on")
        return False
    if SIZE_USD < SPOT_MIN_USD:
        say(
            "skipped %s: spot buys are $%s minimum and SIZE_USD is $%s"
            % (tick.slot, fmt(SPOT_MIN_USD), fmt(SIZE_USD))
        )
        return False
    if STOCK:
        floor = stock_floor(STOCK)
        if SIZE_USD < floor:
            say(
                "skipped %s: %s buys are $%s minimum and SIZE_USD is $%s"
                % (tick.slot, STOCK, fmt(floor), fmt(SIZE_USD))
            )
            return False
    return True


def note_bought(tally):
    bevo.notify(
        "%s: Bought %d of %d: $%s %s" % (NAME, tally["bought"], BUYS, fmt(SIZE_USD), LABEL),
        quiet=True,
    )


def slot_buy_key(tick):
    return "buy:%s:slot:%s" % (bevo.SERVICE_ID, slot_key(tick.slot))


def buy_once(tick):
    """dca@9's fire, worded honestly: one buy for the slot, no count."""
    if not can_buy(tick):
        bevo.status("skipped")
        return
    kind, summary = filed(ARGS, slot_buy_key(tick), "Buy %s" % LABEL)
    if kind == "wait":
        # The pocket is unanswered or empty, so no buy has run yet: the row
        # keeps saying when the first one is, never "failed".
        say("waiting %s: %s" % (tick.slot, summary))
        bevo.status("starting")
    elif kind in ("executed", "asked", "placed"):
        bevo.notify(("%s: %s" % (NAME, summary))[:500], quiet=True)
        if kind == "executed":
            bevo.status("bought")
        elif kind == "asked":
            bevo.status("approval")
        else:
            bevo.status("placed")
    else:
        say("skipped %s: %s" % (tick.slot, summary))
        bevo.status("failed")


def count_once(tick, tally):
    """One fire of a BUYS run: file a buy if a turn is free, then settle every
    buy still placed, and finish once every turn has resolved."""
    skipped_fire = False
    fresh = None
    if resolved(tally) + len(tally["placed"]) < BUYS:
        if not can_buy(tick):
            skipped_fire = True
        elif slot_buy_key(tick) in tally["filed"]:
            say("skipped %s: this slot's buy is already filed" % tick.slot)
        else:
            key = slot_buy_key(tick)
            kind, summary = filed(ARGS, key, "Buy %s" % LABEL)
            say("%s: %s" % (tick.slot, summary))
            if kind != "wait":
                tally["filed"].append(key)
            if kind == "executed":
                tally["bought"] += 1
                note_bought(tally)
            elif kind in ("asked", "placed"):
                tally["placed"].append(key)
                fresh = key
            elif kind == "refused":
                tally["skipped"] += 1
                bevo.notify(
                    ("%s: %s — nothing was bought; that turn is used up" % (NAME, summary))[:500],
                    quiet=True,
                )
            elif kind == "unknown":
                tally["unsure"] += 1
                bevo.notify(
                    ("%s: %s — counted as unconfirmed; check Activity" % (NAME, summary))[:500],
                    quiet=True,
                )
            save_tally(tally)

    awaiting = False
    for key in list(tally["placed"]):
        verdict = settled(key, wait=SETTLE_WAIT_S if key == fresh else 0)
        if verdict == "executed":
            tally["placed"].remove(key)
            tally["bought"] += 1
            save_tally(tally)
            note_bought(tally)
        elif verdict == "dropped":
            tally["placed"].remove(key)
            tally["skipped"] += 1
            save_tally(tally)
            bevo.notify(
                "%s: a buy was declined or failed — nothing was bought; that turn is used up"
                % NAME,
                quiet=True,
            )
        elif verdict == "unknown":
            tally["placed"].remove(key)
            tally["unsure"] += 1
            save_tally(tally)
        elif verdict == "approval":
            awaiting = True

    if resolved(tally) >= BUYS:
        summary = "%d of %d buys of $%s %s went through" % (
            tally["bought"], BUYS, fmt(SIZE_USD), LABEL
        )
        if tally["skipped"]:
            summary += ", %d declined or failed" % tally["skipped"]
        if tally["unsure"]:
            summary += ", %d unconfirmed — check Activity" % tally["unsure"]
        bevo.done(summary)

    if awaiting:
        bevo.status("approval_count", n=tally["bought"], total=BUYS)
    elif skipped_fire:
        bevo.status("skipped")
    elif not tally["filed"]:
        # Nothing filed yet — a pocket still unanswered or empty included.
        bevo.status("starting")
    else:
        bevo.status("progress", n=tally["bought"], total=BUYS)


ARGS, PROBLEM = order(TOKEN, ADDRESS, CHAIN_ID, SIZE_USD)
#: The ticker when ARGS is the tokenized-stock shape — the one `order()`
#: answers with `--token` rather than `--token-in`.
STOCK = ARGS[1] if ARGS and ARGS[0] == "--token" else None
#: Named the way the title names it: TOKEN, the ticker or the address the
#: owner gave, never the ADDRESS behind a ticker.
LABEL = token_ref(TOKEN)
if PROBLEM:
    # Said once, when the program starts: every fire would say the same thing,
    # and nothing but a settings change from the owner can fix it.
    bevo.notify(
        "%s buys nothing until its token and chain are confirmed: %s." % (NAME, PROBLEM)
    )

if PROBLEM:
    bevo.status("paused")

# The owner's Duties row: recipe.json `status` words each state. A state is
# reported on every fire, so the row always says what happened last and when
# the next buy is.
for tick in bevo.ticks():
    if PROBLEM:
        say("skipped %s: %s" % (tick.slot, PROBLEM))
        bevo.status("paused")
        continue
    if BUYS:
        count_once(tick, load_tally())
    else:
        buy_once(tick)
