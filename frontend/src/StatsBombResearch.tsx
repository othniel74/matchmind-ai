import { useEffect, useState } from 'react';

type Event = {id:string;index:number;period:number;minute:number;second:number;type:string;team:string;player:string;recipient:string;outcome:string;xg:number|null;start:number[]|null;end:number[]|null};
type Team = {name:string;passes:number;completed:number;shots:number;goals:number;xg:number;shootout_goals:number};
type Node = {id:number;name:string;team:string;x:number;y:number;involvement:number};
type Edge = {from:number;to:number;weight:number;evidence:string[];from_name:string;to_name:string;team:string};
type Analysis = {total_events:number;events_processed:number;teams:Team[];events:Event[];nodes:Node[];edges:Edge[];clock:{period:number;minute:number;second:number}|null;engine:string};

export default function StatsBombResearch({standalone=false}:{standalone?:boolean}) {
  const [data,setData]=useState<Analysis|null>(null);
  const [limit,setLimit]=useState(4407),[pending,setPending]=useState(true);
  const [error,setError]=useState(''),[team,setTeam]=useState('Argentina');
  const [selected,setSelected]=useState(''),[view,setView]=useState('shots');
  useEffect(()=>{
    const controller=new AbortController();setPending(true);setError('');
    const timer=setTimeout(()=>{fetch(`/api/research/statsbomb?event_limit=${limit}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(d=>{setData(d);setPending(false)}).catch(()=>{if(!controller.signal.aborted){setError('Local StatsBomb research data is unavailable. Check the backend and dataset import.');setPending(false)}})},180);
    return ()=>{clearTimeout(timer);controller.abort()};
  },[limit]);
  const evidence=data?.events.find(e=>e.id===selected);
  const shots=data?.events.filter(e=>e.type==='Shot')??[];
  const nodes=data?.nodes.filter(n=>n.team===team)??[];
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const edges=data?.edges.filter(e=>e.team===team&&byId.has(e.from)&&byId.has(e.to))??[];
  const clock=data?.clock;
  const stamp=(e:Event)=>`${e.minute}:${String(e.second).padStart(2,'0')}`;
  return <section className={`tracking-replay statsbomb-research ${standalone?'tracking-standalone':''}`} aria-label="StatsBomb real event research">
    <div className="tracking-heading"><span className="eyebrow">STATSBOMB OPEN DATA / LOCAL RESEARCH</span><h3>Argentina v France</h3><p>18 December 2022 / World Cup final / Event data, not continuous tracking</p></div>
    {standalone&&<a href="/app?view=studio">Return to Studio</a>}
    <div className="research-attribution"><img src="/api/research/statsbomb/logo" alt="StatsBomb"/><span>Data provided by StatsBomb. Independent noncommercial research demo.</span></div>
    {error&&<p role="alert">{error}</p>}
    <label className="research-progress">Source event cutoff: {limit.toLocaleString()} / {data?.total_events??4407}<input aria-label="StatsBomb event cutoff" type="range" min="0" max={data?.total_events??4407} step="1" value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label>
    <p className="subtle-note" role="status">{pending?'Updating source analysis...':clock?`Through source period ${clock.period}, ${clock.minute}:${String(clock.second).padStart(2,'0')}.`:'No events selected.'} Match clocks can overlap during stoppage time; the cutoff follows source event order.</p>
    {data&&<>
      <div className="research-score">{data.teams.map(t=><div key={t.name}><span>{t.name}</span><b>{t.goals}</b><small>{t.completed}/{t.passes} completed passes / {t.shots} shots / {t.xg.toFixed(2)} xG</small></div>)}</div>
      <p className="subtle-note">Goals and xG above exclude the shootout. Shootout goals at this cutoff: {data.teams.map(t=>`${t.name} ${t.shootout_goals}`).join(' / ')}.</p>
      <div className="tracking-source"><label>Analysis view <select aria-label="StatsBomb analysis view" value={view} onChange={e=>{setView(e.target.value);setSelected('')}}><option value="shots">Shot map and evidence</option><option value="network">Passing network</option></select></label><label>Team <select aria-label="StatsBomb team" value={team} onChange={e=>{setTeam(e.target.value);setSelected('')}}><option>Argentina</option><option>France</option></select></label></div>
      <div className="research-pitch"><svg viewBox="0 0 120 80" role="img" aria-label={view==='shots'?'Real match shot locations':'Directed weighted passing network'}>
        <rect x="1" y="1" width="118" height="78"/><path d="M60 1V79 M1 20H19V60H1 M119 20H101V60H119"/><circle className="field-center" cx="60" cy="40" r="10"/>
        {view==='network'?<>{edges.map(e=>{const a=byId.get(e.from)!,b=byId.get(e.to)!;return <line key={`${e.from}-${e.to}`} className="research-edge" x1={a.x*1.2} y1={a.y*.8} x2={b.x*1.2} y2={b.y*.8} style={{strokeWidth:Math.min(1.5,.1+e.weight*.045)}}><title>{e.from_name} to {e.to_name}: {e.weight} completed passes</title></line>})}{nodes.map(n=><g key={n.id}><circle className="research-node" cx={n.x*1.2} cy={n.y*.8} r={Math.min(2.1,.7+Math.sqrt(n.involvement)*.08)}><title>{n.name}: {n.involvement} incoming + outgoing passes</title></circle><text x={n.x*1.2} y={n.y*.8-2.6}>{n.name.split(' ').slice(-1)[0]}</text></g>)}</>:shots.filter(e=>e.team===team&&e.start).map(e=><circle key={e.id} className={`research-shot ${e.outcome==='Goal'?'goal':''} ${selected===e.id?'selected':''}`} cx={e.start![0]*1.2} cy={e.start![1]*.8} r={1+Math.sqrt(e.xg??0)*2} onClick={()=>setSelected(e.id)}><title>{stamp(e)} {e.player}: {e.outcome}, xG {e.xg?.toFixed(3)}</title></circle>)}
        {evidence?.start&&evidence.end&&<line className="research-evidence-path" x1={evidence.start[0]*1.2} y1={evidence.start[1]*.8} x2={evidence.end[0]*1.2} y2={evidence.end[1]*.8}/>}
      </svg></div>
      <p className="subtle-note">{view==='network'?`${data.engine}. Nodes use mean source event locations; lines represent completed passes with explicit recipients. Positions are not tracking or a formation. Select a connection below for evidence.`:'Shots use StatsBomb’s attacking coordinate frame. Circle size reflects source xG; lime marks goals. Select a shot below for evidence.'}</p>
      {evidence&&<div className="research-evidence" role="status"><b>{stamp(evidence)} / period {evidence.period} / {evidence.team}</b><p>{evidence.player} / {evidence.type}{evidence.recipient?` to ${evidence.recipient}`:''} / {evidence.outcome}{evidence.xg!==null?` / xG ${evidence.xg.toFixed(3)}`:''}</p><small>Source event {evidence.id} / index {evidence.index}</small></div>}
      <div className="research-event-list">{view==='network'?edges.slice(0,12).map(e=><button key={`${e.from}-${e.to}`} onClick={()=>setSelected(e.evidence[0])}><b>{e.weight} completed passes</b> {e.from_name} to {e.to_name}<small>{e.evidence.length} source event IDs; select to inspect the first</small></button>):shots.filter(e=>e.team===team).map(e=><button key={e.id} className={selected===e.id?'selected':''} onClick={()=>setSelected(e.id)}><b>{stamp(e)}</b> {e.player} / {e.outcome} / xG {e.xg?.toFixed(3)}<small>Evidence {e.id}</small></button>)}</div>
    </>}
    <p className="subtle-note">Local research only. StatsBomb’s terms restrict commercial exploitation and redistribution of raw data. This match is separate from the SkillCorner, Metrica and synthetic scenarios; no footage or continuous player movement is available here.</p>
    <a href="https://github.com/statsbomb/open-data" target="_blank" rel="noreferrer">StatsBomb Open Data source</a> / <a href="/api/research/statsbomb/terms" target="_blank" rel="noreferrer">Source usage agreement</a>
  </section>;
}
