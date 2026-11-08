
import os
import json
import time
import base64
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

BASE = "https://us.api.blizzard.com"
NAMESPACE = "profile-forever-us"

GUILDS = [
    {
        "id": "rp-horde",
        "name": "Division VII",
        "slug": "division-vii",
        "ruleset": "RP-PvP",
        "faction": "Horde",
        "realm": "pvp_rp",
    },
    {
        "id": "rp-alliance",
        "name": "DivisionVII Imperium",
        "slug": "divisionvii-imperium",
        "ruleset": "RP-PvP",
        "faction": "Alliance",
        "realm": "pvp_rp",
    },
    {
        "id": "pvp-horde",
        "name": "DivisionVII",
        "slug": "divisionvii",
        "ruleset": "PvP",
        "faction": "Horde",
        "realm": "pvp",
    },
]

OUTPUT = Path(__file__).resolve().parent / "data" / "leaderboard.json"


def authenticate():
    client_id = os.environ["BLIZZARD_CLIENT_ID"]
    client_secret = os.environ["BLIZZARD_CLIENT_SECRET"]

    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    req = Request(
        "https://oauth.battle.net/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": "Basic " + credentials,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urlopen(req, timeout=30) as response:
        return json.load(response)["access_token"]


def fetch_json(path, token):
    url = BASE + path
    separator = "&" if "?" in url else "?"
    url += separator + "namespace=" + NAMESPACE + "&locale=en_US"

    req = Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        },
    )

    with urlopen(req, timeout=30) as response:
        return json.load(response)


def display_name(value, fallback="Unknown"):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str):
            return name
        if isinstance(name, dict):
            return name.get("en_US", fallback)
    return fallback


def character_url(character, guild):
    slug = character.get("slug")
    if not slug:
        full_name = " ".join(
            filter(None, [
                character.get("name"),
                character.get("surname"),
            ])
        )
        slug = full_name.replace(" ", "-")

    return (
        "https://armorywowforever.com/c/forever/us/"
        + guild["realm"] + "/"
        + quote(str(slug), safe="-")
    )


def parse_roster(data, guild):
    members = data.get("members")
    if not isinstance(members, list):
        raise ValueError("API response has no members list")

    characters = []

    for member in members:
        c = member.get("character", {})
        if not isinstance(c, dict):
            continue

        name = c.get("name", "")
        surname = c.get("surname", "")
        full_name = " ".join(filter(None, [name, surname]))

        if not full_name:
            continue

        rank = member.get("rank", 0)
        if isinstance(rank, dict):
            rank = rank.get("id", rank.get("name", 0))

        try:
            rank_number = int(rank)
            rank_label = (
                "Guild Master" if rank_number == 0
                else f"Rank {rank_number}"
            )
        except (TypeError, ValueError):
            rank_label = str(rank)

        characters.append({
            "name": full_name,
            "level": int(c.get("level", 1)),
            "race": display_name(c.get("playable_race")),
            "class": display_name(c.get("playable_class")),
            "rank": rank_label,
            "url": character_url(c, guild),
            "guildId": guild["id"],
            "ruleset": guild["ruleset"],
            "faction": guild["faction"],
            "guild": guild["name"],
        })

    if not characters:
        raise ValueError("No characters parsed")

    return characters


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT.exists():
        try:
            previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
    else:
        previous = {}

    old_chars = previous.get("characters", [])
    history = previous.get("history", {})
    now = int(time.time())

    token = authenticate()
    print("Blizzard authentication successful")

    all_chars = []
    errors = []
    successful = 0

    for guild in GUILDS:
        try:
            path = (
                "/data/wow/guild/"
                + guild["slug"] + "/roster"
            )

            data = fetch_json(path, token)
            characters = parse_roster(data, guild)

            all_chars.extend(characters)
            successful += 1

            print(
                guild["id"],
                len(characters),
                "characters fetched"
            )

        except Exception as exc:
            message = f"{guild['id']}: {exc}"
            errors.append(message)
            print("ERROR:", message)

            # Preserve the previous roster on partial failure.
            all_chars.extend(
                c for c in old_chars
                if c.get("guildId") == guild["id"]
            )

    if successful == 0:
        raise RuntimeError(
            "All API requests failed. Existing roster preserved."
        )

    for c in all_chars:
        key = c["guildId"] + "|" + c["url"]
        observations = history.setdefault(key, [])

        # Record a new observation only when the level changes.
        if not observations or observations[-1][1] != c["level"]:
            observations.append([now, c["level"]])

        # Retain 35 days of history, plus the latest observation.
        history[key] = [
            o for o in observations
            if o[0] >= now - 35 * 86400
        ] or observations[-1:]

        for period, field in [
            (86400, "gain24h"),
            (604800, "gain7d"),
        ]:
            baseline = next(
                (
                    o[1] for o in reversed(history[key])
                    if o[0] <= now - period
                ),
                None,
            )
            c[field] = (
                c["level"] - baseline
                if baseline is not None
                else None
            )

    live_keys = {
        c["guildId"] + "|" + c["url"]
        for c in all_chars
    }

    history = {
        key: value
        for key, value in history.items()
        if key in live_keys
    }

    all_chars.sort(
        key=lambda c: (-c["level"], c["name"].lower())
    )

    result = {
        "updated": now,
        "characters": all_chars,
        "errors": errors,
        "history": history,
    }

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )

    print("Saved", len(all_chars), "characters")
    print("Successful guilds:", successful)
    print("Errors:", len(errors))


if __name__ == "__main__":
    main()
