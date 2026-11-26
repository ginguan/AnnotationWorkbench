import {test} from 'node:test';
import assert from 'node:assert/strict';
import {intake,outcomes,replay,riskScore,selectReviews} from '../src/review-budget.ts';

const pool=intake.filter(x=>x.first!=='unsupported');
test('both policies use equal budgets and exclude already flagged cases',()=>{
 for(const policy of ['random','risk']) for(let budget=0;budget<=pool.length;budget++){
  const ids=selectReviews(intake,budget,policy,101);
  assert.equal(new Set(ids).size,budget);
  assert(ids.every(id=>pool.some(row=>row.id===id)));
  assert.deepEqual(ids,selectReviews([...intake].reverse(),budget,policy,101));
 }
});
test('risk takes the highest available scores before the audit',()=>{
 const result=selectReviews(intake,8,'risk',101);
 const best=pool.map(riskScore).sort((a,b)=>b-a).slice(0,6);
 assert.deepEqual(result.slice(0,6).map(id=>riskScore(pool.find(x=>x.id===id))),best);
 const audits=new Set(Array.from({length:64},(_,i)=>selectReviews(intake,8,'risk',101+i*97).slice(6).join(',')));
 assert(audits.size>1);
});
test('outcomes are used for scoring only; a selected case can still be missed',()=>{
 const random=selectReviews(intake,pool.length,'random',101), risk=selectReviews(intake,pool.length,'risk',101);
 const a=replay(intake,outcomes,random), b=replay(intake,outcomes,risk);
 assert.deepEqual(a,b);
 assert.deepEqual(replay(intake,outcomes,[]),{reviewed:0,recovered:0,missed:8,flagged:0});
 assert.deepEqual(a,{reviewed:20,recovered:7,missed:1,flagged:9});
 const flipped=outcomes.map(row=>({...row,second:'supported'}));
 assert.equal(replay(intake,flipped,risk).missed,6);
});
