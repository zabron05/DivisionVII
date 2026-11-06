from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from urllib.parse import urljoin
import json, re, time, threading

BASE='https://armorywowforever.com'
GUILDS=[{'id':'rp-horde','name':'Division VII','ruleset':'RP-PvP','faction':'Horde','url':BASE+'/g/forever/us/pvp_rp/division-vii'}, {'id':'rp-alliance','name':'DivisionVII Imperium','ruleset':'RP-PvP','faction':'Alliance','url':BASE+'/g/forever/us/pvp_rp/divisionvii-imperium'}, {'id':'pvp-horde','name':'DivisionVII','ruleset':'PvP','faction':'Horde','url':BASE+'/g/forever/us/pvp/divisionvii'}]
RACES=['Windshaper Skyborne','High Order Skyborne','Night Elf','Blood Elf','Undead','Tauren','Troll','Orc','Human','Gnome','Dwarf','Draenei']
CLASSES=['Death Knight','Demon Hunter','Paladin','Warlock','Warrior','Hunter','Shaman','Priest','Rogue','Druid','Mage','Monk']
class Parser(HTMLParser):
 def __init__(self): super().__init__();self.links=[];self.href=None;self.buf=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':self.href=dict(attrs).get('href');self.buf=[]
 def handle_data(self,data):
  if self.href is not None:self.buf.append(data)
 def handle_endtag(self,tag):
  if tag=='a' and self.href is not None:self.links.append((' '.join(' '.join(self.buf).split()),self.href));self.href=None;self.buf=[]
def parse(text,g):
 p=Parser();p.feed(text);rows=[];seen=set()
 for label,href in p.links:
  if not href or not re.search(r'/c/|/character/',href):continue
  # Character link text contains name, level, race, class, guild rank, optional gear score.
  match=re.search(r'\b(\d{1,3})\s+('+ '|'.join(map(re.escape,sorted(RACES,key=len,reverse=True))) +r')\s+('+ '|'.join(map(re.escape,CLASSES))+r')\s+(Guild Master|Rank\s+\d+)',label,re.I)
  if not match:continue
  name=label[:match.start()].strip();level=int(match.group(1))
  if not name or level>100:continue
  url=urljoin(BASE,href)
  if url in seen:continue
  seen.add(url)
  rows.append({'name':name,'level':level,'race':match.group(2),'class':match.group(3),'rank':match.group(4),'url':url,'guildId':g['id'],'ruleset':g['ruleset'],'faction':g['faction'],'guild':g['name']})
 return rows

from pathlib import Path
from datetime import datetime, timezone
import sys

def main():
    output=Path(__file__).resolve().parent/'data'/'leaderboard.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        previous=json.loads(output.read_text()) if output.exists() else {}
    except (ValueError,OSError):
        previous={}
    old={c['guildId']:[] for c in previous.get('characters',[])}
    for c in previous.get('characters',[]):old.setdefault(c['guildId'],[]).append(c)
    all_chars=[];errors=[];successful=0
    for g in GUILDS:
        try:
            req=Request(g['url'],headers={'User-Agent':'Mozilla/5.0 (compatible; DivisionVIILeaderboard/1.0)'})
            with urlopen(req,timeout=25) as response: page=response.read().decode('utf-8','replace')
            rows=parse(page,g)
            if not rows: raise ValueError('No character rows parsed; page markup may have changed')
            all_chars.extend(rows);successful+=1
            print(g['id'],len(rows),'characters')
        except Exception as exc:
            errors.append(f"{g['id']}: {exc}")
            all_chars.extend(old.get(g['id'],[]))
            print(errors[-1],file=sys.stderr)
    if not successful and not previous.get('characters'):
        raise RuntimeError('No guild rosters could be fetched; refusing to publish empty data')
    now=int(time.time())
    # Keep bounded, compact level observations per character for progress tracking.
    history=previous.get('history',{})
    for c in all_chars:
        key=c['guildId']+'|'+c['url']
        observations=history.setdefault(key,[])
        if not observations or observations[-1][1]!=c['level']:
            observations.append([now,c['level']])
        history[key]=[o for o in observations if o[0]>=now-60*60*24*35] or observations[-1:]
        for period,field in ((86400,'gain24h'),(604800,'gain7d')):
            baseline=next((o[1] for o in reversed(history[key]) if o[0]<=now-period),None)
            c[field]=c['level']-baseline if baseline is not None else None
    livekeys={c['guildId']+'|'+c['url'] for c in all_chars}
    history={k:v for k,v in history.items() if k in livekeys}
    data={'updated':now,'characters':all_chars,'errors':errors,'history':history}
    output.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    print('Saved',len(all_chars),'characters')
if __name__=='__main__': main()
