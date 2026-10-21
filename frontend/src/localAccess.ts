export type LocalUser={id:string;username:string;role:'analyst'|'reviewer';is_owner:boolean};
export type LocalSession={user:LocalUser|null;csrf_token:string|null;needs_setup:boolean};
export async function getSession():Promise<LocalSession>{
 const r=await fetch('/api/access/session',{cache:'no-store'});
 if(!r.ok)throw Error('Could not read local session.');return r.json();
}
export async function localPost(path:string,body:unknown={}){
 const session=await getSession();
 return fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Pitchlight-Local':'1',...(session.csrf_token?{'X-CSRF-Token':session.csrf_token}:{})},body:JSON.stringify(body)});
}
export async function signOut(){const session=await getSession();if(session.user){const r=await localPost('/api/access/logout');if(!r.ok)throw Error('Sign-out failed. Please retry.');}}
