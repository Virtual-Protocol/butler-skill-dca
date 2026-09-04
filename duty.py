"""butler-dca duty — one DCA slice per scheduled tick.

One asset, one direction, one cadence. The tick's schedule SLOT (not the
moment it fired) is the idempotency key's source id, so a redelivered tick or
a restarted duty maps to a key that was already used and files nothing new.
See SKILL.md for the procedure this code implements.
"""
import json
import os
from datetime import datetime, timezone

import bevo

STATE_PATH = "state.json"
NOTES_PATH = "notified.json"
MAX_SLOTS = 500

SPOT_MIN_USD = 2.0
PERP_OPEN_MIN_USD = 15.0


def _num(raw, default):
    """A param that arrived as text; a missing or unparsable value is the
    skill's declared default, never a crash mid-schedule."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


ACTION = os.environ.get("DCA_ACTION", "buy").strip().lower()
TOKEN = os.environ.get("DCA_TOKEN", "").strip()
CHAIN_ID = os.environ.get("DCA_CHAIN_ID", "8453").strip()
USD_PER_RUN = _num(os.environ.get("DCA_USD_PER_RUN", "25"), 25.0)
SELL_QTY_PER_RUN = _num(os.environ.get("DCA_SELL_QTY_PER_RUN", "0"), 0.0)
PERP_SIDE = os.environ.get("DCA_PERP_SIDE", "long").strip().lower()
LEVERAGE = _num(os.environ.get("DCA_LEVERAGE", "2"), 2.0)
INTERVAL_SECONDS = int(_num(os.environ.get("DCA_INTERVAL_SECONDS", "86400"), 86400.0))
DAILY_AT = os.environ.get("DCA_DAILY_AT", "").strip()
MAX_PRICE = _num(os.environ.get("DCA_MAX_PRICE", "0"), 0.0)
MIN_PRICE = _num(os.environ.get("DCA_MIN_PRICE", "0"), 0.0)
MIN_CASH_USD = _num(os.environ.get("DCA_MIN_CASH_USD", "25"), 25.0)
MAX_RUNS = int(_num(os.environ.get("DCA_MAX_RUNS", "0"), 0.0))
TOTAL_BUDGET_USD = _num(os.environ.get("DCA_TOTAL_BUDGET_USD", "0"), 0.0)
ESCALATE = os.environ.get("DCA_ESCALATE", "false").strip().lower() in ("1", "true", "yes")


def label():
    """What to call the asset in a note to the owner: a perp symbol as-is, an
    address shortened — a 42-character hex string in a push notification is
    noise, not information."""
    if TOKEN.startswith("0x") and len(TOKEN) > 12:
        return f"{TOKEN[:6]}\u2026{TOKEN[-4:]}"
    return TOKEN or "this asset"


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def fmt(n):
    """A CLI number: never scientific notation, which the trade grammar cannot
    read back (0.00000012 must not become 1.2e-07)."""
    return f"{n:.8f}".rstrip("0").rstrip(".") or "0"


class State:
    """Slots already handled, plus what the ladder has done so far. The slot
    list is the order of record (a set has none, so trimming one drops
    arbitrary slots rather than the oldest)."""

    def __init__(self, path):
        self.path = path
        data = load_json(path, {})
        self.slots = list(data.get("slots", []))
        self.member = set(self.slots)
        self.runs = int(data.get("runs", 0))
        self.moved_usd = float(data.get("moved_usd", 0.0))

    def __contains__(self, slot):
        return slot in self.member

    def done(self, slot, ran=False, moved_usd=0.0):
        if slot not in self.member:
            self.slots.append(slot)
            self.member.add(slot)
            if len(self.slots) > MAX_SLOTS:
                dropped = self.slots[: len(self.slots) - MAX_SLOTS]
                self.slots = self.slots[-MAX_SLOTS:]
                self.member.difference_update(dropped)
        if ran:
            self.runs += 1
        self.moved_usd += moved_usd
        save_json(self.path, {"slots": self.slots, "runs": self.runs, "moved_usd": self.moved_usd})


class Notes:
    """One note per reason — a schedule that hits the same wall every tick
    must not spend the owner's notify budget on it every tick."""

    def __init__(self, path):
        self.path = path
        self.ids = list(load_json(path, {}).get("ids", []))
        self.member = set(self.ids)

    def once(self, note_id, text):
        if note_id in self.member:
            return
        self.ids.append(note_id)
        self.member.add(note_id)
        if len(self.ids) > MAX_SLOTS:
            dropped = self.ids[: len(self.ids) - MAX_SLOTS]
            self.ids = self.ids[-MAX_SLOTS:]
            self.member.difference_update(dropped)
        save_json(self.path, {"ids": self.ids})
        bevo.notify(text)


