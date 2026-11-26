export type EvidenceSpan = {target:'answer'|'passages';start:number;end:number;text:string};

export function currentAnchor(span:EvidenceSpan, content:string) {
 const {start,end,text}=span;
 const dividesPair=(offset:number)=>{
  const left=content.charCodeAt(offset-1),right=content.charCodeAt(offset);
  return left>=0xd800&&left<=0xdbff&&right>=0xdc00&&right<=0xdfff;
 };
 return Number.isInteger(start)&&Number.isInteger(end)&&start>=0&&end>start&&end<=content.length
  &&!dividesPair(start)&&!dividesPair(end)&&content.slice(start,end)===text;
}

export function overlapsAnchor(a:EvidenceSpan,b:EvidenceSpan){
 return a.target===b.target&&Math.max(a.start,b.start)<Math.min(a.end,b.end);
}
