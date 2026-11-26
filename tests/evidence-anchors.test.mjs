import assert from 'node:assert/strict';
import {test} from 'node:test';
import {currentAnchor, overlapsAnchor} from '../src/evidence-anchors.ts';
const anchor=(start,end,text,target='passages')=>({target,start,end,text});
test('checks UTF-16 boundaries and does not jump to stale or moved quotes',()=>{
 const s='😀 closed Mondays; open after noon';
 assert(currentAnchor(anchor(3,9,'closed'),s));
 assert(!currentAnchor(anchor(0,1,s.slice(0,1)),s));
 assert(!currentAnchor(anchor(3,9,'always'),s));
 assert(!currentAnchor(anchor(0,6,'closed'),s));
});
test('overlap compares geometry only, not verdict, with touching/or disjoint alternative citations allowed',()=>{
 assert(overlapsAnchor(anchor(0,4,'abcd'),anchor(0,4,'abcd')));
 assert(overlapsAnchor(anchor(0,4,'abcd'),anchor(2,6,'cdef')));
 assert(!overlapsAnchor(anchor(0,4,'abcd'),anchor(4,6,'ef')));
 assert(!overlapsAnchor(anchor(0,4,'abcd'),anchor(0,4,'abcd','answer')));
});