def slot_for(tick_at):
    """The schedule slot this tick belongs to. A daily cadence buckets by UTC
    date, an interval one by interval index — both map a redelivered tick to
    the SAME slot, which its raw timestamp never would."""
    raw = str(tick_at or "")
    fired = None
    if raw:
        try:
            fired = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            fired = None
    if fired is None:
        return raw or "unknown"
    if fired.tzinfo is None:
        fired = fired.replace(tzinfo=timezone.utc)
    if DAILY_AT:
        return fired.astimezone(timezone.utc).strftime("%Y-%m-%d")
    step = INTERVAL_SECONDS if INTERVAL_SECONDS > 0 else 86400
    return str(int(fired.timestamp()) // step)


def read_assets():
    try:
        return bevo.read("/user-assets")
    except bevo.BevoError as exc:
        bevo.log(f"dca: /user-assets unreadable ({exc}) — skipping this run")
        return None


def holding(assets):
    """The DCA_TOKEN row on DCA_CHAIN_ID. A sell settles on ONE chain, so the
    row is the sellable quantity — never a total summed across chains."""
    spot = assets.get("spot") or {}
    if not spot.get("available"):
        return None
    for row in spot.get("tokens") or []:
        addr = str(row.get("tokenAddress") or "").lower()
        same_chain = str(row.get("chainId") or "") == CHAIN_ID
        if addr and addr == TOKEN.lower() and same_chain:
            return row
    return None


def position(assets):
    perps = assets.get("perps") or {}
    if not perps.get("available"):
        return None
    for row in perps.get("positions") or []:
        if str(row.get("coin") or "").lower() == TOKEN.lower():
            return row
    return None


def spot_price(assets):
    """The live price: the holding's own if the owner holds it, else the
    token-search quote. None means unknown — the caller must not trade."""
    row = holding(assets)
    if row is not None and row.get("usdPrice") is not None:
        return _num(row.get("usdPrice"), 0.0) or None
    try:
        body = bevo.read("/token-search", {"q": TOKEN})
    except bevo.BevoError as exc:
        bevo.log(f"dca: /token-search unreadable ({exc})")
        return None
    for hit in (body or {}).get("tokens") or []:
        if str(hit.get("address") or "").lower() == TOKEN.lower():
            price = _num(hit.get("priceUsd"), 0.0)
            return price or None
    return None


def plan(assets, key):
    """(command, usd this run moves) for this action, or (None, reason)."""
    if ACTION == "buy":
        cash = assets.get("spotUsdcUsd")
        if cash is None:
            return None, "spot cash could not be read"
        if _num(cash, 0.0) - USD_PER_RUN < MIN_CASH_USD:
            return None, f"a ${fmt(USD_PER_RUN)} buy would leave under ${fmt(MIN_CASH_USD)} cash"
        if USD_PER_RUN < SPOT_MIN_USD:
            return None, f"${fmt(USD_PER_RUN)} is under the ${fmt(SPOT_MIN_USD)} spot minimum"
        if MAX_PRICE > 0:
            price = spot_price(assets)
            if price is None:
                return None, "price gate is set but the price could not be read"
            if price > MAX_PRICE:
                return None, f"price ${fmt(price)} is above the ${fmt(MAX_PRICE)} gate"
        return (
            f"acp trade --token-in usdc --amount-in {fmt(USD_PER_RUN)} "
            f"--token-out {TOKEN} --chain-out {CHAIN_ID} --idempotency-key {key}"
        ), USD_PER_RUN

    if ACTION == "sell":
        row = holding(assets)
        if row is None:
            return None, f"nothing held on chain {CHAIN_ID} to sell"
        price = spot_price(assets)
        if MIN_PRICE > 0:
            if price is None:
                return None, "price gate is set but the price could not be read"
            if price < MIN_PRICE:
                return None, f"price ${fmt(price)} is below the ${fmt(MIN_PRICE)} gate"
        qty = SELL_QTY_PER_RUN
        if qty <= 0:
            if not price:
                return None, "no price to size the sell from"
            qty = USD_PER_RUN / price
        held = _num(row.get("balance"), 0.0)
        qty = min(qty, held)
        if qty <= 0:
            return None, f"nothing left to sell on chain {CHAIN_ID}"
        return (
            f"acp trade --token-in {TOKEN} --chain-in {CHAIN_ID} "
            f"--amount-in {fmt(qty)} --token-out usdc --idempotency-key {key}"
        ), qty * (price or 0.0)

    if ACTION == "perp-open":
        if MAX_PRICE > 0 or MIN_PRICE > 0:
            return None, "a price gate on a perp open belongs in the duty's judgment, not a knob"
        if USD_PER_RUN < PERP_OPEN_MIN_USD:
            return None, f"${fmt(USD_PER_RUN)} is under the ${fmt(PERP_OPEN_MIN_USD)} perp minimum"
        return (
            f"acp trade --side {PERP_SIDE} --token {TOKEN} "
            f"--amount-usdc {fmt(USD_PER_RUN)} --leverage {fmt(LEVERAGE)} --idempotency-key {key}"
        ), USD_PER_RUN

    if ACTION == "perp-reduce":
        pos = position(assets)
        if pos is None:
            return None, f"no open position on {TOKEN} to reduce"
        mark = _num(pos.get("markPriceUsd"), 0.0)
        if MIN_PRICE > 0:
            if not mark:
                return None, "price gate is set but the mark price could not be read"
            if mark < MIN_PRICE:
                return None, f"mark ${fmt(mark)} is below the ${fmt(MIN_PRICE)} gate"
        value = _num(pos.get("positionValueUsd"), 0.0)
        size = min(USD_PER_RUN, value)
        if size <= 0:
            return None, f"the {TOKEN} position has no value left to reduce"
        # Reducing is the OPPOSITE side of the position that is actually open —
        # never DCA_PERP_SIDE, and never without --reduce-only, which is what
        # keeps this from opening a fresh position the other way.
        opposite = "short" if str(pos.get("side")) == "long" else "long"
        return (
            f"acp trade --side {opposite} --token {TOKEN} "
            f"--amount-usdc {fmt(size)} --reduce-only --idempotency-key {key}"
        ), size

    return None, f"unknown action {ACTION!r}"


def status_of(result):
    """TradeResult exposes .status; the rehearsal/replay stub hands back the
    raw dict — read whichever this is."""
    status = getattr(result, "status", None)
    if status is None and hasattr(result, "get"):
        status = result.get("status")
    return status


def main():
    state = State(STATE_PATH)
    notes = Notes(NOTES_PATH)

    for ev in bevo.events():
        if ev.get("kind") != "timer":
            continue

        slot = slot_for(ev.get("at"))
        if slot in state:
            continue

        if MAX_RUNS and state.runs >= MAX_RUNS:
            notes.once("max-runs", f"DCA on {label()}: {state.runs} of {MAX_RUNS} runs done — disable it when you're ready.")
            state.done(slot)
            continue
        if TOTAL_BUDGET_USD and state.moved_usd >= TOTAL_BUDGET_USD:
            notes.once("budget", f"DCA on {label()}: ${fmt(state.moved_usd)} moved, its limit — disable it when you're ready.")
            state.done(slot)
            continue

        assets = read_assets()
        if assets is None:
            continue  # unknown is not zero: leave the slot open for the next tick

        key = f"dca:{bevo.SERVICE_ID}:{ACTION}:{slot}"
        command, detail = plan(assets, key)
        if command is None:
            bevo.log(f"dca slot={slot} skipped: {detail}")
            notes.once(f"skip:{detail}", f"DCA on {label()} skipped a run: {detail}.")
            state.done(slot)
            continue

        if ESCALATE:
            # A condition the knobs cannot express: judgment decides and places
            # the trade itself. Escalating spends a wake, so only eligible runs
            # that already passed every numeric gate get here.
            bevo.escalate(f"DCA slot {slot}: {ACTION} {TOKEN} — {command}", [dict(ev)])
            state.done(slot, ran=True)
            continue

        result = bevo.trade(command=command, idempotency_key=key)
        status = status_of(result)
        bevo.log(f"dca slot={slot} action={ACTION} status={status} key={key}")

        if status == "manual_signing_required":
            notes.once(f"ask:{slot}", f"DCA on {label()}: this run needs your approval — it's in Approvals.")
        elif status not in ("accepted", "executed"):
            notes.once(f"refused:{status}", f"DCA on {label()} was refused ({status}) — the schedule keeps its next run.")

        ok = status in ("accepted", "executed", "manual_signing_required")
        # Every terminal status ends the slot: never loop on one tick.
        state.done(slot, ran=ok, moved_usd=float(detail) if ok else 0.0)


if __name__ == "__main__":
    main()
