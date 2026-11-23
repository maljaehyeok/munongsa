/* Display exact, explicit KRW literals only. Never derive a grant or edit evidence. */
(function(root){
 'use strict';
 function literal(number,unit){
  if(!/^(?:\d+|[1-9]\d{0,2}(?:,\d{3})+)(?:\.\d{1,6})?$/.test(number))return null;
  const [whole,fraction='']=number.replace(/,/g,'').split('.'),scale=10n**BigInt(fraction.length),base=unit==='백만'?1000000n:unit==='천'?1000n:null;
  if(!base)return null;const numerator=BigInt(whole+fraction)*base;if(numerator%scale)return null;
  const won=numerator/scale;if(won>BigInt(Number.MAX_SAFE_INTEGER))return null;
  return Number(won);
 }
 function wonText(won){
  const parts=[],uk=Math.floor(won/100000000),man=Math.floor(won%100000000/10000),rest=won%10000;
  if(uk)parts.push(uk.toLocaleString('ko-KR')+'억');if(man)parts.push(man.toLocaleString('ko-KR')+'만');
  if(rest)parts.push(rest.toLocaleString('ko-KR'));
  return (parts.join(' ')||'0')+(rest?'원':' 원');
 }
 function analyse(value){
  const original=String(value??''),segments=[];let last=0,display='';
  const pattern=/(?<![\d.,])((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(백만|천)\s*원/g;
  for(const m of original.matchAll(pattern)){
   const prefix=original.slice(Math.max(0,m.index-32),m.index),end=m.index+m[0].length;
   // A shared range/list unit (100~200백만원) is ambiguous: leave it verbatim.
   if(/\d[\d,]*(?:\.\d+)?\s*[~∼–—-]\s*$/.test(prefix)||/\d\s*[,·]\s*$/.test(prefix))continue;
   const won=literal(m[1],m[2]);if(won===null)continue;
   const role=/총\s*(?:사업비|예산)|사업\s*전체\s*예산/.test(prefix)?'project_budget':/기준\s*단가|지원\s*단가|단가/.test(prefix)?'unit_price':/한도|최대/.test(prefix)?'ceiling':/개인|인당|농가당/.test(prefix)?'per_applicant':'unspecified';
   display+=original.slice(last,m.index)+wonText(won);last=end;segments.push({original:m[0],won,role});
  }
  return {original,display:display+original.slice(last),segments};
 }
 function parseInput(value,defaultUnit='man',allowZero=false){
  const s=String(value).trim().replace(/\s+/g,'');if(!s)return null;
  const n='(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d{1,4})?';
  let m=s.match(new RegExp('^('+n+')억(?:('+n+')만)?원?$'));
  let won;
  if(m)won=Number(m[1].replace(/,/g,''))*100000000+Number((m[2]||'0').replace(/,/g,''))*10000;
  else{m=s.match(new RegExp('^('+n+')(천만|만)?원?$'));if(!m)return NaN;const unit=m[2]||(/원$/.test(s)?'원':defaultUnit);won=Number(m[1].replace(/,/g,''))*({천만:10000000,만:10000,원:1,man:10000,won:1}[unit]);}
  return Number.isSafeInteger(won)&&(won>0||(allowZero&&won===0))?won:NaN;
 }
 root.MunongsaAmounts={literal,wonText,analyse,parseInput,format:v=>analyse(v).display};
})(globalThis);
