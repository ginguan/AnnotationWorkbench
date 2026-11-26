import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const port=Number(process.argv[2]??5195);
const taskName='Can I collect an order from the nursery on Monday?';
const browser=await chromium.launch();
const contexts=[];
const errors=[];
async function page(persona,viewport,query=''){
 const ctx=await browser.newContext({viewport});contexts.push(ctx);
 const p=await ctx.newPage();p.on('pageerror',error=>errors.push(error.message));
 await p.goto('http://127.0.0.1:'+port+'/'+query);
 await p.getByLabel('Demo persona').selectOption(persona);
 await p.getByRole('navigation',{name:'Task queue'}).getByRole('button',{name:new RegExp(taskName.replace('?','\\?'))}).click();
 return p;
}
async function review(p,{target,phrase,verdict,rationale,submit}){
 const panel=p.locator('.paper').filter({has:p.getByRole('heading',{name:target,exact:true})});
 if(phrase){
   await panel.locator('.text').evaluate((el,phrase)=>{
     const index=el.textContent.indexOf(phrase);
     if(index<0)throw new Error('Could not locate evidence fixture');
     function position(offset){
       const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
       for(let node; (node=walker.nextNode()); ){
         if(offset<=node.length)return [node,offset];
         offset-=node.length;
       }
       throw new Error('Text offset outside evidence fixture');
     }
     const range=document.createRange(); range.setStart(...position(index)); range.setEnd(...position(index+phrase.length));
     window.getSelection().removeAllRanges();window.getSelection().addRange(range);
   },phrase);
   await panel.getByRole('button',{name:'Add selection'}).click();
   await p.locator('.selections').getByText(phrase,{exact:false}).waitFor();
 }
 await p.getByRole('radio',{name:verdict,exact:true}).check();
 await p.getByLabel('Rationale').fill(rationale);
 await p.getByRole('button',{name:submit,exact:true}).click();
}
try{
 const a=await page('reviewer-a',{width:1280,height:900});
 await review(a,{target:'Source passages',phrase:'The nursery is closed on Mondays.',verdict:'Supported',rationale:'The days match the source schedule.',submit:'Submit review'});
 await a.getByText('Your review is locked',{exact:false}).waitFor();
 const b=await page('reviewer-b',{width:390,height:844});
 assert.equal(await b.getByText('The days match the source schedule.').count(),0);
 assert.equal(await b.getByText('Reveal benchmark annotations').count(),0);
 assert.equal(await b.evaluate(()=>document.documentElement.scrollWidth),390);
 await review(b,{target:'AI answer',verdict:'Uncertain',rationale:'I was not sure if the location also needed verification.',submit:'Submit review'});
 await b.getByText('This task is awaiting adjudication.',{exact:false}).waitFor();
 const baseline=await page('adjudicator',{width:1280,height:900},'#citation-pilot-baseline');
 await baseline.getByRole('heading',{name:'Review record',exact:true}).waitFor();
 await baseline.getByText('The days match the source schedule.').waitFor();
 assert.equal(await baseline.getByRole('button',{name:/Jump to .* citation/}).count(),0);
 assert.equal(await baseline.getByRole('button',{name:'Finalize decision'}).count(),1);
 assert.match(await baseline.locator('.paper .text').first().innerText(),/Bring the order confirmation to the east gate/);
 const j=await page('adjudicator',{width:1280,height:900});
 await j.getByText('The days match the source schedule.').waitFor();
 await j.getByText('Different verdicts',{exact:true}).waitFor();
 await j.getByRole('heading',{name:'Compare reviewer evidence'}).waitFor();
 assert.equal(await b.getByRole('button',{name:/Jump to .* citation/}).count(),0);
 await j.getByRole('button',{name:'Jump to Reviewer A citation 1'}).click();
 const anchor=j.locator('mark.evidence-jump');
 assert.equal(await anchor.innerText(),'The nursery is closed on Mondays.');
 assert.match(await anchor.locator('..').innerText(),/Bring the order confirmation to the east gate/);
 assert.equal(await anchor.evaluate(node=>document.activeElement===node),true);
 await j.getByText('Batch quality',{exact:true}).click();
 const quality=j.getByRole('region',{name:'Demo metrics'});
 await quality.getByText('1 / 3',{exact:true}).waitFor();
 await quality.getByText('100%',{exact:true}).waitFor();

 await j.getByText('Adaptive review · Budget replay',{exact:true}).click();
 const budget=j.locator('.budget-panel');
 await budget.getByText('Synthetic offline experiment.',{exact:true}).waitFor();
 const graph=budget.getByRole('img',{name:'Recovered misses versus second reviews assigned'});
 await graph.waitFor();
 const counts=budget.getByRole('row',{name:/^Second reviews/});
 assert.deepEqual(await counts.getByRole('cell').allTextContents(),['6','6']);
 if(process.env.ANNOTATION_BUDGET_SCREENSHOT)await budget.screenshot({path:process.env.ANNOTATION_BUDGET_SCREENSHOT,animations:'disabled'});
 const slider=budget.getByRole('slider',{name:/Second-review budget/});
 await slider.focus();
 await slider.press('End');
 assert.deepEqual(await counts.getByRole('cell').allTextContents(),['20','20']);
 assert.deepEqual(await budget.getByRole('row',{name:/^Misses recovered/}).getByRole('cell').allTextContents(),['7','7']);
 await budget.getByText('Why these cases were selected',{exact:true}).click();
 assert.equal(await budget.getByText(/· Random audit · risk/).count(),5);
 await b.getByLabel('Demo persona').selectOption('adjudicator');
 await b.getByText('Adaptive review · Budget replay',{exact:true}).click();
 assert.equal(await b.evaluate(()=>document.documentElement.scrollWidth),390);
 await j.getByText('I was not sure if the location also needed verification.').waitFor();
 await review(j,{target:'Source passages',phrase:'Bring the order confirmation to the east gate.',verdict:'Supported',rationale:'Both the days and the location are present in the source.',submit:'Finalize decision'});
 await j.getByRole('heading',{name:'Final decision · Adjudicated'}).waitFor();
 await quality.getByText('2 / 3',{exact:true}).waitFor();
 await quality.getByText('2 verdict splits',{exact:false}).waitFor();

 const pending=j.waitForEvent('download');
 await j.getByRole('button',{name:'Export JSONL'}).click();
 const download=await pending;
 const exported=(await readFile(await download.path(),'utf8')).trim().split('\n').map(JSON.parse);
 assert(exported.some(row=>row.task_id==='demo-02'&&row.verdict==='supported'&&row.resolution==='adjudicated'));
 await j.getByText('Import JSONL batch',{exact:true}).click();
 await j.getByLabel('Batch name').fill('Browser batch');
 const row={id:'new-1',question:'Do these windows open?',passages:'All windows are locked.',answer:'No.'};
 await j.getByLabel('JSONL file').setInputFiles({name:'questions.jsonl',mimeType:'application/x-ndjson',buffer:Buffer.from(JSON.stringify(row)+'\n')});
 await j.getByRole('button',{name:'Import batch',exact:true}).click();
 await j.getByText('Browser batch: 1 added, 0 already present.',{exact:false}).waitFor();
 await j.getByLabel('Demo persona').selectOption('reviewer-a');
 await j.getByLabel('Batch',{exact:true}).selectOption('Browser batch');
 await j.getByRole('heading',{name:row.question,exact:true}).waitFor();

 assert.deepEqual(errors,[]);
 console.log('PASS: independent desktop/390px browser contexts, capture evidence, adjudicate, download and parse JSONL.');
}finally{for(const ctx of contexts)await ctx.close();await browser.close();}
