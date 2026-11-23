/* Browser-tab profile adapter. No accounts, server persistence or new eligibility rules. */
(function(root){
 'use strict';
 const valid=v=>v!==undefined&&v!==null&&v!==''&&!['all','unknown'].includes(v);
 const applicant={individual:'individual_farmer',young:'individual_farmer',prospective:'individual_farmer',agricultural_corporation:'agricultural_corporation',group:'group',business:'business'};
 let explicitStage=null;
 function toConversation(p,previous={}){
  const out={...previous};
  for(const k of ['region','farm_region','farm_registered','applicant','crop'])delete out[k];
  for(const [key,a,b]of [['region','residenceRegion','residenceDistrict'],['farm_region','region','district']]){
   if(valid(p[a]))out[key]=[p[a],valid(p[b])?p[b]:''].filter(Boolean).join(' ');
  }
  if(['yes','no'].includes(p.farmRegistered))out.farm_registered=p.farmRegistered;
  if(applicant[p.applicant])out.applicant=applicant[p.applicant];
  for(const [key,field]of [['farming_years','farmingYears'],['group_size','groupMemberCount']]){delete out[key];if(valid(p[field])&&Number.isFinite(Number(p[field]))&&Number(p[field])>=0)out[key]=Number(p[field]);}
  delete out.planned;
  if(p.farmingSituation==='preparing')out.planned=true;
  else if(p.farmingSituation==='independent')out.planned=false;
  else if(explicitStage&&explicitStage.situation===p.farmingSituation)out.planned=explicitStage.value;
  const crop=root.MunongsaCropDirectory?.find(document.getElementById('crop')?.selectedOptions[0]?.textContent||p.crop);
  if(crop)out.crop=crop.name;
  if(previous.crop!==undefined&&previous.crop!==out.crop||previous.planned!==undefined&&previous.planned!==out.planned)delete out.cultivating;
  const changed=['region','farm_region','crop','farm_registered','applicant','planned','farming_years','group_size'].some(k=>previous[k]!==out[k]);
  if(changed)for(const k of ['notice_ids','list_ids','list_versions','last_kind','search_offset','search_fingerprint','empty_search'])delete out[k];
  if(previous.crop!==out.crop)for(const k of ['search_crop','search_mode','search_query','tech_crop','tech_topic','tech_resource'])delete out[k];
  if(previous.farm_region!==out.farm_region)for(const k of ['search_scope','search_mode','search_query'])delete out[k];
  return out;
 }
 let applying=false;
 function apply(context){
  if(applying||typeof readProfile!=='function'||!root.MunongsaInputUX)return;
  applying=true;
  try{
   const p=readProfile(),before=toConversation(p),ux=root.MunongsaInputUX;
   for(const [key,kind]of [['region','residence'],['farm_region','farm'],['crop','crop']]){
    if(context[key]!==before[key]){const value=context[key]||'',province=kind!=='crop'?ux.places?.().find(row=>row.region===value&&!row.district):null;ux.commit(kind,province?.text||value);}
   }
   const set=(id,value)=>{const e=document.getElementById(id);if(e&&e.value!==value){e.value=value;e.dispatchEvent(new Event('change',{bubbles:true}));}};
   set('farmRegistered',context.farm_registered||'unknown');
   for(const [key,field]of [['farming_years','farmingYears'],['group_size','groupMemberCount']])if(context[key]!==before[key])set(field,context[key]===undefined?'':String(context[key]));
   if(context.applicant!==toConversation(readProfile()).applicant)set('applicant',Object.keys(applicant).find(k=>applicant[k]===context.applicant)||'all');
   if(context.planned===true)set('farmingSituation','preparing');
   else if(p.farmingSituation==='preparing')set('farmingSituation','unknown');
   // A chat statement about starting does not establish independent management.
   explicitStage=typeof context.planned==='boolean'?{value:context.planned,situation:readProfile().farmingSituation}:null;
   if(typeof draw==='function')draw();
  }finally{applying=false;}
 }
 const money={};
 document.addEventListener?.('change',event=>{if(!applying&&event.target?.id==='farmingSituation')explicitStage=null;},true);
 function fundingFacts(q){
  if(/만약|가정|이라면|있다면|하면|한다면|할\s*경우/.test(q))return [];
  const matches=[...q.matchAll(/(?:필요\s*(?:한\s*)?(?:자금|사업비|대출금)|(?:총\s*)?사업비|희망\s*대출금|보유\s*자금|자기\s*자금|자부담)\s*(?:은|는|이|가|을|를|:)?\s*([\d,]+(?:\.\d+)?\s*(?:억\s*(?:[\d,]+\s*만)?|천\s*만|만)?\s*원)/g)];
  const values=matches.map(m=>({won:root.MunongsaAmounts?.parseInput(m[1],'won'),kind:/보유|자기|자부담/.test(m[0])?'own':/대출금/.test(m[0])?'loan':/사업비/.test(m[0])?'project':'required'}));
  if(values.some(v=>!Number.isSafeInteger(v.won)||v.won<=0)||new Set(values.map(v=>v.kind)).size!==values.length)return [];
  return values;
 }
 function fundingQuestion(q){const values=fundingFacts(q);return values.length===1?values[0]:null;}
 root.MunongsaFarmProfile={toConversation,apply,fundingQuestion,fundingFacts,money,isApplying:()=>applying};
 document.addEventListener?.('munongsa:profile-reset',()=>{explicitStage=null;for(const key of Object.keys(money))delete money[key];});
 document.addEventListener?.('munongsa:profile-change',()=>setTimeout(()=>{
  if(typeof activeCategory==='undefined'||typeof readProfile!=='function')return;
  let link=document.getElementById('sharedProfileNext');const message=document.getElementById('resultMessage');if(!message)return;
  if(!link){link=document.createElement('p');link.id='sharedProfileNext';message.after(link);}
  link.replaceChildren();link.hidden=true;
  const financeNeed=readProfile().requiredFundsWon||Object.keys(money).length;
  const category=activeCategory==='bank'?'support':activeCategory==='support'&&financeNeed?'bank':null;
  if(!category)return;link.hidden=false;
  const button=document.createElement('button');button.type='button';button.className='source-action';button.textContent=category==='bank'?'자금이 필요하다면 같은 조건으로 농업금융 보기':'같은 조건으로 지원사업도 보기';button.addEventListener('click',()=>navigateTo(category));link.append(button);
 },0));
})(globalThis);
