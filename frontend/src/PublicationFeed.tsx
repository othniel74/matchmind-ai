import {useEffect,useState} from 'react';
type Feed={items:{id:string;snapshot:{body:string;state_version:number;approved_by:{username:string}}}[];withheld_count:number};
export default function PublicationFeed({seed,userId}:{seed:number;userId:string}){
 const [feed,setFeed]=useState<Feed|null>(null),[error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();setFeed(null);setError('');
  async function refresh(){try{const r=await fetch(`/api/foundation/publications/feed?seed=${seed}`,{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('Sign in to inspect the local feed.');const next=await r.json();if(!controller.signal.aborted){setFeed(next);setError('')}}catch(e){if(!controller.signal.aborted){setFeed(null);setError(e instanceof Error?e.message:String(e))}}}
  void refresh();const timer=setInterval(()=>void refresh(),3000);return()=>{controller.abort();clearInterval(timer)};
 },[seed,userId]);
 return <div className="el-feed"><h3>What the local feed serves</h3>{error?<p role="alert">{error}</p>:feed?<>{feed.items.length?feed.items.map(item=><article key={item.id}><blockquote>{item.snapshot.body}</blockquote><small>STATE {item.snapshot.state_version} · APPROVED BY {item.snapshot.approved_by.username}</small></article>):<p>No active publications. Unapproved and withdrawn drafts are excluded.</p>}{feed.withheld_count>0&&<p role="alert">{feed.withheld_count} publication(s) withheld because an integrity or evidence check failed.</p>}</>:<p>Checking the publication gate…</p>}<p className="el-review-limit">Refreshes every three seconds. This is a local consumer preview.</p></div>
}
