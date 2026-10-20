"""Set Kyle's Yahoo fantasy basketball lineup for today plus the next 4 days.

The start/sit logic is RULES.md, in priority order:
  1. Fill the most active slots with players who have a game.
  2. Out / Injured / Not Active never start; move them to IL if a slot is free.
  3. Score = weighted average of each player's place on the roster (1 = best)
     for two factors; lower is better.
  4. Questionable: score x2.  5. Doubtful: only to avoid an empty slot.
  6. Ties go to the higher % Rostered.

Runs in GitHub Actions. Any problem exits non-zero, so GitHub emails Kyle.
Set DRY_RUN=1 to plan without saving.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LEAGUE_ID = "96295"
TEAM_ID = "1"
DAYS = int(os.environ.get("DAYS") or 5)
DRY_RUN = os.environ.get("DRY_RUN") == "1"
REDIRECT_URI = "oob"  # must match setup_auth.py

# Through Nov 9: 75% % Rostered + 25% pre-season rank (no season stats yet).
# From Nov 10: 75% recent rank + 25% season rank.
RECENT_PHASE_STARTS = date(2026, 11, 10)

NEVER_START = {"O", "INJ", "NA", "SUSP", "OUT", "IL"}
QUESTIONABLE = {"Q", "GTD", "DTD"}
DOUBTFUL = {"D", "DOUBT", "DOUBTFUL"}
HEALTHY = {"", "P", "PROB"}
DOUBTFUL_WEIGHT = 1e6  # only picked when it is the only way to fill a slot

API = "https://fantasysports.yahooapis.com/fantasy/v2"
NS = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
EASTERN = ZoneInfo("America/New_York")

TOKEN = None
problems = []      # anything that should make the run fail (and email Kyle)
report = []        # lines for the run summary


def say(line=""):
    print(line)
    report.append(line)


# ---------------------------------------------------------------- Yahoo API

def access_token():
    cid = os.environ["YAHOO_CLIENT_ID"]
    secret = os.environ["YAHOO_CLIENT_SECRET"]
    refresh = os.environ["YAHOO_REFRESH_TOKEN"]
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://api.login.yahoo.com/oauth2/get_token", body,
        {"Authorization": f"Basic {basic}",
         "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["access_token"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Yahoo sign-in failed ({e.code}): {e.read()[:300]!r}. "
                         "The refresh token may have been revoked; rerun setup_auth.py.")


def call(method, path, body=None):
    for attempt in range(4):
        req = urllib.request.Request(
            API + path, body, method=method,
            headers={"Authorization": f"Bearer {TOKEN}",
                     **({"Content-Type": "application/xml"} if body else {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return ET.fromstring(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {path} -> {e.code}: {e.read()[:500]!r}")


def text(el, path, default=""):
    found = el.find(path, NS)
    return found.text if found is not None and found.text is not None else default


# ------------------------------------------------------------ data gathering

def roster_settings(league_key):
    root = call("GET", f"/league/{league_key}/settings")
    caps = {}
    for rp in root.iterfind(".//y:roster_positions/y:roster_position", NS):
        caps[text(rp, "y:position")] = int(text(rp, "y:count", "0"))
    return caps


def read_roster(team_key, day):
    root = call("GET", f"/team/{team_key}/roster;date={day.isoformat()}")
    players = []
    for p in root.iterfind(".//y:roster/y:players/y:player", NS):
        players.append({
            "key": text(p, "y:player_key"),
            "name": text(p, "y:name/y:full"),
            "team": text(p, "y:editorial_team_full_name"),
            "eligible": [e.text for e in p.iterfind("y:eligible_positions/y:position", NS)],
            "slot": text(p, "y:selected_position/y:position"),
            "status": text(p, "y:status").upper(),
            # Yahoo marks a player not editable once his game has started.
            "editable": text(p, "y:is_editable", "1") != "0",
        })
    if not players:
        raise RuntimeError(f"Yahoo returned an empty roster for {day}")
    return players


def percent_owned(league_key, keys):
    out = {}
    for i in range(0, len(keys), 25):
        chunk = ",".join(keys[i:i + 25])
        root = call("GET", f"/league/{league_key}/players;player_keys={chunk}/percent_owned")
        for p in root.iterfind(".//y:player", NS):
            out[text(p, "y:player_key")] = float(text(p, "y:percent_owned/y:value", "0") or 0)
    return {k: out.get(k, 0.0) for k in keys}


def rank_order(league_key, keys, sort):
    """Kyle's players in Yahoo's order for `sort` (e.g. 'sort=OR' or
    'sort=AR;sort_type=lastmonth'). Players Yahoo never lists go last."""
    wanted, order = set(keys), []
    for start in range(0, 1500, 25):
        root = call("GET", f"/league/{league_key}/players;status=T;{sort};start={start};count=25")
        page = [text(p, "y:player_key") for p in root.iterfind(".//y:player", NS)]
        order += [k for k in page if k in wanted]
        if not page or len(order) == len(wanted):
            break
    return order + [k for k in keys if k not in order]


def places_from_order(order):
    return {k: i + 1 for i, k in enumerate(order)}


def places_from_values(values):
    """Higher value = better place; ties share the average place."""
    ranked = sorted(values.values(), reverse=True)
    out = {}
    for k, v in values.items():
        idx = [i + 1 for i, x in enumerate(ranked) if x == v]
        out[k] = sum(idx) / len(idx)
    return out


def nickname(full):
    """'Los Angeles Clippers' and 'LA Clippers' both -> 'clippers'."""
    return full.split()[-1].lower() if full else ""


def games_on(day):
    """Team nicknames with a game that day, and which have already started."""
    url = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
           f"?dates={day.strftime('%Y%m%d')}&limit=100")
    with urllib.request.urlopen(url, timeout=30) as r:
        events = json.load(r).get("events", [])
    playing, started = set(), set()
    for ev in events:
        state = ev.get("status", {}).get("type", {}).get("state", "pre")
        for c in ev["competitions"][0]["competitors"]:
            nick = nickname(c["team"]["displayName"])
            playing.add(nick)
            if state != "pre":
                started.add(nick)
    return playing, started


# ------------------------------------------------------------------- scoring

def build_scores(league_key, keys, today):
    owned = percent_owned(league_key, keys)
    owned_place = places_from_values(owned)
    if today < RECENT_PHASE_STARTS:
        season = places_from_order(rank_order(league_key, keys, "sort=OR"))
        score = {k: 0.75 * owned_place[k] + 0.25 * season[k] for k in keys}
        basis = "75% % Rostered + 25% pre-season rank"
    else:
        # Yahoo has no last-14-days rank; average last week and last month.
        week = places_from_order(rank_order(league_key, keys, "sort=AR;sort_type=lastweek"))
        month = places_from_order(rank_order(league_key, keys, "sort=AR;sort_type=lastmonth"))
        season = places_from_order(rank_order(league_key, keys, "sort=AR;sort_type=season"))
        score = {k: 0.75 * (week[k] + month[k]) / 2 + 0.25 * season[k] for k in keys}
        basis = "75% recent rank (avg of last week + last month) + 25% season rank"
    return score, owned, basis


# ------------------------------------------------------------------ planning

def can_fill(slot, player):
    return slot == "Util" or slot in player["eligible"]


def assign(players, open_slots):
    """Match players to slot instances. Returns {slot_index: player} or None.
    Tries each player's current slot first so unchanged players stay put."""
    slot_of = {}

    def augment(p, seen):
        order = sorted(range(len(open_slots)),
                       key=lambda j: open_slots[j] != p["slot"])
        for j in order:
            if can_fill(open_slots[j], p) and j not in seen:
                seen.add(j)
                if j not in slot_of or augment(slot_of[j], seen):
                    slot_of[j] = p
                    return True
        return False

    for p in players:
        if not augment(p, set()):
            return None
    return slot_of


