import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Persona = 'reviewer-a'|'reviewer-b'|'adjudicator';
type Verdict = 'supported'|'unsupported'|'uncertain';
type State = 'awaiting_reviews'|'needs_adjudication'|'complete';
type Span = {target:'answer'|'passages'; start:number; end:number; text:string};
type Review = {actor:Persona; verdict:Verdict; rationale:string; spans:Span[]};
type Triage = {reason:'verdict_split'|'claim_span_split'|'both_uncertain'; overlap:number|null};
type Summary = {id:string; triage?:Triage; external_id:string|null; batch:string; source:string; question:string; rubric:string; state:State; submitted:boolean};
type Task = Omit<Summary,'submitted'> & {answer:string; passages:string; reviews:Review[]; final:Review|null; reference:{text:string;label_type:string}[]|null; canSubmit:boolean};
type BatchMetric = {
 batch:string; source:string; rubric:string; total:number; awaiting_reviews:number;
 needs_adjudication:number; finalized:number; adjudicated:number;
 verdict_split:number; claim_span_split:number; both_uncertain:number;
};
const names:Record<Persona,string>={'reviewer-a':'Reviewer A','reviewer-b':'Reviewer B',adjudicator:'Adjudicator'};
const verdicts:Record<Verdict,string>={supported:'Supported',unsupported:'Unsupported',uncertain:'Uncertain'};
const states:Record<State,string>={awaiting_reviews:'Awaiting reviews',needs_adjudication:'Needs adjudication',complete:'Complete'};
const enc=encodeURIComponent;
function triageLabel(t:Triage){
 if(t.reason==='verdict_split')return 'Different verdicts';
 if(t.reason==='both_uncertain')return 'Both uncertain';
 return t.overlap===null?'Different answer selections':new Intl.NumberFormat('en',{style:'percent',maximumFractionDigits:1}).format(t.overlap)+' answer overlap';
}

