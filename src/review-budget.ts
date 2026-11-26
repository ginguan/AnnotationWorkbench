export type Verdict = 'supported' | 'unsupported' | 'uncertain';
export type Intake = {
 id:string;
 first:Verdict;
 firstEvidence:0|1|2; // Number of distinct evidence selections, capped at two.
 qualifierMismatch:boolean; // A synthetic answer/source rule found a missing condition.
};
export type Outcome = {id:string;second:Verdict;final:'supported'|'unsupported'};
export type Replay = {reviewed:number;recovered:number;missed:number;flagged:number};

function seeded(seed:number){
 let state=seed>>>0;
 return ()=>{state=(Math.imul(1664525,state)+1013904223)>>>0;return state/4294967296;};
}
function shuffle<T>(values:readonly T[],seed:number){
 const result=[...values], random=seeded(seed);
 for(let i=result.length-1;i>0;i--){
  const j=Math.floor(random()*(i+1));
  [result[i],result[j]]=[result[j],result[i]];
 }
 return result;
}

export function riskScore(task:Intake){
 return Number(task.qualifierMismatch)*4+Number(task.first==='uncertain')*2+(2-task.firstEvidence);
}

export function selectReviews(intake:readonly Intake[],budget:number,policy:'random'|'risk',seed:number){
 const pool=intake.filter(x=>x.first!=='unsupported').slice().sort((a,b)=>a.id.localeCompare(b.id));
 if(!Number.isInteger(budget)||budget<0||budget>pool.length)throw Error('Review budget must be within the candidate pool.');
 if(policy==='random')return shuffle(pool,seed).slice(0,budget).map(x=>x.id);
 const shuffled=shuffle(pool,seed);
 const audit=budget>=2?Math.max(1,Math.floor(budget/4)):0;
 const prioritized=shuffled.slice().sort((a,b)=>riskScore(b)-riskScore(a)).slice(0,budget-audit);
 const locked=new Set(prioritized.map(x=>x.id));
 return [...prioritized,...shuffle(pool.filter(x=>!locked.has(x.id)),seed^0xa511e9b3).slice(0,audit)].map(x=>x.id);
}

export function replay(intake:readonly Intake[],outcomes:readonly Outcome[],selection:readonly string[]):Replay{
 const outcomesById=new Map(outcomes.map(o=>[o.id,o]));
 const selected=new Set(selection);
 let recovered=0,missed=0,flagged=0;
 for(const task of intake){
  const outcome=outcomesById.get(task.id);
  if(!outcome)throw Error('Missing reference outcome for replay.');
  if(task.first==='unsupported')continue;
  const escalated=selected.has(task.id)&&(task.first==='uncertain'||outcome.second!=='supported');
  if(escalated)flagged++;
  if(outcome.final==='unsupported'){
   if(escalated)recovered++;
   else missed++;
  }
 }
 return {reviewed:selected.size,recovered,missed,flagged};
}

// Authored, intentionally mixed reports. Results illustrate mechanics, not measured accuracy.
const fixtures:readonly [Verdict,0|1|2,boolean,Verdict,Outcome['final']][]=[
 ['supported',1,true,'unsupported','unsupported'], // e.g. “returns allowed” omits “unopened”.
 ['supported',0,true,'supported','supported'],
 ['supported',1,false,'supported','supported'],
 ['uncertain',0,true,'unsupported','unsupported'],
 ['supported',2,false,'supported','supported'],
 ['supported',2,false,'uncertain','unsupported'],  // A case risk can miss; audit can catch it.
 ['uncertain',1,false,'supported','supported'],
 ['supported',1,true,'uncertain','unsupported'],
 ['supported',2,true,'supported','supported'],
 ['uncertain',1,false,'unsupported','unsupported'],
 ['supported',2,true,'supported','unsupported'],  // Both reviewers can miss it.
 ['supported',2,false,'unsupported','supported'],  // Escalation overruled on adjudication.
 ['supported',1,false,'supported','supported'],
 ['supported',1,false,'supported','supported'],
 ['supported',0,true,'unsupported','unsupported'],
 ['supported',2,false,'supported','supported'],
 ['supported',2,false,'supported','supported'],
 ['supported',2,false,'supported','supported'],
 ['supported',1,false,'uncertain','unsupported'],
 ['supported',2,false,'supported','supported'],
 ['unsupported',1,true,'unsupported','unsupported'],
 ['unsupported',2,false,'unsupported','unsupported'],
 ['unsupported',2,false,'supported','supported'],
 ['unsupported',2,true,'unsupported','unsupported'],
];
export const intake:Intake[]=fixtures.map(([first,firstEvidence,qualifierMismatch],i)=>
 ({id:'SIM-'+String(i+1).padStart(2,'0'),first,firstEvidence,qualifierMismatch}));
export const outcomes:Outcome[]=fixtures.map(([,,,second,final],i)=>({id:intake[i].id,second,final}));