def plan_day(players, caps, playing, started, score, owned):
    active_caps = {s: caps.get(s, 0) for s in ("G", "F", "C", "Util")}
    il_cap = caps.get("IL", 0) + caps.get("IL+", 0)
    target, notes = {}, []

    for p in players:
        p["has_game"] = nickname(p["team"]) in playing
        p["locked"] = not p["editable"] or nickname(p["team"]) in started

    # Locked players stay exactly where they are.
    open_slots = []
    for s, n in active_caps.items():
        taken = sum(1 for p in players if p["locked"] and p["slot"] == s)
        open_slots += [s] * max(0, n - taken)
    for p in players:
        if p["locked"]:
            target[p["key"]] = p["slot"]
    free = [p for p in players if not p["locked"]]

    # IL: healthy players come off; never-start players go on if there is room.
    il_used = sum(1 for p in players if p["locked"] and p["slot"] in ("IL", "IL+"))
    for p in free:
        on_il = p["slot"] in ("IL", "IL+")
        il_ok = any(e in ("IL", "IL+") for e in p["eligible"])
        if on_il and il_ok:
            target[p["key"]] = p["slot"]
            il_used += 1
    for p in free:
        on_il = p["slot"] in ("IL", "IL+")
        il_ok = any(e in ("IL", "IL+") for e in p["eligible"])
        if on_il and not il_ok:
            notes.append(f"{p['name']} is on IL but no longer IL-eligible; moving to bench")
        if not on_il and il_ok and p["status"] in NEVER_START and il_used < il_cap:
            target[p["key"]] = "IL" if "IL" in p["eligible"] else "IL+"
            il_used += 1

    # Candidates for the active slots.
    weight = {}
    for p in free:
        if p["key"] in target or not p["has_game"] or p["status"] in NEVER_START:
            continue
        w = score[p["key"]]
        if p["status"] in QUESTIONABLE:
            w *= 2
        elif p["status"] in DOUBTFUL:
            w += DOUBTFUL_WEIGHT
        elif p["status"] not in HEALTHY:
            notes.append(f"unknown injury status '{p['status']}' for {p['name']}; treated as healthy")
        weight[p["key"]] = w
    candidates = sorted((p for p in free if p["key"] in weight),
                        key=lambda p: (weight[p["key"]], -owned.get(p["key"], 0)))

    # Greedy over a transversal matroid: take each player, best first, if a
    # slot matching still exists. Gives the most filled slots, then the best
    # total score.
    chosen = []
    for p in candidates:
        if assign(chosen + [p], open_slots) is not None:
            chosen.append(p)
    for j, p in assign(chosen, open_slots).items():
        target[p["key"]] = open_slots[j]
    for p in free:
        target.setdefault(p["key"], "BN")

    bench_cap = caps.get("BN", 0)
    if sum(1 for v in target.values() if v == "BN") > bench_cap:
        problems.append("Not enough bench spots for the planned moves "
                        "(probably a healthy player stuck on IL) - needs a roster move.")

    empty = len(open_slots) - len(chosen)
    return target, empty, notes