async function request<T>(persona:Persona,path:string,options?:RequestInit):Promise<T>{
 const res=await fetch('/api/'+path,{...options,headers:{'X-Demo-Persona':persona,...(options?.body?{'Content-Type':'application/json'}:{})}});
 if(!res.ok) throw Error((await res.json()).error ?? 'Request failed.');
 return res.json();
}
function App(){
 const [persona,setPersona]=useState<Persona>('reviewer-a');
 return <><header className="top"><div className="brand"><span className="logo" aria-hidden>◈</span><div><strong>Evidence Desk</strong><small>ANNOTATION WORKBENCH</small></div></div><label className="profile">Demo persona <select value={persona} onChange={e=>setPersona(e.target.value as Persona)}>{Object.entries(names).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label></header><Workspace key={persona} persona={persona}/></>;
}
function Workspace({persona}:{persona:Persona}){
 const [tasks,setTasks]=useState<Summary[]>([]);
 const [loaded,setLoaded]=useState(false);
 const [id,setId]=useState('');
 const [batch,setBatch]=useState('All batches');
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [revision,bump]=useState(0);
 useEffect(()=>{
  const controller=new AbortController();
  request<Summary[]>(persona,'tasks',{signal:controller.signal}).then(rows=>{setTasks(rows);setLoaded(true);})
   .catch(e=>{if(!controller.signal.aborted){setError(e.message);setLoaded(true);}});
  return ()=>controller.abort();
 },[persona,revision]);
 const visible=tasks.filter(row=>batch==='All batches'||row.batch===batch);
 const sorted=[...visible].sort((a,b)=>Number(persona==='adjudicator'?a.state==='complete':a.submitted)-Number(persona==='adjudicator'?b.state==='complete':b.submitted));
 const active=visible.some(row=>row.id===id)?id:sorted[0]?.id;
 const pending=visible.filter(t=>persona==='adjudicator'?t.state==='needs_adjudication':!t.submitted).length;
 async function download(){
  setError('');setNotice('');
  try{
   const response=await fetch('/api/export',{headers:{'X-Demo-Persona':persona}});
   if(!response.ok)throw Error((await response.json()).error);
   const blob=await response.blob();
   if(!blob.size){setNotice('No finalized tasks to export yet.');return;}
   const url=URL.createObjectURL(blob);
   const a=document.createElement('a');a.href=url;a.download='reviewed-annotations.jsonl';a.click();
   window.setTimeout(()=>URL.revokeObjectURL(url),1000);setNotice('Finalized annotations exported.');
  }catch(e){setError((e as Error).message);}
 }
 return <main><section className="intro"><div><span className="eyebrow">GROUNDING REVIEW / V1</span><h1>{persona==='adjudicator'?'Adjudication queue':'Review queue'}</h1><p>{persona==='adjudicator'?'Resolve disagreements before exporting an evaluation batch. Different verdicts and non-overlapping claims are queued first.':'Check whether an AI answer is supported by the supplied source material.'}</p></div>{persona==='adjudicator'&&<button className="secondary" onClick={download}>Export JSONL ↓</button>}</section>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {persona==='adjudicator'&&<><BatchImport onImported={()=>bump(n=>n+1)}/><BatchQuality revision={revision}/></>}
 <div className="shell"><aside className="queue" aria-label="Tasks"><div className="queue-title"><strong>Tasks</strong><span>{pending} pending</span></div>
 <label className="batch">Batch<select aria-label="Batch" value={batch} onChange={e=>setBatch(e.target.value)}><option>All batches</option>{[...new Set(tasks.map(t=>t.batch))].map(b=><option key={b}>{b}</option>)}</select></label>
 <nav aria-label="Task queue">{sorted.map(t=><button className="queue-item" key={t.id} aria-current={t.id===active?'true':undefined} onClick={()=>setId(t.id)}><small>{t.external_id??t.id.toUpperCase()} · {t.source==='synthetic'?'Synthetic demo':t.source}</small><strong>{t.question}</strong><span className={'badge '+t.state}>{t.submitted && t.state==='awaiting_reviews'?'Your review submitted':states[t.state]}</span>{t.triage&&<small className="triage-label">{triageLabel(t.triage)}</small>}</button>)}</nav></aside>
 <section aria-label="Review workspace">{active?< TaskPanel key={active} id={active} persona={persona} onSaved={()=>bump(n=>n+1)} />:<div className="empty">{!loaded?'Loading tasks…':persona==='adjudicator'?'No completed review pairs yet. Submit both independent reviews to populate this queue.':'No tasks in this batch.'}</div>}</section></div></main>;
}
function BatchImport({onImported}:{onImported:()=>void}){
 const [batch,setBatch]=useState('');
 const [file,setFile]=useState<File>();
 const [busy,setBusy]=useState(false);
 const [notice,setNotice]=useState('');
 const [error,setError]=useState('');
 const sending=useRef(false);
 async function upload(e:React.FormEvent){
  e.preventDefault();
  if(sending.current)return;
  if(!file||file.size===0||file.size>2*1024*1024){setError('Choose a nonempty JSONL file up to 2 MiB.');return;}
  sending.current=true;setBusy(true);setError('');setNotice('');
  try{
   const response=await fetch('/api/import?batch='+enc(batch),{method:'POST',headers:{'X-Demo-Persona':'adjudicator','Content-Type':'application/x-ndjson'},body:file});
   const result=await response.json();
   if(!response.ok)throw Error(result.error??'Import failed.');
   setNotice(`${result.batch}: ${result.inserted} added, ${result.skipped} already present. Switch to a reviewer persona to see the new tasks.`);
   onImported();
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);sending.current=false;}
 }
 return <details className="quality"><summary>Import JSONL batch</summary>
 <p className="quality-help">Local only. Use UTF-8, one task per line, up to 300 rows or 2 MiB. Required keys: id, question, passages, answer.</p>
 <form className="import-form" onSubmit={upload}>
 <label>Batch name<input value={batch} required maxLength={70} onChange={e=>setBatch(e.target.value)} placeholder="e.g. July documentation checks"/></label>
 <label>JSONL file<input type="file" accept=".jsonl,.ndjson,application/x-ndjson" required onChange={e=>setFile(e.target.files?.[0])}/></label>
 <button className="primary" type="submit" disabled={busy}>{busy?'Importing…':'Import batch'}</button>
 </form>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 </details>;
}

