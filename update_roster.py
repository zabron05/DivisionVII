
"""Division VII WoW Forever Armory roster updater (Python 3.12, stdlib only)."""
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

BASE = 'https://armorywowforever.com'
GUILDS = [
    {'id': 'rp-horde', 'name': 'Division VII', 'ruleset': 'RP-PvP', 'faction': 'Horde', 'url': BASE + '/g/forever/us/pvp_rp/division-vii'},
    {'id': 'rp-alliance', 'name': 'DivisionVII Imperium', 'ruleset': 'RP-PvP', 'faction': 'Alliance', 'url': BASE + '/g/forever/us/pvp_rp/divisionvii-imperium'},
    {'id': 'pvp-horde', 'name': 'DivisionVII', 'ruleset': 'PvP', 'faction': 'Horde', 'url': BASE + '/g/forever/us/pvp/divisionvii'},
]
RACES = ['Windshaper Skyborne', 'High Order Skyborne', 'Night Elf', 'Blood Elf', 'Undead', 'Tauren', 'Troll', 'Orc', 'Human', 'Gnome', 'Dwarf', 'Draenei']
CLASSES = ['Death Knight', 'Demon Hunter', 'Paladin', 'Warlock', 'Warrior', 'Hunter', 'Shaman', 'Priest', 'Rogue', 'Druid', 'Mage', 'Monk']
PATTERN = re.compile(r'\b(\d{1,3})\s+(' + '|'.join(map(re.escape, sorted(RACES, key=len, reverse=True))) + r')\s+(' + '|'.join(map(re.escape, sorted(CLASSES, key=len, reverse=True))) + r')\s+(Guild Master|Rank\s+\d+)', re.I)

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and self.current is None:
            self.current = {'href': dict(attrs).get('href'), 'text': []}
            self.depth = 1
        elif tag == 'a' and self.current is not None:
            self.depth += 1

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.links.append((' '.join(' '.join(self.current['text']).split()), self.current['href']))
                self.current = None

def parse(page, guild):
    parser = LinkParser()
    parser.feed(page)
    rows, seen = [], set()
    for label, href in parser.links:
        if not href or not re.search(r'/c/|/character/', href):
            continue
        match = PATTERN.search(label)
        if not match:
            continue
        name = label[:match.start()].strip()
        level = int(match.group(1))
        if not name or not 1 <= level <= 100:
            continue
        url = urljoin(BASE, href)
        if urlparse(url).hostname != urlparse(BASE).hostname or url in seen:
            continue
        seen.add(url)
        rows.append({'name': name, 'level': level, 'race': match.group(2), 'class': match.group(3),
                     'rank': match.group(4), 'url': url, 'guildId': guild['id'],
                     'ruleset': guild['ruleset'], 'faction': guild['faction'], 'guild': guild['name']})
    return rows

def fetch(guild, stamp):
    # Unique query string discourages intermediate CDN caching; it cannot guarantee freshness.
    url = guild['url'] + '?' + urlencode({'divisionvii_refresh': stamp})
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36',
        'Cache-Control': 'no-cache, no-store, max-age=0',
        'Pragma': 'no-cache',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urlopen(req, timeout=30) as response:
        page = response.read().decode('utf-8', 'replace')
        print(f"{guild['id']}: HTTP {response.status}, bytes={len(page)}, cache={response.headers.get('X-Cache', 'unknown')}, age={response.headers.get('Age', 'unknown')}", flush=True)
    return page

def baseline_at_or_before(observations, cutoff):
    older = [level for timestamp, level in observations if timestamp <= cutoff]
    return older[-1] if older else None

def main():
    output = Path(__file__).resolve().parent / 'data' / 'leaderboard.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    prior_chars = previous.get('characters', [])
    old_by_guild = {g['id']: [c for c in prior_chars if c.get('guildId') == g['id']] for g in GUILDS}
    old_by_key = {(c.get('guildId'), c.get('url')): c for c in prior_chars}
    now = int(time.time())
    all_chars, errors, statuses = [], [], []
    successful = 0
    for guild in GUILDS:
        try:
            page = fetch(guild, now)
            rows = parse(page, guild)
            if not rows:
                raise ValueError('No roster rows parsed (site layout, access, or source response may have changed)')
            # Detect suspicious partial results rather than replacing a roster with only a few entries.
            prior_count = len(old_by_guild[guild['id']])
            if prior_count >= 10 and len(rows) < prior_count * 0.5:
                raise ValueError(f'Suspicious roster shrink: {prior_count} -> {len(rows)}; keeping prior roster')
            changes = [(c['name'], old_by_key[(guild['id'], c['url'])]['level'], c['level'])
                       for c in rows if (guild['id'], c['url']) in old_by_key
                       and old_by_key[(guild['id'], c['url'])]['level'] != c['level']]
            additions = [c['name'] for c in rows if (guild['id'], c['url']) not in old_by_key]
            print(f"{guild['id']}: {len(rows)} characters; {len(changes)} level changes; {len(additions)} new characters", flush=True)
            for name, before, after in changes[:20]:
                print(f'  LEVEL: {name}: {before} -> {after}', flush=True)
            for name in additions[:20]:
                print(f'  NEW: {name}', flush=True)
            all_chars.extend(rows)
            statuses.append({'guildId': guild['id'], 'ok': True, 'count': len(rows), 'levelChanges': len(changes), 'newCharacters': len(additions)})
            successful += 1
        except Exception as exc:
            message = f"{guild['id']}: {type(exc).__name__}: {exc}"
            errors.append(message)
            statuses.append({'guildId': guild['id'], 'ok': False, 'count': len(old_by_guild[guild['id']])})
            all_chars.extend(old_by_guild[guild['id']])
            print('ERROR: ' + message, file=sys.stderr, flush=True)
    if successful == 0:
        raise RuntimeError('All three Armory fetches failed; refusing to overwrite the existing data')

    history = previous.get('history', {})
    for c in all_chars:
        key = c['guildId'] + '|' + c['url']
        observations = history.get(key, [])
        # Only record a new observation for a successfully refreshed guild.
        status = next(s for s in statuses if s['guildId'] == c['guildId'])
        if status['ok'] and (not observations or observations[-1][1] != c['level'] or now - observations[-1][0] >= 3600):
            observations.append([now, c['level']])
        observations = sorted(observations, key=lambda x: x[0])
        observations = [o for o in observations if o[0] >= now - 36 * 86400] or observations[-1:]
        history[key] = observations
        for period, field in ((86400, 'gain24h'), (604800, 'gain7d')):
            baseline = baseline_at_or_before(observations, now - period)
            c[field] = c['level'] - baseline if baseline is not None else None
    livekeys = {c['guildId'] + '|' + c['url'] for c in all_chars}
    history = {k: v for k, v in history.items() if k in livekeys}
    data = {'updated': now, 'characters': all_chars, 'errors': errors, 'history': history, 'guildStatus': statuses}
    temp = output.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(output)
    print(f'Saved {len(all_chars)} characters; {successful}/3 guilds refreshed; {len(errors)} errors', flush=True)
    if errors:
        print('WARNING: Some guilds retained their previous roster due to fetch errors.', file=sys.stderr)

if __name__ == '__main__':
    main()