def put_lineup(team_key, day, players, target):
    moves = [p for p in players if not p["locked"] and target[p["key"]] != p["slot"]]
    if not moves:
        return moves
    rows = "".join(
        f"<player><player_key>{p['key']}</player_key><position>{target[p['key']]}</position></player>"
        for p in players if not p["locked"])
    body = ('<?xml version="1.0"?><fantasy_content><roster>'
            f"<coverage_type>date</coverage_type><date>{day.isoformat()}</date>"
            f"<players>{rows}</players></roster></fantasy_content>").encode()
    call("PUT", f"/team/{team_key}/roster", body)
    return moves


# ---------------------------------------------------------------------- main

def main():
    global TOKEN
    TOKEN = access_token()
    game_key = text(call("GET", "/game/nba"), ".//y:game_key")
    league_key = f"{game_key}.l.{LEAGUE_ID}"
    team_key = f"{league_key}.t.{TEAM_ID}"
    caps = roster_settings(league_key)

    today = datetime.now(EASTERN).date()
    first = read_roster(team_key, today)
    keys = [p["key"] for p in first]
    score, owned, basis = build_scores(league_key, keys, today)

    say(f"## Lineup run {datetime.now(EASTERN):%a %b %d, %I:%M %p} ET"
        + (" (DRY RUN - nothing saved)" if DRY_RUN else ""))
    say(f"Scoring: {basis}")

    for offset in range(DAYS):
        day = today + timedelta(days=offset)
        try:
            players = first if offset == 0 else read_roster(team_key, day)
            for p in players:
                if p["key"] not in score:  # e.g. added mid-run; score him last
                    score[p["key"]] = len(score) + 1
            playing, started = games_on(day)
            target, empty, notes = plan_day(players, caps, playing, started, score, owned)
            moves = [p for p in players if not p["locked"] and target[p["key"]] != p["slot"]]
            say(f"\n### {day:%a %b %d}")
            for m in moves:
                say(f"- {m['name']}: {m['slot']} -> {target[m['key']]}")
            if not moves:
                say("- no changes")
            if empty:
                say(f"- {empty} active slot(s) empty (not enough players with games)")
            for n in notes:
                say(f"- note: {n}")
            if moves and not DRY_RUN:
                put_lineup(team_key, day, players, target)
                after = {p["key"]: p["slot"] for p in read_roster(team_key, day)}
                wrong = [m["name"] for m in moves if after.get(m["key"]) != target[m["key"]]]
                if wrong:
                    problems.append(f"{day}: Yahoo did not keep the move for {', '.join(wrong)}")
        except Exception as e:  # keep going with the other days, but fail the run
            problems.append(f"{day}: {e}")

    if problems:
        say("\n### Problems")
        for p in problems:
            say(f"- {p}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