function BatchQuality({revision}:{revision:number}){
 const [rows,setRows]=useState<BatchMetric[]>();
 const [error,setError]=useState('');
 useEffect(()=>{
  const controller=new AbortController();
  setError('');
  request<BatchMetric[]>('adjudicator','batch-metrics',{signal:controller.signal}).then(setRows)
   .catch(e=>{if(!controller.signal.aborted){setRows(undefined);setError(e.message);}});
  return ()=>controller.abort();
 },[revision]);
 return <details className="quality"><summary>Batch quality</summary>
 <p className="quality-help">Disagreement rate uses finalized tasks only. Compare batches within the same rubric; both uncertain is reported separately.</p>
 {error?<p className="error" role="alert">{error}</p>:!rows?<p role="status">Loading batch quality…</p>:!rows.length?<p>No batches yet.</p>:
 <div className="quality-grid">{rows.map(row=>{
  const disagree=row.verdict_split+row.claim_span_split;
  const rate=row.finalized ? new Intl.NumberFormat('en',{style:'percent',maximumFractionDigits:1}).format(disagree/row.finalized) : '—';
  return <section className="quality-card" key={[row.batch,row.source,row.rubric].join('|')} aria-label={row.batch+' metrics'}>
   <h2>{row.batch}</h2><small>{row.source==='synthetic'?'Synthetic demo':row.source} · {row.rubric}</small>
   <dl>
    <div><dt>Finalized</dt><dd>{row.finalized} / {row.total}</dd></div>
    <div><dt>Disagreement rate</dt><dd>{rate}</dd></div>
    <div><dt>Waiting for both reviews</dt><dd>{row.awaiting_reviews}</dd></div>
    <div><dt>Awaiting adjudication</dt><dd>{row.needs_adjudication}</dd></div>
   </dl>
   <p>{row.finalized===0?'No finalized tasks yet.':`Among finalized: ${row.verdict_split} verdict splits · ${row.claim_span_split} claim-span splits · ${row.both_uncertain} both uncertain.`}</p>
  </section>;
 })}</div>}
 </details>;
}

