import urllib.request,json,hashlib
from pathlib import Path
base='https://raw.githubusercontent.com/SkillCorner/opendata/master/'
out=Path(__file__).resolve().parents[1]/'frontend/public/tracking'
out.mkdir(parents=True,exist_ok=True)
meta=json.load(urllib.request.urlopen(base+'data/matches/2017461/2017461_match.json'))
frames=[]
url='https://media.githubusercontent.com/media/SkillCorner/opendata/master/data/matches/2017461/2017461_tracking_extrapolated.jsonl'
with urllib.request.urlopen(url) as response:
 for line in response:
  f=json.loads(line)
  if f['frame']<2510: continue
  if f['frame']>3710: break
  frames.append(f)
print('frames',len(frames),'first',json.dumps(frames[0])[:1800])
print('pitch',[(k,v) for k,v in meta.items() if 'pitch' in k])
(out/'source-match.json').write_text(json.dumps(meta),encoding='utf-8')
(out/'source-clip.json').write_text(json.dumps(frames),encoding='utf-8')
(out/'LICENSE.txt').write_bytes(urllib.request.urlopen(base+'LICENSE').read())

manifest={'provider':'SkillCorner','match_id':2017461,'retrieved':'2026-10-18','source':url,'metadata_source':base+'data/matches/2017461/2017461_match.json','start_frame':2510,'end_frame':3710,'fps':10,'period':1,'license':'MIT','limitations':['Historical excerpt, not live','Extrapolated positions are provider estimates','Missing source positions are hidden','Generic player models, kits and animations'],'sha256':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['source-match.json','source-clip.json','LICENSE.txt']}}
(out/'provenance.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
