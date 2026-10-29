/* Compare facts already approved for display; never approve, mutate or invent eligibility. */
(function(root){
 'use strict';
 const names={applicant:'신청 대상',residence:'거주 지역',farm_registration:'경영체 등록',crop:'재배 작물',export_activity:'수출 활동',group_size:'공동 신청 인원',age:'연령',independent_management:'독립경영 기간',farming_experience:'영농 경력'};
 function project(item){
  if(item.verification_status!=='verified'||!['approved_reference','approved'].includes(item.publication)||!root.MunongsaSupport.safeUrl(item.url))return item;
  const target=item.target||'',original=item.eligibility||{},conditions=[...(original.conditions||[])],added=[];
  const evidence={url:item.url,location:'승인된 공식 안내의 지원대상 사실정보',fact_confirmed:true};
  function add(kind,value){if(conditions.some(c=>c.kind===kind&&c.status==='verified'&&c.presence==='specified'))return;const condition_id='display_fact_'+kind;conditions.push({condition_id,kind,presence:'specified',status:'verified',value,evidence});added.push({condition_id})}
  if(/농업경영체에\s*등록하고|경영체\s*등록\s*(?:청년농|농업인)/.test(target))add('farm_registration',{registered:true});
  // Specific crop names only; generic pepper does not establish dried-pepper eligibility.
  const crop=target.match(/(마늘|벼|양파|사과|배추|무|감자|고구마|콩|밀)(?:을|를)?\s*재배하는/);
  if(crop&&!/재배하는.{0,20}(?:제외|대상\s*아님)/.test(target))add('crop',{any_of:[crop[1]]});
  const residence=target.match(/(포항|전주)에\s*거주(?:하며|하는|하고)/),scopes={포항:'경북 포항시',전주:'전북 전주시'};
  if(residence)add('residence',{regions:[scopes[residence[1]]]});
  const group=target.match(/(\d+)\s*인\s*이상[^.。]{0,30}(?:법인|모임|단체)/);
  if(group&&!/(?:법인|모임|단체)(?:은|는)?\s*제외/.test(group[0]+target.slice(group.index+group[0].length,group.index+group[0].length+8))){const min=Number(group[1]);if(min>0&&min<=100000)add('group_size',{min,max:null,min_inclusive:true,max_inclusive:true,unit:'persons'})}
  const optionalExport=/수출실적(?:이)?\s*(?:없어도|무관|불필요)|수출(?:업체|농가).{0,8}(?:아니어도|않아도)|수출(?:업체|농가)(?:는|가)?\s*(?:제외|대상\s*아님)/.test(target);
  if(!optionalExport&&/수출업체|수출농가|수출실적(?:이\s*있는|\s*요건을\s*충족)|수출\s*농식품\s*업체/.test(target))add('export_activity',{required:true});
  if(!added.length)return item;
  // Retain UNKNOWN and all original AND/OR/NOT clauses, including exclusions.
  return {...item,eligibility:{conditions,logic:{op:'AND',children:[original.logic||{op:'UNKNOWN',children:[]},...added]}}};
 }
 function reasons(item,match){
  const negative=new Set();function walk(n,not=false){if(!n)return;if(n.condition_id){if(not)negative.add(n.condition_id);return}for(const c of n.children||[])walk(c,n.op==='NOT'?!not:not)}walk(item.eligibility?.logic);
  return match.conditions.filter(c=>c.status!=='check').map(c=>{const not=negative.has(c.id),state=not?{match:'mismatch',mismatch:'match'}[c.status]:c.status,label=names[c.field]||'확인된 조건';return {state,weight:not?0:1,text:not?(state==='mismatch'?'명시된 제외 조건에 해당':'해당 제외 조건과 다름'):(label+(state==='match'?' 일치':' 불일치'))}});
 }
 function support(data,profile,now=Date.now()){
  const groups=root.MunongsaSupport.explore(data,profile,now),rows=[...groups.recommendations,...groups.excluded,...groups.references];
  return rows.map(row=>{const projected=project(row.item),match=root.MunongsaSupport.evaluate(projected,profile),why=reasons(projected,match),place=String(profile.district||'').replace(/[시군]$/,''),scope=row.item.region||'';
   const geographic=place.length>=2&&place!=='all'&&scope.includes(place)?'영농지역과 안내 지역 관련 · 거주·농지 자격 충족 아님':null;
   return {...row,match,comparisonItem:projected,reasons:why,geographic,recommendationAllowed:row.available&&match.conditionStatus==='match',display:root.MunongsaSupportReview.presentation(row.item,now),relevance:why.reduce((n,r)=>n+(r.state==='match'?r.weight:0),0)+(geographic?2:0)};
  }).sort((a,b)=>{
   const period=r=>({window:0,unknown:1,upcoming:2,elapsed:3}[r.display.state]),condition=r=>({match:0,check:1,mismatch:2}[r.match.conditionStatus]);
   return period(a)-period(b)||condition(a)-condition(b)||b.relevance-a.relevance||(a.display.end||'9999-12-31').localeCompare(b.display.end||'9999-12-31')||a.item.id.localeCompare(b.item.id);
  });
 }
 root.MunongsaPersonalization={project,reasons,support};
})(globalThis);