function TaskPanel({id,persona,onSaved}:{id:string;persona:Persona;onSaved:()=>void}){
 const [task,setTask]=useState<Task>();
 const [verdict,setVerdict]=useState<Verdict|' ' >(' ');
 const [rationale,setRationale]=useState('');
 const [spans,setSpans]=useState<Span[]>([]);
 const [error,setError]=useState('');
 const [saving,setSaving]=useState(false);
 const sending=useRef(false);
 const passage=useRef<HTMLDivElement>(null);
 const answer=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  const controller=new AbortController();
  request<Task>(persona,'tasks/'+enc(id),{signal:controller.signal}).then(setTask).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
  return ()=>controller.abort();
 },[id,persona]);
 function collect(target:Span['target']){
  const el=(target==='answer'?answer:passage).current;
  const selected=window.getSelection();
  if(!el||!selected||selected.isCollapsed||!selected.rangeCount){setError('Select text in this panel first.');return;}
  const range=selected.getRangeAt(0);
  if(!el.contains(range.startContainer)||!el.contains(range.endContainer)){setError('Keep the selection in a single text panel.');return;}
  const startRange=document.createRange();startRange.selectNodeContents(el);startRange.setEnd(range.startContainer,range.startOffset);
  const start=startRange.toString().length,text=range.toString(),end=start+text.length;
  if(!text.trim()){setError('Select actual text.');return;}
  if(spans.some(s=>s.target===target&&s.start===start&&s.end===end)){setError('That selection is already included.');return;}
  if(spans.length>=10){setError('Add at most ten selections.');return;}
  setSpans(prev=>[...prev,{target,start,end,text}]);setError('');selected.removeAllRanges();
 }
 async function submit(e:React.FormEvent){
  e.preventDefault();if(sending.current)return;
  sending.current=true;setSaving(true);setError('');
  try{
   await request(persona,'tasks/'+enc(id),{method:'POST',body:JSON.stringify({verdict,rationale,spans})});
   setTask(await request<Task>(persona,'tasks/'+enc(id)));onSaved();
  }catch(e){setError((e as Error).message);}
  finally{sending.current=false;setSaving(false);}
 }
 if(!task)return <div className={error?'error':'empty'} role={error?'alert':'status'}>{error||'Loading task…'}</div>;
 function textPanel(target:Span['target'],title:string,ref:React.RefObject<HTMLDivElement|null>){
  return <section className="paper"><header><h3>{title}</h3>{task?.canSubmit&&<button className="link" onMouseDown={e=>e.preventDefault()} onClick={()=>collect(target)}>+ Add selection</button>}</header><div tabIndex={0} ref={ref} className="text">{task?.[target]}</div></section>;
 }
 return <article className="task">
 <header className="task-header"><div className="meta"><span>{task.external_id??task.id.toUpperCase()} / {task.batch}</span><span className={'badge '+task.state}>{states[task.state]}</span></div><h2>{task.question}</h2><small>Rubric: {task.rubric} · {task.source==='synthetic'?'Synthetic example':task.source}</small></header>
 <div className="panes">{textPanel('passages','Source passages',passage)}{textPanel('answer','AI answer',answer)}</div>
 {task.reviews.length>0&&<section className="review-box"><h3>{persona==='adjudicator'||task.state==='complete'?'Review record':'Your review'}</h3><div className="review-cards">{task.reviews.filter(r=>r.actor!=='adjudicator').map(r=><ReviewCard key={r.actor} review={r}/>)}</div></section>}
 {task.final&&<section className="review-box final"><h3>Final decision · {task.final.actor==='adjudicator'?'Adjudicated':'Consensus'}</h3><ReviewCard review={task.final}/>{task.reference!==null&&<details><summary>Reveal benchmark annotations</summary><ul>{task.reference.length===0?<li>No hallucination spans in the reference annotations.</li>:task.reference.map((r,i)=><li key={i}>{r.label_type}: “{r.text}”</li>)}</ul></details>}</section>}
 {task.canSubmit?<form className="review-box" onSubmit={submit}><h3>{persona==='adjudicator'?'Record a final decision':'Submit independent review'}</h3><p className="form-help">Select text above, then click Add selection. Mark supporting evidence in the source, or a specific unsupported claim in the answer.</p>
 <fieldset><legend>Verdict</legend>{Object.entries(verdicts).map(([key,label])=><label key={key}><input type="radio" name="verdict" required checked={verdict===key} onChange={()=>setVerdict(key as Verdict)}/>{label}</label>)}</fieldset>
 {spans.length>0&&<ul className="selections">{spans.map((s,i)=><li key={s.target+s.start+':'+s.end}><small>{s.target==='passages'?'Source':'Answer'}</small> “{s.text}” <button type="button" className="link" aria-label={'Remove selection '+(i+1)} onClick={()=>setSpans(v=>v.filter((_,j)=>i!==j))}>Remove</button></li>)}</ul>}
 <label className="rationale">Rationale<textarea required minLength={3} maxLength={1500} value={rationale} onChange={e=>setRationale(e.target.value)} placeholder="Explain why the supplied evidence supports or fails to support this answer." rows={2}/></label>
 {error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={saving}>{saving?'Saving…':persona==='adjudicator'?'Finalize decision':'Submit review'}</button></form>:
 task.state!=='complete'&&persona!=='adjudicator'?<p className="waiting" role="status">{task.state==='needs_adjudication'?'Both reviews are in. This task is awaiting adjudication.':'Your review is locked. The other reviewer has not finished yet.'}</p>:null}
 </article>;
}
function ReviewCard({review}:{review:Review}){
 return <div className="review-card"><strong>{names[review.actor]} · {verdicts[review.verdict]}</strong><p>{review.rationale}</p>{review.spans.length>0&&<ul>{review.spans.map(s=><li key={s.target+s.start+':'+s.end}>{s.target==='passages'?'Source':'Answer'}: “{s.text}”</li>)}</ul>}</div>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
