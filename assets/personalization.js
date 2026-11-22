/* Compare facts already approved for display; never approve, mutate or invent eligibility. */
(function(root){
 'use strict';
 const names={applicant:'신청 대상',residence:'거주 지역',farm_registration:'경영체 등록',crop:'재배 작물',export_activity:'수출 활동',group_size:'공동 신청 인원',age:'연령',independent_management:'독립경영 기간',farming_experience:'영농 경력'};
 const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
 function sourceConditions(item,annotation,now){
  const basis=Object.fromEntries(['id','title','url','target','region','reference_application_dates','application_period','eligibility'].map(k=>[k,item[k]??null]));
  if(!annotation||annotation.review_required||annotation.complete!==false||Date.parse(annotation.expires_at)<=now||!Number.isFinite(Date.parse(annotation.expires_at))||canonical(annotation.basis)!==canonical(basis)||!['approved','approved_reference','official_guidance'].includes(item.publication))return null;
  const allowed=['farm_registration','residence','business_location','crop','scale','applicant'];
  if(!Array.isArray(annotation.conditions)||!annotation.conditions.length||!annotation.conditions.every(c=>allowed.includes(c.kind)&&c.status==='verified'&&c.presence==='specified'&&c.evidence?.fact_confirmed===true&&c.evidence.url===item.url&&c.evidence.location))return null;
  const original=item.eligibility||{},conditions=[...(original.conditions||[]),...annotation.conditions];
  if(new Set(conditions.map(c=>c.condition_id)).size!==conditions.length)return null;
  return {...item,eligibility:{conditions,logic:{op:'AND',children:[original.logic||{op:'UNKNOWN',children:[]},...annotation.conditions.map(c=>({condition_id:c.condition_id}))]}}};
 }
 function sourceFacts(item,annotation,now){
  const basis=Object.fromEntries(['id','title','url','target','region','reference_application_dates','application_period','eligibility'].map(k=>[k,item[k]??null]));
  if(!annotation||annotation.review_required||annotation.complete!==false||!Number.isFinite(Date.parse(annotation.checked_at))||Date.parse(annotation.checked_at)>now||canonical(annotation.basis)!==canonical(basis)||annotation.evidence?.url!==item.url||annotation.evidence.fact_confirmed!==true)return item;
  const fields=annotation.fields||{},allowed=['reference_application_dates','application_method','target','support','geographic_scope','scope_note'];
  if(Object.keys(fields).some(k=>!allowed.includes(k)))return item;
  const r=annotation.reception||{},age=now-Date.parse(r.checked_at),reception=age>=0&&age<86400000&&r.status==='open_notice_verified'?r:null;
  return {...item,...fields,...(Object.keys(fields.reference_application_dates||{}).length?{verified_period_at:annotation.checked_at}:{}),last_checked_at:annotation.checked_at,verified_facts_at:annotation.checked_at,verified_reception:reception,
    facts_unknown:Array.isArray(annotation.unknown)?annotation.unknown:[],eligibility_complete:false};
 }
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
  return match.conditions.filter(c=>c.status!=='check').map(c=>{const not=negative.has(c.id),state=not?{match:'mismatch',mismatch:'match'}[c.status]:c.status,label=names[c.field]||'확인된 조건';
   const condition=(item.eligibility?.conditions||[]).find(v=>v.condition_id===c.id),individual=not&&c.field==='applicant'&&condition?.value?.one_of?.length===1&&condition.value.one_of[0]==='individual_farmer';
   const text=individual?(state==='mismatch'?'개인 단독 신청 대상 아님':'개인 단독 신청 제외 조건에는 해당하지 않음'):not?(state==='mismatch'?'명시된 제외 조건에 해당':'이 제외 조건에는 해당하지 않음'):c.field==='export_activity'?(state==='match'?'수출 관련 기본 응답 일치 · 품목·실적·회원사 등 세부 요건 별도 확인':'수출 관련 기본 응답 불일치'):(label+(state==='match'?' 일치':' 불일치'));
   return {state,weight:not?0:1,text};
  });
 }
 // Interest vocabulary never creates an eligibility condition.
 const topics=[['startup',/창업|귀농|처음|초보|정착|농사.{0,6}시작/,/창업|귀농|정착|후계농/,'창업·영농 시작'],['facility',/시설|하우스|온실|스마트팜|현대화/,/시설|하우스|온실|스마트팜|현대화/,'시설 설치·개선'],['machinery',/농기계|트랙터|농업기계/,/농기계|트랙터|농업기계/,'농기계 구입'],['education',/교육|배우|연수|공부/,/교육|연수|대학|교육생|학습|수강/,'농업 교육'],['fertilizer',/비료|유기질|유기농업자재|토양/,/비료|유기질|유기농업자재|토양/,'비료·토양 관리'],['export',/수출|해외판로/,/수출|해외판로/,'수출 지원'],['insurance',/보험|재해/,/보험|재해/,'보험·재해'],['finance',/융자|대출|금융|운영\s*자금|자금.{0,4}부족/,/융자|대출|금융|운영\s*자금/,'금융·운영 자금']];
 function discovery(item,profile={},query=''){
  const title=String(item.title||'').toLowerCase(),hay=[title,item.institution,item.target,item.support,item.application_preparation?.office_note].filter(v=>typeof v==='string'&&v!=='unknown').join(' ').toLowerCase(),q=String(query).toLowerCase().trim();
  const terms=(q.match(/[가-힣a-z0-9]+/g)||[]).map(t=>t.replace(/(?:으로|에서|관련|을|를|이|가|은|는)$/,'')).filter(t=>t.length>1&&!/^(지원사업|지원|사업|공고|농사|농업|농업인|관련|어떤|있어|알려줘|보여줘|하려고|해요)$/.test(t));
  const content=[title,item.support].filter(v=>typeof v==='string'&&v!=='unknown').join(' '),wanted=topics.filter(g=>g[1].test(q)),installation=/설치|하우스|온실|현대화/.test(q),installPurpose=/시설원예|시설현대화|시설지원|시설\s*지원|온실|하우스|스마트팜|시설.{0,8}(?:설치|신축|개보수|현대화)/;
  const thematic=wanted.filter(g=>g[2].test(content)&&(g[0]!=='facility'||!installation||installPurpose.test(content)));
  const hits=terms.filter(t=>hay.includes(t)),compact=q.replace(/[^가-힣a-z0-9]/g,''),titleCompact=title.replace(/[^가-힣a-z0-9]/g,''),exact=titleCompact.length>=6&&compact.includes(titleCompact);
  const cropWord=['토마토','딸기','감귤','마늘','벼','사과','포도','상추','고추','배추','콩','오이'].find(c=>q.includes(c));
  const preparing=profile.farmingSituation==='preparing',broadened=!!q&&!wanted.length&&!!cropWord&&preparing&&topics[0][2].test(content),place=[profile.district,profile.region].filter(t=>t&&t!=='all').some(t=>hay.includes(t)),crop=profile.crop&&profile.crop!=='all'&&content.includes(profile.crop);
  const audiencePenalty=(preparing||profile.applicant==='individual')&&/기업|수출업체|기관 모집/.test(title)&&!/기업|수출/.test(q)?45:0;
  const remaining=/신청기간.{0,8}남|기간.{0,5}남은|마감.{0,5}남은/.test(q),periodOnly=remaining&&!wanted.length&&!cropWord;
  const matches=(!q||exact||periodOnly||(wanted.length?thematic.length===wanted.length:cropWord?content.includes(cropWord)||broadened:hits.length>0))&&(!remaining||['window','upcoming'].includes(root.MunongsaSupportReview.presentation(item).state));
  const reasons=exact?['사업명 일치']:thematic.length?[thematic.map(g=>g[3]).join(' · ')+' 분야의 공개 정보 일치']:broadened?['영농 준비 관련 대안 · 작물 전용 사업 아님']:cropWord&&content.includes(cropWord)?['공개 정보에 '+cropWord+' 명시']:hits.length?['검색어가 공개 정보에 포함']:preparing&&topics[0][2].test(content)?['영농 시작 관심 분야 관련']:[];
  return {score:(exact?1000:0)+hits.reduce((n,t)=>n+(title.includes(t)?20:8),0)+thematic.reduce((n,g)=>n+(g[2].test(title)?70:35),0)+(preparing&&topics[0][2].test(content)?8:0)+(place?3:0)+(crop?5:0)-audiencePenalty,matches,reasons,broadened,eligibility_confirmed:false};
 }
 function support(data,profile,now=Date.now()){
  const groups=root.MunongsaSupport.explore(data,profile,now),rows=[...groups.recommendations,...groups.excluded,...groups.references];
  return rows.map(row=>{const facts=data.verified_facts?.[row.item.id],shown=root.MunongsaNoticeReview?.project(sourceFacts(row.item,facts,now),data.notice_observations?.[row.item.id],now)||sourceFacts(row.item,facts,now),reviewed=sourceConditions(row.item,data.verified_comparisons?.[row.item.id]||facts,now),projected=project(reviewed||row.item),match=root.MunongsaSupport.evaluate(projected,profile),why=reasons(projected,match),place=String(profile.district||'').replace(/[시군]$/,''),scope=row.item.region||'';
   const geographic=place.length>=2&&place!=='all'&&scope.includes(place)?'영농지역과 안내 지역 관련 · 거주·농지 자격 충족 아님':null;
   const display=root.MunongsaSupportReview.presentation(shown,now),verdict=decision(projected,shown,match,profile),relatedCandidate=verdict.region_state==='match'&&!verdict.excluded&&display.state==='window'&&why.some(r=>r.state==='match');
   const sourceWarning=data.source_review?.[row.item.id]?.title_needs_review===true;
   return {...row,discovery:discovery(shown,profile,profile.supportSearch||''),sourceItem:row.item,item:shown,match,decision:verdict,comparisonItem:{...shown,eligibility:projected.eligibility},reasons:why,geographic,sourceWarning,comparisonReady:!!reviewed&&!sourceWarning,relatedCandidate:relatedCandidate&&!sourceWarning,recommendationAllowed:row.available&&verdict.category==='A'&&!sourceWarning,display,relevance:why.reduce((n,r)=>n+(r.state==='match'?r.weight:0),0)};
  }).sort((a,b)=>{
   const period=r=>({window:r.display.operator_notice?0:1,upcoming:2,standing:3,unknown:4,elapsed:5}[r.display.state]??4),condition=r=>({match:0,check:1,mismatch:2}[r.match.conditionStatus]);
   return Number(a.decision.excluded)-Number(b.decision.excluded)||(profile.supportSearch?b.discovery.score-a.discovery.score:0)||a.decision.tier-b.decision.tier||Number(a.decision.audience_check)-Number(b.decision.audience_check)||period(a)-period(b)||b.discovery.score-a.discovery.score||condition(a)-condition(b)||b.relevance-a.relevance||(a.display.end||'9999-12-31').localeCompare(b.display.end||'9999-12-31')||String(b.item.last_checked_at||'').localeCompare(String(a.item.last_checked_at||''))||a.item.id.localeCompare(b.item.id);
  });
 }
 function decision(projected,shown,match,profile){
  const trusted=(projected.eligibility?.conditions||[]).filter(c=>c.status==='verified'&&['specified','no_restriction'].includes(c.presence)&&c.evidence?.location&&root.MunongsaSupport.safeUrl(c.evidence.url)&&(c.evidence.quote||c.evidence.fact_confirmed===true));
  const ids=new Set(trusted.filter(c=>['residence','business_location'].includes(c.kind)).map(c=>c.condition_id));
  function regional(node){
   if(!node)return null;if(node.condition_id)return ids.has(node.condition_id)?node:null;
   const children=(node.children||[]).map(regional),kept=children.filter(Boolean);if(!kept.length)return null;
   if(node.op==='OR'&&children.some(n=>!n))return {op:'UNKNOWN',children:[]};
   return {...node,children:kept};
  }
  const logic=regional(projected.eligibility?.logic);
  const region=shown.geographic_scope==='nationwide_verified'&&shown.verified_facts_at?'match':logic?root.MunongsaSupport.evaluate({...projected,eligibility:{conditions:trusted.filter(c=>ids.has(c.condition_id)),logic}},profile).conditionStatus:'check';
  const audience=profile.farmingSituation==='preparing'&&/수출/.test(shown.target||'')&&(shown.verified_facts_at||shown.evidence?.target?.url===shown.url);
  let category,label,tier;
  if(match.conditionStatus==='mismatch'){category='C';label='명확한 조건 불일치';tier=4;}
  else if(audience){category='D';label='조건 정보 부족';tier=3;}
  else if(region==='match'){
   if(projected.eligibility_complete===true&&match.conditionStatus==='match'){category='A';label='확인된 조건 일치';tier=0;}
   else{category='B';label='추가 자격 확인 필요';tier=1;}
  }else if(trusted.length){category='B';label='지역 확인 필요';tier=2;}
  else{category='D';label='조건 정보 부족';tier=3;}
  return {category,label,tier,region_state:region,audience_check:!!audience,excluded:category==='C',final_application_eligibility_confirmed:false};
 }
 root.MunongsaPersonalization={project,reasons,support,sourceConditions,sourceFacts,decision,discovery};
})(globalThis);
