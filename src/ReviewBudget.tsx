import {useState} from 'react';
import {intake,outcomes,replay,riskScore,selectReviews} from './review-budget';
import type {Replay} from './review-budget';

const pool=intake.filter(x=>x.first!=='unsupported').length;
const initialMisses=replay(intake,outcomes,[]).missed;
const seeds=Array.from({length:64},(_,i)=>101+i*97);
const metrics:[keyof Replay,string][]=[
 ['reviewed','Second reviews'],['recovered','Misses recovered'],['missed','Unsupported still missed'],['flagged','Escalated to adjudication'],
];
const format=(x:number)=>Number.isInteger(x)?String(x):x.toFixed(2);
function mean(budget:number,policy:'random'|'risk'){
 const totals:Replay={reviewed:0,recovered:0,missed:0,flagged:0};
 for(const seed of seeds){
  const result=replay(intake,outcomes,selectReviews(intake,budget,policy,seed));
  for(const [key] of metrics)totals[key]+=result[key];
 }
 for(const [key] of metrics)totals[key]/=seeds.length;
 return totals;
}
const curve = Array.from({length:pool+1},(_,budget)=>({random:mean(budget,'random'),risk:mean(budget,'risk')}));
const auditSlots=(budget:number)=>budget>=2?Math.max(1,Math.floor(budget/4)):0;

function BudgetChart({budget}:{budget:number}){
 const x=(n:number)=>52+548*n/pool;
 const y=(n:number)=>165-142*n/initialMisses;
 const line=(policy:'random'|'risk')=>curve.map((row,i)=>x(i)+','+y(row[policy].recovered)).join(' ');
 return <figure className="budget-figure">
  <figcaption><strong>Recovered misses by second-review budget</strong> <small>Mean across the same 64 fixed seeds · synthetic cases only</small></figcaption>
  <ul className="budget-legend"><li><i className="risk-line"/>Risk + random audit</li><li><i className="baseline-line"/>Random selection</li></ul>
  <svg viewBox="0 0 630 211" role="img" aria-labelledby="budget-chart-label budget-chart-detail">
   <title id="budget-chart-label">Recovered misses versus second reviews assigned</title>
   <desc id="budget-chart-detail">{`At ${budget} second reviews, random recovers ${format(curve[budget].random.recovered)} missed unsupported cases, and risk plus audit recovers ${format(curve[budget].risk.recovered)}, on average across 64 seeds.`}</desc>
   {[0,2,4,6,initialMisses].map(n=><g key={n}><line x1="52" x2="600" y1={y(n)} y2={y(n)} className="budget-grid"/><text x="43" y={y(n)+4} textAnchor="end">{n}</text></g>)}
   {[0,5,10,15,pool].map(n=><text key={n} x={x(n)} y="186" textAnchor="middle">{n}</text>)}
   <text x="325" y="206" textAnchor="middle">Second reviews assigned</text>
   <line x1={x(budget)} x2={x(budget)} y1="18" y2="165" className="budget-marker"/>
   <polyline points={line('random')} className="budget-baseline"/>
   <polyline points={line('risk')} className="budget-risk"/>
   <circle cx={x(budget)} cy={y(curve[budget].random.recovered)} r="4" className="baseline-dot"/>
   <circle cx={x(budget)} cy={y(curve[budget].risk.recovered)} r="4" className="risk-dot"/>
  </svg>
 </figure>;
}

export function ReviewBudget(){
 const [budget,setBudget]=useState(6);
 const [seed,setSeed]=useState(101);
 const selected=selectReviews(intake,budget,'risk',seed);
 const {random,risk}=curve[budget];
 const audit=auditSlots(budget);
 return <details className="quality budget-panel">
  <summary>Adaptive review · Budget replay</summary>
  <div className="budget-replay">
   <p><strong>Synthetic offline experiment.</strong> Every case received a first review. This replay has {pool} second-review candidates and {initialMisses} unsupported cases not flagged on the first pass. It does not modify the live queue.</p>
   <div className="budget-controls">
    <label>Second-review budget <output htmlFor="review-budget">{budget} / {pool}</output><input id="review-budget" aria-label="Second-review budget" type="range" min="0" max={pool} value={budget} onChange={e=>setBudget(Number(e.currentTarget.value))}/></label>
   </div>
   <BudgetChart budget={budget}/>
   <div className="budget-table"><table aria-label="Review policy outcomes">
    <thead><tr><th scope="col">Outcome</th><th scope="col">Random<br/><small>64-seed mean</small></th><th scope="col">Risk + random audit<br/><small>64-seed mean</small></th></tr></thead>
    <tbody>{metrics.map(([key,label])=><tr key={key}><th scope="row">{label}</th><td>{format(random[key])}</td><td>{format(risk[key])}</td></tr>)}</tbody>
   </table></div>
   <p>Both policies use the same second-review budget. Escalations are reported separately: each costs an extra adjudication. A case is counted as recovered only if it reaches adjudication and the reference outcome is unsupported. Any uncertainty or second-review unsupported verdict escalates.</p>
   <details><summary>Why these cases were selected</summary>
    <p>Priority uses only first-review uncertainty, evidence count and a fixture flag for a missing source qualifier. The audit samples uniformly from remaining cases. Second reviews and reference decisions are used only after routing.</p>
    <div className="budget-controls"><label>Inspect one risk replay <input aria-label="Risk replay seed" type="number" min={0} max={4294967295} step={1} value={seed} onChange={e=>setSeed(Math.max(0,Math.min(4294967295,Math.trunc(Number(e.currentTarget.value)))))}/></label></div>
    <p>{budget-audit} priority · {audit} audit</p>
    <ol>{selected.map((id,i)=>{
     const task=intake.find(x=>x.id===id)!;
     return <li key={id}>{id} · {i>=budget-audit?'Random audit':'Priority'} · risk {riskScore(task)}</li>;
    })}</ol>
    {!selected.length&&<p>No second reviews at this budget.</p>}
   </details>
   <p className="quality-help">The data and signal weights are authored examples, not a calibrated model. These results do not measure production accuracy or labor savings.</p>
  </div>
 </details>;
}
