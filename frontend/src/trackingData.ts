export type RawFrame = {frame:number; timestamp:string; period:number; ball_data:{x:number|null;y:number|null;z:number|null;is_detected:boolean|null}; possession:{player_id:number|null}; player_data:{player_id:number;x:number;y:number;is_detected:boolean}[]};
export function metricaSummary(events:{team:string;time:number;type:string;subtype:string;end_frame:number}[],time:number) {
 return ['Home','Away'].map(team=>{const visible=events.filter(e=>e.team===team&&e.time<=time);return {team,passes:visible.filter(e=>e.type==='PASS').length,shots:visible.filter(e=>e.type==='SHOT').length,goals:visible.filter(e=>e.type==='SHOT'&&e.subtype.split('-').includes('GOAL')&&(e.end_frame-1)/25<=time).length}});
}
export type Match = {id:number;fps?:number;pitch_length:number;pitch_width:number;home_team:{id:number;short_name:string};away_team:{id:number;short_name:string};players:{id:number;team_id:number;number:number;short_name:string;player_role:{acronym:string}}[]};
export function sampleTracking(frames:RawFrame[],match:Match,time:number) {
 const fps=match.fps??10;
 time=Math.max(0,Math.min((frames.length-1)/fps,time));
 const index=Math.max(0,Math.min(frames.length-1,Math.floor(time*fps)));
 const a=frames[index], b=frames[Math.min(index+1,frames.length-1)];
 const mix=Math.max(0,Math.min(1,time*fps-index));
 const lerp=(x:number,y:number)=>x+(y-x)*mix;
 const next=new Map(b.player_data.map(p=>[p.player_id,p]));
 const roster=new Map(match.players.map(p=>[p.id,p]));
 const players=a.player_data.flatMap(p=>{
  const meta=roster.get(p.player_id); if(!meta)return [];
  const q=next.get(p.player_id)??p;
  const vx=(q.x-p.x)*fps,vy=(q.y-p.y)*fps;
  const x=lerp(p.x,q.x), y=lerp(p.y,q.y);
  const bx=a.ball_data.x??0,by=a.ball_data.y??0;
  return [{player_id:String(p.player_id),team_id:meta.team_id===match.home_team.id?'home':'away',number:meta.number,name:meta.short_name,
   goalkeeper:meta.player_role.acronym==='GK',x:50+x/match.pitch_length*100,y:50+y/match.pitch_width*100,
   vx,vy,heading:Math.hypot(vx,vy)>.2?Math.atan2(vx,vy):Math.atan2(bx-x,by-y),
   active:a.possession.player_id===p.player_id,detected:p.is_detected&&q.is_detected}];
 });
 const valid=(v:number|null):v is number=>v!==null&&Number.isFinite(v);
 const visible=valid(a.ball_data.x)&&valid(a.ball_data.y)&&valid(b.ball_data.x)&&valid(b.ball_data.y);
 return {players,ball:{x:50+lerp(a.ball_data.x??0,b.ball_data.x??0)/match.pitch_length*100,y:50+lerp(a.ball_data.y??0,b.ball_data.y??0)/match.pitch_width*100},ballHeight:Math.max(0,lerp(a.ball_data.z??0,b.ball_data.z??0)),ballVisible:visible,tracking:true,minute:time,ballDetected:a.ball_data.is_detected===true&&b.ball_data.is_detected===true};
}
