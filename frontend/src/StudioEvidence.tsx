import {useEffect,useRef} from 'react';
import {X,ShieldCheck} from 'lucide-react';
import EvidenceLab from './EvidenceLab';
import WorkspaceAccess from './WorkspaceAccess';
import './studio-evidence.css';

export type ReviewContext={minute:number;seed:number;accountOnly?:boolean};

export default function StudioEvidence({context,onDismiss}:{context:ReviewContext;onDismiss:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{
  const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
  const element=dialog.current;
  element?.showModal();
  return()=>{element?.close();previous?.focus()};
 },[]);
 return <dialog ref={dialog} className="studio-evidence-dialog" aria-labelledby="studio-evidence-title" onCancel={e=>{e.preventDefault();onDismiss()}}>
  <header className="studio-evidence-heading"><div><small><ShieldCheck size={14}/> PITCHLIGHT STUDIO</small><h2 id="studio-evidence-title">{context.accountOnly?'Workspace access':'Evidence & story review'}</h2><p>{context.accountOnly?'Manage your local session and team access.':`Passing observation at ${context.minute}′ · the match continues in the background.`}</p></div><button type="button" onClick={onDismiss} autoFocus aria-label="Close evidence panel"><X size={20}/></button></header>
  {context.accountOnly?<section className="evidence-lab evidence-embedded"><WorkspaceAccess onUser={()=>{}}/></section>:<EvidenceLab embedded initialMinute={context.minute} initialSeed={context.seed}/>}
 </dialog>
}
