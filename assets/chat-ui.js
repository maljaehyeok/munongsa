/* Same-origin consultation UI. Rendering only; no profile uploads or eligibility rules. */
(function(){
  'use strict';
  const byId=id=>document.getElementById(id),dialog=byId('supportChat');
  if(!dialog||!byId('chatConversation'))return;
  const input=byId('chatQuestion'),form=byId('chatForm'),history=byId('chatHistory'),body=byId('chatBody');
  const productionPage=location.protocol==='https:'&&location.hostname==='munongsa.duckdns.org';
  const localPage=productionPage||(location.protocol==='http:'&&['localhost','127.0.0.1'].includes(location.hostname));
  const endpoint=productionPage?'/api/chat':'http://127.0.0.1:8765/api/chat';
  const officialHosts=new Set(['www.buan.go.kr','www.gochang.go.kr','www.rda.go.kr','www.jeonbuk.go.kr','www.oads.or.kr','global.at.or.kr','www.jeonju.go.kr','www.jinan.go.kr','www.imsil.go.kr','www.sunchang.go.kr','www.gunsan.go.kr','www.bizinfo.go.kr','bizinfo.go.kr','www.mafra.go.kr','www.koat.or.kr','www.gimje.go.kr','agriacademy.jeonbuk.go.kr']);
  let opener=null,pending=false,conversation={},stateRevision=0,resetting=false;
  const state=globalThis.MunongsaFarmProfile;
  const purposes=[['','분야 제한 없음'],['startup','창업·영농 시작'],['facility','시설 설치·개선'],['machinery','농기계 구입'],['education','농업 교육'],['fertilizer','비료·토양'],['export','수출 지원'],['insurance','보험·재해'],['finance','금융·운영 자금'],['grant','보조금 탐색']];
  let financeState=null,lastNext=null,lastDiscovery=false;
  const selectionQuestion='선택한 조건으로 지원사업을 찾아주세요.';
  // Reuse the API's bounded conversation fields; no separate profile or engine.
  const areas=['전주','부안','고창','안산','김제','군산','익산','정읍','남원','완주','진안','무주','장수','임실','순창','파주','포항','부산','서울','전북','전남','경북','경남','경기','충남','충북','강원','제주','인천','대전','대구','광주','울산','세종'];
  const crops=globalThis.MunongsaCropDirectory?.entries.map(e=>e.name)||[];
  const fields=[
    {key:'farm_region',label:'영농지·예정지',hint:'농사짓는 곳 또는 시작할 곳',options:areas},
    {key:'region',label:'현재 거주지',hint:'지금 살고 있는 곳',options:areas},
    {key:'applicant',label:'신청자 유형',options:[['individual_farmer','개인 농업인'],['group','단체·모임'],['agricultural_corporation','농업법인'],['business','사업체']]},
    {key:'farm_registered',label:'농업경영체 등록',options:[['yes','등록'],['no','미등록']]},
    {key:'crop',label:'영농 작물 (직접 알려준 조건)',options:crops},
    {key:'planned',label:'영농 시작 상태',options:[['true','시작 예정'],['false','이미 시작']]},
    {key:'age',label:'나이 (세)',min:0,max:120,step:1},
    {key:'cultivating',label:'선택한 작물을 실제 재배하나요?',options:[['true','현재 재배'],['false','아직 재배하지 않음']]},
    {key:'group_size',label:'단체 구성원 수 (명)',min:1,max:100000,step:1},
    {key:'farming_years',label:'영농 경력 (년)',min:0,max:100,step:0.01},
    {key:'facility_sqm',label:'시설면적 (㎡)',min:0,max:100000000,step:0.0001}
  ];
  let editor=null,editorOpener=null;
  const contextLine=document.createElement('details');contextLine.className='chat-context';contextLine.id='chatSettings';contextLine.hidden=true;body.prepend(contextLine);
  function settingsButtonState(){for(const b of dialog.querySelectorAll('.chat-header-condition')){const active=!!editor?.isConnected||contextLine.open;b.textContent=active?'설정 닫기':'조건 설정';b.setAttribute('aria-expanded',String(active));b.setAttribute('aria-controls','chatSettings');}}
  contextLine.addEventListener('toggle',settingsButtonState);
  function conditionValues(heading,rows){const panel=text('section','','chat-condition-summary');panel.append(text('h3',heading));const dl=document.createElement('dl');for(const [label,value]of rows){const row=document.createElement('div');row.append(text('dt',label),text('dd',value===undefined||value===''?'설정 안 함':String(value)));dl.append(row);}panel.append(dl);return panel;}
  function updateContext(value,share=true){
    const factKey=c=>JSON.stringify([...fields.map(f=>f.key),'age_basis','group_min','search_scope','search_crop','search_mode','search_purpose','search_period','search_limit'].map(k=>[k,c?.[k]??null]));
    if(factKey(conversation)!==factKey(value)){
      stateRevision++;lastNext=null;lastDiscovery=false;
      for(const result of history.querySelectorAll('.chat-result-message'))if(!result.dataset.profileStale){
        result.dataset.profileStale='true';result.prepend(text('p','영농 조건 또는 검색 조건이 변경됐어요. 이 카드는 변경 전 결과입니다.','chat-condition-note'));
      }
    }
    conversation=value||{};
    if(share)globalThis.MunongsaFarmProfile?.apply(conversation);
    const labels=fields.map(f=>{
      const value=conversation[f.key],option=f.options?.find(v=>String(Array.isArray(v)?v[0]:v)===String(value));
      return [{crop:'영농 작물',farm_registered:'경영체 등록',planned:'시작 상태'}[f.key]||f.label,value===undefined?undefined:(Array.isArray(option)?option[1]:option||value)+(f.key==='group_size'&&conversation.group_min?' 이상':'')];
    });
    const money=globalThis.MunongsaFarmProfile?.money||{};
    for(const [key,label]of Object.entries({own:'보유 자금',loan:'희망 대출금',project:'필요 사업비',required:'필요 자금'}))if(money[key]!==undefined)labels.push([label,MunongsaAmounts.wonText(money[key])]);
    contextLine.replaceChildren(text('summary','내 영농정보와 검색 조건 확인'));
    const values=conditionValues('실제 영농정보',labels.slice(0,6));
    const extra=document.createElement('details');extra.append(text('summary','나이·경력·자금 등 추가 정보'),conditionValues('추가 영농정보',labels.slice(6)));values.append(extra,conditionButton('영농정보 입력·수정',()=>openConditions([],'profile')));
    const search=conditionValues('지원사업 검색 조건',[
      ['이번 검색 지역',conversation.search_scope||'지역 제한 없음'],['관심 작물',conversation.search_crop||'작물 제한 없음'],['지원 분야',purposes.find(p=>p[0]===conversation.search_purpose)?.[1]||'분야 제한 없음'],['공고 범위',conversation.search_period==='past'?'기재기간 경과':conversation.search_period==='current'?'기재기간 남음 · 접수 별도 확인':'현재 목록 · 기간 미확인 포함'],['요청 개수',conversation.search_limit?conversation.search_limit+'개까지':'기본 · 3건씩 보기']]);
    search.append(text('p','검색 조건은 실제 거주지·영농지·재배 사실을 바꾸지 않아요.','chat-condition-note'),conditionButton('검색 조건 수정',()=>openConditions()),conditionButton('현재 검색 조건으로 다시 찾기',()=>currentSearch(),'primary'));
    const resets=document.createElement('details');resets.append(text('summary','초기화 범위 선택'),text('p','검색만 비우면 영농 조건은 유지해요. 새 대화는 영농 조건을 유지하고 검색·공고 참조를 지워요.','chat-condition-note'),conditionButton('검색 조건 초기화',()=>resetLocal('search')),conditionButton('영농 프로필 초기화',()=>resetLocal('profile')));
    const all=conditionButton('모두 초기화',()=>{if(all.dataset.confirm==='yes'){resetLocal('all');return;}all.dataset.confirm='yes';all.textContent='영농 조건·검색·상담 모두 지우기 (확인)';});resets.append(all);
    const panels=text('div','','chat-condition-panels');panels.append(values,search);contextLine.append(panels,resets);contextLine.hidden=false;settingsButtonState();
  }
  function searchLabel(c){return [c.search_scope||'지역 제한 없음',c.search_crop||'작물 제한 없음',purposes.find(p=>p[0]===c.search_purpose)?.[1]||'분야 제한 없음',c.search_period==='past'?'기재기간 경과':c.search_period==='current'?'기재기간 남음 · 접수 별도 확인':'현재 목록 · 기간 미확인 포함',c.search_limit?c.search_limit+'개까지':'3건씩 보기'].join(' · ');}
  function closeEditor(restoreFocus=false){if(editor?.isConnected)editor.remove();editor=null;dialog.classList.remove('chat-editing');settingsButtonState();if(restoreFocus)(editorOpener?.isConnected?editorOpener:dialog.querySelector('.chat-header-condition')||input).focus({preventScroll:true});}
  function editorHeading(title,note){const row=text('div','','chat-editor-heading');const heading=text('h3',title);heading.tabIndex=-1;row.append(heading,conditionButton('설정 닫기',()=>closeEditor(true)));editor.append(row,text('p',note));contextLine.open=false;settingsButtonState();requestAnimationFrame(()=>{if(editor?.isConnected)heading.focus({preventScroll:true});});}
  function resetLocal(scope,dom=true){
    const next=state.transition(conversation,scope);
    if(dom&&(scope==='profile'||scope==='all')){resetting=true;byId('resetFilters').click();resetting=false;}
    if(scope==='search'){
      const field=byId('supportSearch');if(field){field.value='';field.dispatchEvent(new Event('input',{bubbles:true}));}
      globalThis.MunongsaCultivation?.resetSelection();if(typeof selectedCropName!=='undefined')selectedCropName='';
      if(window.history.state?.crop&&typeof navigationFromUrl==='function'){const nav=navigationFromUrl();nav.crop='';window.history.replaceState({...window.history.state,crop:''},'',navigationUrl(nav));}
    }
    closeEditor();lastNext=null;lastDiscovery=false;financeState=null;stateRevision++;
    if(scope==='all')history.replaceChildren();
    updateContext(next,false);showConversation(true);
    byId('chatFormStatus').textContent=scope==='search'?'검색 조건을 비웠어요. 실제 영농 조건은 유지합니다.':scope==='profile'?'실제 영농 조건을 비웠어요. 임시 검색은 별도로 유지합니다.':scope==='conversation'?'상담·검색 참조를 지웠어요. 실제 영농 조건은 유지합니다.':'영농 조건·검색·상담을 모두 비웠어요.';sync();
  }
  function currentSearch(){if(pending)return;updateContext({...conversation,search_action:'current'},false);closeEditor();sendQuestion('현재 검색 조건으로 다시 검색');}
  function openSearch(){
    if(pending)return;editorOpener=document.activeElement;closeEditor();pullProfile();
    editor=text('section','','chat-message chat-message-answer chat-condition-editor');editor.setAttribute('aria-label','검색 조건 수정');dialog.classList.add('chat-editing');
    editorHeading('지원사업 검색 조건','선택 안 함은 이번 검색의 제한 해제입니다. 실제 영농정보는 바뀌지 않으며 적용 전에는 기존 검색 조건을 유지해요.');
    const draft=document.createElement('form'),grid=text('div','','chat-condition-grid'),controls=new Map();
    const places=state?MunongsaInputUX.places().map(p=>[[p.region,p.district].filter(Boolean).join(' '),p.text]):areas;
    for(const [key,label,options] of [['search_scope','탐색 지역',[["전국","전국 탐색"],...places]],['search_crop','관심 작물',crops],['search_purpose','지원 분야',purposes.filter(p=>p[0])],['search_period','기간 필터',[['current','기재기간이 남은 공고 · 접수 별도 확인'],['past','기재기간 경과 공고']]],['search_limit','결과 개수',[[5,'5개까지'],[7,'7개까지'],[10,'10개까지']]]]){
      const row=text('label','','chat-condition-field');row.append(text('span',label));const select=document.createElement('select');select.dataset.searchCondition=key;select.name=key;const blank=text('option',key==='search_limit'?'기본 · 3건씩':'선택 안 함 · 제한 해제');blank.value='';select.append(blank);
      for(const v of options){const option=text('option',Array.isArray(v)?v[1]:v);option.value=String(Array.isArray(v)?v[0]:v);select.append(option);}
      const initial=conversation[key]??'';if(initial&&!Array.from(select.options).some(o=>o.value===String(initial))){const o=text('option',String(initial));o.value=initial;select.append(o);}select.value=String(initial);controls.set(key,select);row.append(select);grid.append(row);
    }
    const note=text('p','','chat-condition-note');note.setAttribute('role','status');const actions=text('div','','chat-condition-actions'),apply=text('button','검색 조건 적용·찾기');apply.type='submit';
    actions.append(apply,conditionButton('변경 없이 현재 검색',currentSearch),conditionButton('영농 조건에서 가져오기',()=>{controls.get('search_scope').value=conversation.farm_region||conversation.region||'';controls.get('search_crop').value=conversation.crop||'';note.textContent='영농 조건을 입력칸에 가져왔어요. 적용하면 검색에 사용합니다.';}),conditionButton('입력칸 비우기',()=>{controls.forEach(c=>c.value='');note.textContent='초안만 비웠어요. 적용하면 과거 검색 제한도 모두 해제합니다. 취소하면 현재 조건이 유지돼요.';}),conditionButton('취소·닫기',()=>{closeEditor();input.focus();}));
    draft.append(grid,note,actions);editor.append(draft);history.append(editor);showConversation(true);sync();editor.scrollIntoView({block:'start'});
    draft.addEventListener('submit',event=>{event.preventDefault();if(pending)return;const values={};controls.forEach((control,key)=>{if(control.value)values[key]=key==='search_limit'?Number(control.value):control.value;});updateContext(state.transition(conversation,'replace',values),false);closeEditor();sendQuestion('선택한 검색 조건으로 찾아줘');});
  }
  function requestQuestion(question){return Object.keys(conversation).length?'[무농사 대화 참고]\n'+JSON.stringify(conversation)+'\n[질문]\n'+question:question;}
  function conditionButton(label,fn,kind='secondary'){const b=text('button',label,'chat-action chat-action-'+kind);b.type='button';b.addEventListener('click',fn);return b;}
  function openConditions(missing=[],mode='search'){
    if(mode==='search'){openSearch();return;}
    if(pending)return;
    editorOpener=document.activeElement;closeEditor();pullProfile();dialog.classList.add('chat-editing');
    editor=text('section','','chat-message chat-message-answer chat-condition-editor');editor.setAttribute('aria-label','내 조건 선택');
    editorHeading('실제 영농정보 입력·수정','직접 알려준 영농 사실입니다. 비운 항목은 적용할 때 해제돼요. 관심 지역·작물만 바꾸려면 검색 조건을 수정하세요.');
    const form=document.createElement('form');form.className='chat-condition-form';
    const core=text('div','','chat-condition-grid'),extra=document.createElement('details');extra.className='chat-condition-extra';
    extra.append(text('summary','나이·경력·인원·시설면적 더 선택'));const advanced=text('div','','chat-condition-grid'),controls=new Map();
    fields.forEach((f,i)=>{
      const label=text('label','','chat-condition-field');label.append(text('span',f.label));
      const control=document.createElement(f.options?'select':'input');control.name=f.key;control.dataset.condition=f.key;
      if(f.options){const blank=text('option','선택 안 함');blank.value='';control.append(blank);
        const choices=['region','farm_region'].includes(f.key)&&globalThis.MunongsaInputUX?.places?MunongsaInputUX.places().map(p=>[[p.region,p.district].filter(Boolean).join(' '),p.text]):f.options;
        choices.forEach(v=>{const option=text('option',Array.isArray(v)?v[1]:v);option.value=Array.isArray(v)?v[0]:v;control.append(option);});
        if(conversation[f.key]&&!Array.from(control.options).some(o=>o.value===String(conversation[f.key]))){const current=text('option',String(conversation[f.key]));current.value=String(conversation[f.key]);control.append(current);}
      }else{control.type='number';control.min=f.min;control.max=f.max;control.step=f.step;control.inputMode=f.step===1?'numeric':'decimal';control.placeholder='선택 입력';}
      control.value=conversation[f.key]===undefined?'':String(conversation[f.key]);
      if(f.key==='group_size'&&conversation.group_min)label.append(text('small','앞서 알려주신 값은 최소 인원이에요. 수정하면 정확한 인원으로 비교해요.'));
      controls.set(f.key,{control,initial:control.value});label.append(control);(i<6?core:advanced).append(label);
      if(f.hint)label.append(text('small',f.hint));
      if(i>=6&&(conversation[f.key]!==undefined||missing.includes(f.key)))extra.open=true;
    });
    extra.append(advanced);form.append(core,extra,text('p','나이·경력·거주지 선택만으로 공고 기준일의 자격이나 독립경영을 확정하지 않아요.','chat-condition-note'));
    const actions=text('div','','chat-condition-actions'),apply=text('button','영농 조건 적용·찾기');apply.type='submit';
    const cleared=text('p','','chat-condition-note');cleared.setAttribute('role','status');
    actions.append(apply,conditionButton('변경 없이 영농 조건으로 찾기',()=>{closeEditor();sendQuestion(selectionQuestion);}),conditionButton('입력칸 비우기',()=>{for(const {control} of controls.values())control.value='';cleared.textContent='초안만 비웠어요. 적용하면 실제 영농 조건을 해제하며, 취소하면 유지합니다.';}),conditionButton('취소·닫기',()=>{closeEditor();input.focus();}));form.append(cleared,actions);editor.append(form);history.append(editor);
    form.addEventListener('submit',event=>{
      event.preventDefault();if(pending||!form.reportValidity())return;
      const next=state.transition(conversation,'profile');
      for(const f of fields){const {control,initial}=controls.get(f.key),value=control.value;
        if(value===''){delete next[f.key];if(f.key==='age')delete next.age_basis;if(f.key==='group_size')delete next.group_min;continue;}
        next[f.key]=f.options?(['planned','cultivating'].includes(f.key)?value==='true':value):Number(value);
        if(f.key==='age'&&value!==initial)next.age_basis='unspecified';
        if(f.key==='group_size'&&value!==initial)next.group_min=false;
      }
      updateContext(next);closeEditor();sendQuestion(selectionQuestion,'수정한 영농 조건으로 검색');
    });
    showConversation(true);sync();editor.scrollIntoView({block:'start',behavior:'instant'});
    const first=fields.find(f=>missing.includes(f.key)&&conversation[f.key]===undefined)||fields[0];controls.get(first.key).control.focus({preventScroll:true});
  }
  function offerConditions(node,data){
    if(['help','condition_edit'].includes(data.kind))return;
    const map=[[/경영체/,'farm_registered'],[/거주|주소/,'region'],[/영농지역|농지/,'farm_region'],[/개인|단체·법인|신청자/,'applicant'],[/구성원|인원/,'group_size'],[/시설면적/,'facility_sqm'],[/나이|연령/,'age'],[/작물/,'crop']];
    const missing=[...new Set((data.followup_questions||[]).flatMap(q=>map.filter(([re,key])=>re.test(q)&&conversation[key]===undefined).map(([,key])=>key)))];
    if(!missing.length)return;
    const row=text('div','','chat-followups');row.append(conditionButton('필요한 영농 조건 입력',()=>openConditions(missing,'profile')));node.append(row);
  }
  function text(tag,value,className){const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;}
  function officialLink(value,label){
    try{
      const url=new URL(value);
      if(url.protocol!=='https:'||!officialHosts.has(url.hostname)||url.username||url.password||url.port)throw Error();
      const a=text('a',label+' ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';return a;
    }catch{return text('span','공식 출처 주소 확인 필요');}
  }
  function checked(value){
    const date=new Date(value);
    if(!Number.isFinite(date.getTime())||!/(Z|[+-]\d\d:\d\d)$/.test(value))return '확인일 미확인';
    return '확인 '+new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',dateStyle:'medium'}).format(date);
  }
  function dateText(value){
    if(!value||!/^\d{4}-\d{2}-\d{2}$/.test(value.date||''))return '날짜 미확인';
    return value.date+(value.time?' '+value.time+(value.timezone==='Asia/Seoul'?' (한국시간)':' (시간대 확인 필요)'):'');
  }
  function list(parent,heading,values){if(!values.length)return;parent.append(text('h5',heading));const ul=document.createElement('ul');values.forEach(v=>ul.append(text('li',v)));parent.append(ul);}
  function validResponse(data){
    const str=v=>typeof v==='string',strings=v=>Array.isArray(v)&&v.length<=100&&v.every(str);
    const context=data?.conversation;
    const validContext=context===undefined||(context&&typeof context==='object'&&!Array.isArray(context)
      &&Object.keys(context).every(k=>['region','crop','farm_registered','notice_ids','list_ids','list_versions','last_kind','farm_region','age','age_basis','applicant','group_size','group_min','farming_years','planned','cultivating','facility_sqm','casual_topic','conversation_topic','search_scope','search_query','search_offset','search_fingerprint','search_crop','search_mode','search_purpose','search_period','search_limit','search_action','empty_search','service','tech_crop','tech_topic','tech_resource'].includes(k))
      &&(context.search_mode===undefined||['focused','regional','profile','custom'].includes(context.search_mode))
      &&(context.search_period===undefined||['current','past'].includes(context.search_period))
      &&(context.search_action===undefined||['replace','current'].includes(context.search_action))
      &&(context.search_purpose===undefined||purposes.some(p=>p[0]===context.search_purpose))
      &&(context.search_limit===undefined||(Number.isInteger(context.search_limit)&&context.search_limit>=1&&context.search_limit<=10))
      &&(context.empty_search===undefined||(str(context.empty_search)&&/^[a-f0-9]{64}$/.test(context.empty_search)))
      &&(context.tech_resource===undefined||['general','pesticide'].includes(context.tech_resource))
      &&(['search_crop','tech_crop'].every(k=>context[k]===undefined||crops.includes(context[k])))
      &&(context.service===undefined||['support','finance','cultivation'].includes(context.service))
      &&(context.tech_topic===undefined||(Number.isInteger(context.tech_topic)&&context.tech_topic>=0&&context.tech_topic<6))
      &&(context.search_offset===undefined||(Number.isInteger(context.search_offset)&&context.search_offset>=3&&context.search_offset<=1998&&context.search_offset%3===0&&/^[a-f0-9]{64}$/.test(context.search_fingerprint||'')))
      &&(context.search_scope===undefined||(typeof context.search_scope==='string'&&context.search_scope.length<=24))
      &&(context.search_query===undefined||(typeof context.search_query==='string'&&context.search_query.length>0&&context.search_query.length<=300&&!/[<>\x00-\x1f]/.test(context.search_query)))
      &&(context.conversation_topic===undefined||(typeof context.conversation_topic==='string'&&context.conversation_topic.length<=80&&!/https?:\/\/|www\.|[\d<>\n\r@]|API[_ -]?KEY|sk-/i.test(context.conversation_topic)))
      &&(context.casual_topic===undefined||['meal','wellbeing','humor','scope'].includes(context.casual_topic))
      &&['age','group_size','farming_years','facility_sqm'].every(k=>context[k]===undefined||(typeof context[k]==='number'&&Number.isFinite(context[k])&&context[k]>=0&&context[k]<=100000000))
      &&['planned','cultivating','group_min'].every(k=>context[k]===undefined||typeof context[k]==='boolean')
      &&['region','crop','farm_registered','farm_region','age_basis','applicant'].every(k=>context[k]===undefined||(str(context[k])&&context[k].length<=24))
      &&(context.notice_ids===undefined||(strings(context.notice_ids)&&context.notice_ids.length<=3))
      &&(context.list_ids===undefined||(strings(context.list_ids)&&context.list_ids.length<=3&&context.list_ids.every(i=>/^NOTICE-[A-Za-z0-9_-]{1,70}$/.test(i))))
      &&(context.list_versions===undefined||(strings(context.list_versions)&&context.list_versions.length===(context.list_ids||[]).length&&context.list_versions.every(v=>/^[a-f0-9]{64}$/.test(v))))
      &&(context.last_kind===undefined||['help','results','clarify','context'].includes(context.last_kind)));
    const page=data?.catalogue_next;
    const validPage=page==null||(page&&str(page.query)&&page.query.length>0&&page.query.length<=300&&Number.isInteger(page.offset)&&page.offset>=3&&page.offset<=1998&&page.offset%3===0&&str(page.fingerprint)&&/^[a-f0-9]{64}$/.test(page.fingerprint));
    return data&&validPage&&validContext&&(data.followup_questions===undefined||(strings(data.followup_questions)&&data.followup_questions.length<=2))&&(data.suggestions===undefined||(strings(data.suggestions)&&data.suggestions.length<=3))&&data.mode==='local'&&['answered','needs_verification','no_evidence'].includes(data.status)
      &&str(data.answer)&&data.answer.length<=100000&&Array.isArray(data.programs)&&data.programs.length<=3
      &&Array.isArray(data.sources)&&data.sources.length<=100
      &&(data.reset_scope===undefined||['search','profile','conversation','all'].includes(data.reset_scope))
      &&data.sources.every(s=>s&&str(s.url)&&str(s.location)&&str(s.checked_at))
      &&data.programs.every(p=>p&&str(p.id)&&/^NOTICE-[A-Za-z0-9_-]+$/.test(p.id)&&str(p.name)&&str(p.source_url)&&str(p.checked_at)
        &&strings(p.required_conditions)&&strings(p.additional_checks)&&str(p.evidence_level)&&str(p.evidence_note)
        &&(p.comparison===undefined||(p.comparison&&strings(p.comparison.reasons)&&strings(p.comparison.checks)))
        &&(p.card===undefined||(p.card&&['related','check','mismatch','elapsed'].includes(p.card.group)&&str(p.card.label)&&p.card.facts
          &&['region','target','support'].every(k=>str(p.card.facts[k]))&&['funding','method','documents'].every(k=>strings(p.card.facts[k]))))
        &&p.application_period&&str(p.application_period.description));
  }
  function showConversation(show){byId('chatIntroduction').hidden=show;byId('chatConversation').hidden=false;dialog.classList.toggle('chat-has-conversation',show);}
  function resizeInput(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,144)+'px';}
  function sync(){
    input.setCustomValidity('');input.readOnly=pending;
    byId('submitChat').disabled=pending||!localPage||!input.value.trim();
    byId('submitChat').firstElementChild.textContent=pending?'확인 중…':'질문 보내기';
    byId('clearChat').disabled=pending||!history.childElementCount;
    document.querySelectorAll('[data-chat-example]').forEach(b=>b.disabled=pending);
    document.querySelectorAll('[data-chat-select]').forEach(b=>b.disabled=pending||!localPage);
    if(editor?.isConnected)editor.querySelectorAll('input,select,button').forEach(e=>e.disabled=pending||!localPage);
    history.setAttribute('aria-busy',String(pending));
    byId('chatCharacterCount').textContent=input.value.length.toLocaleString('ko-KR')+' / 1,000';resizeInput();
  }
  function readableAnswer(data){
    let value=data.answer;
    const heading='\n\n공식 출처·확인일:\n',start=value.indexOf(heading);
    // Sources are rendered from the validated structured response below each
    // answer, instead of repeating long raw URLs in the reading area.
    if(start>=0&&data.sources.length){const follow=value.indexOf('\n\n추가로 알려주세요:',start);value=value.slice(0,start)+(follow>=0?value.slice(follow):'');}
    value=value.replace(/^외부 AI에 자료를 보내지 않고 저장된 검증 근거를 정리했습니다\. 현재 접수 상태를 새로 조회한 답변은 아닙니다\.\s*/,'');
    const clean=v=>v.replace(/\s*\[\d+\]/g,'').trim();
    const conditions=new Set(data.programs.flatMap(p=>p.required_conditions).map(clean));
    value=value.replace(/함께 확인할 조건:\n((?:- [^\n]+\n?)+)/g,(whole,lines)=>{
      const values=lines.trim().split('\n').map(v=>clean(v.slice(2)));
      return values.length&&values.every(v=>conditions.has(v))?'':whole;
    });
    return value.trim();
  }
  function renderAnswer(node,data){
    if(data.programs.length&&data.programs.every(p=>p.card)){renderResults(node,data);return;}
    node.replaceChildren(text('p',data.programs.length?'무농사 · 공식 근거 안내':data.conversation?.conversation_topic&&data.understanding==='gpt'?'일반 농업 개념 · 개별 공고의 자격 판정과 별개':'무농사 · 상담 안내','chat-answer-label'));
    const answer=text('div','','chat-answer-text');
    readableAnswer(data).split(/\n{2,}/).filter(Boolean).forEach(paragraph=>answer.append(text('p',paragraph)));
    node.append(answer);node.className='chat-message chat-message-answer';
    if(data.kind==='cultivation'){
      node.append(conditionButton('질문한 작물·주제의 공식 자료 보기',()=>{
        const c=data.cultivation;
        if(c&&Number.isInteger(c.topic)&&c.topic>=0&&c.topic<6&&(c.crop==null||globalThis.MunongsaCropDirectory?.entries.some(e=>e.name===c.crop)))globalThis.MunongsaCultivation?.explore(c.crop,c.topic,c.resource==='pesticide'?'pesticide':null);
        dialog.close();if(typeof navigateTo==='function')navigateTo('cultivation');
        if(c?.resource==='pesticide')requestAnimationFrame(()=>document.querySelector('[data-cultivation-source="pesticide"]')?.scrollIntoView({block:'start',behavior:'instant'}));
      }));
    }
    if(['help','condition_edit'].includes(data.kind)){
      const actions=text('div','','chat-followups');
      actions.append(conditionButton('내 조건 선택·수정',()=>{if(!pending)openConditions();}));node.append(actions);
      if(data.kind==='condition_edit')actions.append(conditionButton('바뀐 조건으로 다시 비교',()=>{if(!pending)sendQuestion(selectionQuestion);}));
    }
    if(data.suggestions?.length){
      const choices=text('div','','chat-followups');
      data.suggestions.forEach(value=>{const b=text('button',value);b.type='button';b.addEventListener('click',()=>{if(pending)return;input.value=value;sync();input.focus();});choices.append(b);});node.append(choices);
    }
    if(!data.programs.length)return;
    const metadata=text('div','','chat-answer-metadata');
    data.programs.forEach(program=>{const row=text('div','','chat-source-row');row.append(officialLink(program.source_url,program.name),text('span',checked(program.checked_at)),text('span',program.evidence_level,'chat-evidence-level'));metadata.append(row);});node.append(metadata);
    node.append(text('p','신청 자격과 실제 접수 가능 여부는 확정할 수 없어요. 미확인 조건은 공식 원문이나 담당 기관에서 확인해 주세요.','chat-answer-caution'));
    const details=document.createElement('details');details.className='chat-evidence';details.append(text('summary','공식 근거 보기'));
    const content=text('div','','chat-evidence-content');
    data.programs.forEach(program=>{
      const section=text('section','','chat-program');section.append(text('h4',program.name),text('p',program.evidence_level+' · '+checked(program.checked_at)),text('p',program.evidence_note));
      section.append(text('h5','모집기간'),text('p',dateText(program.application_period.start)+' ~ '+dateText(program.application_period.end)),text('p',program.application_period.description));
      list(section,'필수조건·조건부 증빙',program.required_conditions);list(section,'추가 확인 사항',program.additional_checks);
      section.append(officialLink(program.source_url,'공식 공고 원문'));content.append(section);
    });
    if(data.sources.length){const sources=text('section','','chat-program');sources.append(text('h4','근거 위치'));data.sources.forEach(source=>{const row=text('div','','chat-source-location');row.append(officialLink(source.url,'공식 자료'),text('p',source.location),text('p',checked(source.checked_at)));sources.append(row);});content.append(sources);}
    details.append(content);node.append(details);
  }

  function renderResults(node,data){
    const personal=fields.some(f=>data.conversation?.[f.key]!==undefined);
    const basic=data.programs.every(p=>p.evidence_level==='공식 공고 기본 안내');
    const heading=text('header','','chat-result-heading');
    const countNote=data.catalogue_requested?'요청 최대 '+data.catalogue_requested+'건 · 관련 결과 '+data.catalogue_total+'건. ':'';
    const scopeNote=data.kind==='catalogue'?searchLabel(data.conversation||{})+' · 실제 영농 조건과 신청 자격은 별도 비교. ':'';
    heading.append(text('h3',data.catalogue_scope==='past'?'지난 공고 검색 결과':basic?'공식 공고 검색 결과':personal?'맞춤 추천 결과':'지원사업 검색 결과'),text('p',scopeNote+countNote+(data.catalogue_total??data.programs.length)+'건 중 '+(data.catalogue_start?data.catalogue_start+'~'+(data.catalogue_start+data.programs.length-1)+'번째':data.programs.length+'건')+'를 안내합니다. '+(basic?'기본 안내와 일부 조건 비교이며, 신청 가능 판정이 아닙니다.':'모집기간과 내 조건 비교를 함께 확인하세요.')));
    node.replaceChildren(heading);node.className='chat-message chat-message-answer chat-result-message';
    const linkedRows=new Map((typeof approvedRows==='function'?approvedRows():[]).map(r=>[r.item.id,r]));
    for(const program of data.programs){
      const card=text('section','','card notice-card chat-notice');card.dataset.noticeId=program.id;
      const linked=linkedRows.get(program.id),localRow=linked?.item.url===program.source_url?linked:null;
      const d=localRow?MunongsaSupportReview.presentation(localRow.item):MunongsaSupportReview.presentation({reference_application_dates:program.application_period,actual_reception_state:program.card.reception_state,known_closed:program.card.period_state==='elapsed'&&Boolean(program.card.lifecycle_label)});
      const status=text('div','','notice-status');
      const periodLabel=(localRow?null:program.card.lifecycle_label)||{window:'기재 모집기간 내',upcoming:'모집 예정',standing:'상시·예산 조건 확인',elapsed:'모집기간 경과',unknown:d.historical_elapsed?'최신 모집 확인 필요':'기간 확인 필요'}[d.state];
      status.append(text('span',periodLabel,'notice-chip '+d.tone),text('strong',d.headline,'deadline-badge '+d.tone));
      for(const chip of d.chips.filter(c=>/최종 접수|로그인 이후/.test(c.text)))status.append(text('span',chip.text,'notice-chip check'));
      const order=(data.conversation?.list_ids||[]).indexOf(program.id);
      card.append(text('h3',(order>=0?(order+1)+'. ':'')+program.name,'chat-notice-title'));
      if(program.card.institution!=='확인 필요')card.append(text('p',program.card.institution,'notice-institution'));
      if(typeof program.card.discovery_reason==='string'&&program.card.discovery_reason.length<=160&&program.card.discovery_reason)card.append(text('p','관련성 · '+program.card.discovery_reason+' · 자격 판정과 별개','match-note'));
      const comparison=text('section','','chat-condition-block');
      const mismatch=program.comparison?.decision?.excluded===true||program.comparison?.label==='조건 불일치';
      const comparisonLabel=program.comparison?.decision?.label||(program.guidance_only?'\uAE30\uBCF8 \uC548\uB0B4 \u00B7 \uC790\uACA9 \uD310\uB2E8 \uBCF4\uB958':mismatch?'확인된 조건 불일치':program.card.group==='elapsed'&&program.comparison?.label==='관련 가능성 있음'?'일부 조건 일치 · 모집기간 경과':program.comparison?.label||'추가 확인 필요');
      comparison.append(text('h4','내 조건과 비교'),text('strong',comparisonLabel,'condition-result '+(mismatch?'mismatch':program.card.group)));
      const reasons=program.comparison?.reasons||[],checks=program.comparison?.checks||[];
      const compared=localRow?MunongsaSupportReview.conditionViews(localRow.comparisonItem||localRow.item,localRow.match).filter(v=>v.evidenceUrl&&v.fact!=='확인 필요'):[];
      const mismatchFacts=mismatch&&!program.comparison?.hypothetical?compared.filter(v=>v.comparison==='mismatch').slice(0,2).map(v=>v.label+' 조건 불일치 · '+v.fact):[];
      const points=[...new Set([...(mismatchFacts.length?mismatchFacts:[reasons[0]]),checks[0]].filter(Boolean))];
      if(points.length){const ul=document.createElement('ul');points.forEach(v=>ul.append(text('li',v)));comparison.append(ul);}
      else comparison.append(text('p','지역 관련성만으로 전체 신청 자격을 판단하지 않습니다.'));
      if(d.state==='elapsed')comparison.append(text('p',localRow?'기재 기간이 지난 안내입니다. 현재 신청에 그대로 적용하지 말고 연장·재공고를 별도로 확인하세요.':program.application_period.description||'과거 공고의 금액·조건은 현재 신청에 적용할 수 없습니다. 연장·재공고는 별도 확인하세요.'));
      card.append(comparison,status);
      const facts=document.createElement('dl');facts.className='chat-notice-facts';
      function fact(label,value){const row=text('div','','notice-fact');row.append(text('dt',label,'notice-fact-label'),text('dd',MunongsaAmounts.format(Array.isArray(value)?value.join('\n'):value),'notice-fact-value'));facts.append(row);}
      const f=program.card.facts;
      fact('모집기간',d.periodText);fact('지원 내용',f.support);
      if(f.funding.length)fact('지원 규모·금액',f.funding);
      fact('대상 지역',f.region);fact('신청 대상',f.target);
      card.append(facts);
      const more=document.createElement('details');more.className='chat-application-details';more.append(text('summary','신청 방법·서류·세부 조건 확인'));const moreFacts=document.createElement('dl');moreFacts.className='chat-notice-facts';
      const start=facts.childElementCount;
      if(f.method.length)fact('신청 방법',f.method);
      if(f.documents.length)fact('필요 서류',f.documents);
      const required=program.required_conditions.map(v=>v.replace(/^(신청 대상|지원 지역):\s*/,''))
        .filter(v=>v!==f.target&&v!==f.region);
      if(required.length)fact('필요 조건',required);
      while(facts.children.length>start)moreFacts.append(facts.children[start]);more.append(moreFacts);
      const footer=text('footer','','notice-footer chat-notice-footer');
      const meta=text('div','','chat-notice-meta');meta.append(text('span',checked(program.checked_at)),text('span',program.evidence_level));
      footer.append(meta,officialLink(program.source_url,program.application_entry_url===program.source_url?(program.application_entry_kind==='login_unverified'?'공식 원문·신청 절차 · 로그인 필요':'공식 원문·신청 방법'):'공식 원문'));
      const detail=text('a','내 조건·신청 준비 보기 ↗');detail.href='#categories?'+new URLSearchParams({category:'support',kind:'supportPublic',key:program.id});
      detail.addEventListener('click',event=>{if(typeof navigateTo!=='function'||typeof publicSupport==='undefined'||!publicSupport?.notices?.some(p=>p.id===program.id))return;
        event.preventDefault();dialog.close();navigateTo('support','',{kind:'supportPublic',key:program.id});});footer.append(detail);card.append(footer);
      card.append(more);
      const details=document.createElement('details');details.className='chat-evidence';details.append(text('summary','공식 근거·미확인 조건 보기'));
      const content=text('div','','chat-evidence-content');content.append(text('p',program.evidence_note));
      list(content,'필수조건·조건별 근거',program.required_conditions);list(content,'추가 확인 사항',[...new Set([...program.additional_checks,...checks])]);
      for(const source of data.sources.filter(s=>s.url===program.source_url)){content.append(text('p',source.location+' · '+checked(source.checked_at)));}
      details.append(content);card.append(details);node.append(card);
    }
    if(data.catalogue_next){
      const next=data.catalogue_next,row=text('div','','chat-followups');
      row.append(conditionButton('다음 공고 더 보기',()=>{if(!pending)sendQuestion('[공식 공고 더 보기]\n'+JSON.stringify(next),'다음 공고 더 보기');}));node.append(row);
    }
    const questions=data.followup_questions||[];
    if(questions.length){const ask=text('section','','chat-next-question');ask.append(text('h4','더 정확히 찾아보려면'));questions.slice(0,2).forEach(q=>ask.append(text('p',q)));node.append(ask);}
    node.append(text('p','날짜 기준 모집기간 안내입니다. 실제 접수 가능 여부와 전체 신청 자격·지원금 승인은 공식 기관에서 확인하세요.','chat-answer-caution'));
    // Keep the complete grounded explanation available for calculations and
    // follow-up questions, without repeating it above every business card.
    const explanation=document.createElement('details');explanation.className='chat-full-explanation';explanation.append(text('summary','질문에 대한 상세 안내'));
    const paragraphs=text('div','','chat-answer-text');readableAnswer(data).split(/\n{2,}/).filter(Boolean).forEach(p=>paragraphs.append(text('p',p)));explanation.append(paragraphs);node.append(explanation);
  }
  function message(label,value,kind){const node=text('article','','chat-message chat-message-'+kind);node.append(text('p',label,'chat-message-label'),text('p',value));history.append(node);return node;}
  function pullProfile(){if(typeof readProfile==='function'&&globalThis.MunongsaFarmProfile){const p=readProfile();if(p.requiredFundsWon)MunongsaFarmProfile.money.required=p.requiredFundsWon;else delete MunongsaFarmProfile.money.required;const next=MunongsaFarmProfile.toConversation(p,conversation);if(conversation.list_ids&&!next.list_ids){lastNext=null;lastDiscovery=false;financeState=null;}updateContext(next,false);}}
  document.addEventListener('munongsa:profile-reset',()=>{if(!resetting)resetLocal('all',false);});
  document.addEventListener('munongsa:profile-change',()=>{if(!globalThis.MunongsaFarmProfile?.isApplying())pullProfile();});
  function openChat(event){pullProfile();opener=event.currentTarget;dialog.showModal();document.documentElement.classList.add('chat-ui-open');input.focus({preventScroll:true});resizeInput();}
  byId('openChat').addEventListener('click',openChat);
  document.querySelectorAll('[data-start-chat]').forEach(button=>button.addEventListener('click',openChat));
  document.querySelectorAll('[data-start-conditions]').forEach(button=>button.addEventListener('click',event=>{if(!localPage&&typeof navigateTo==='function'){navigateTo('support');return;}openChat(event);openConditions();}));
  byId('closeChat').addEventListener('click',()=>dialog.close());
  document.querySelectorAll('[data-chat-select]').forEach(button=>button.addEventListener('click',()=>{if(button.classList.contains('chat-header-condition')){if(editor?.isConnected){closeEditor(true);return;}contextLine.open=!contextLine.open;if(contextLine.open){contextLine.scrollIntoView({block:'start'});contextLine.querySelector('summary').focus();}}else openConditions();}));
  dialog.addEventListener('cancel',event=>{if(editor?.isConnected){event.preventDefault();closeEditor(true);}});
  dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
  dialog.addEventListener('close',()=>{closeEditor();document.documentElement.classList.remove('chat-ui-open');if(opener?.isConnected)opener.focus({preventScroll:true});});
  document.querySelectorAll('[data-chat-conditions]').forEach(button=>button.addEventListener('click',()=>{
    if(typeof navigationReady==='undefined'||!navigationReady||typeof navigateTo!=='function'){byId('chatFormStatus').textContent='지원사업 자료를 불러오고 있어요. 잠시 후 다시 눌러주세요.';return;}
    if(dialog.open)dialog.close();navigateTo('support');
    const toggle=byId('profileToggle');if(toggle?.getAttribute('aria-expanded')==='false')toggle.click();
    const field=byId('regionEntry')||byId('region');field?.focus({preventScroll:true});field?.scrollIntoView({block:'center',behavior:'auto'});
  }));
  document.querySelectorAll('[data-chat-example]').forEach(button=>button.addEventListener('click',()=>{input.value=button.dataset.chatExample;byId('chatFormStatus').textContent='질문 예시를 넣었어요. 내 상황에 맞게 바꾸고 보내세요.';sync();input.focus();}));
  input.addEventListener('input',()=>{byId('chatFormStatus').textContent='';sync();});
  input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&event.keyCode!==229){event.preventDefault();form.requestSubmit();}});
  form.addEventListener('submit',event=>{event.preventDefault();sendQuestion(input.value.trim());});
  async function sendQuestion(question,label=question){
    if(pending||!localPage)return;
    if(!question||question.length>1000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(question)){input.setCustomValidity('질문을 1~1,000자로 입력하고 사용할 수 없는 특수문자는 지워주세요.');input.reportValidity();return;}
    closeEditor();
    pullProfile();
    const another=/^(?:(?:조금\s*)?더\s*(?:보여줘|알려줘)|(?:다른|다음|나머지)\s*(?:관련\s*)?(?:지원)?사업(?:도)?\s*(?:보여줘|알려줘))[.!?\s]*$|그거\s*말고\s*다른\s*(?:거|건|사업)|아까\s*보여준\s*사업\s*말고\s*다른/.test(question);
    if(another&&lastNext)question='[공식 공고 더 보기]\n'+JSON.stringify(lastNext);
    else if(another&&lastDiscovery){message('무농사','같은 검색에서 추가로 보여드릴 관련 공고가 없어요. 앞서 본 공고의 공식 조건을 확인하거나, 시설·교육 등 찾는 목적을 바꿔 주세요. 입력한 영농 조건은 그대로 유지합니다.','answer');input.value='';sync();return;}
    showConversation(true);byId('chatFormStatus').textContent='';message('내 질문',label,'user');
    const status=message('무농사','생각 중...','status');status.setAttribute('role','status');
    pending=true;sync();status.scrollIntoView({block:'nearest',behavior:'instant'});
    const fundingFacts=globalThis.MunongsaFarmProfile?.fundingFacts(question)||[],funding=fundingFacts.length===1?fundingFacts[0]:null;
    if(fundingFacts.length>1){for(const fact of fundingFacts)MunongsaFarmProfile.money[fact.kind]=fact.won;message('자금 구분 확인',fundingFacts.map(f=>({own:'보유 자금',project:'필요 사업비',loan:'희망 대출금',required:'필요 자금'}[f.kind])+': '+MunongsaAmounts.wonText(f.won)).join(' · ')+'으로 각각 기억했어요. 지원금이나 대출금 확보액을 뜻하지 않아요.','answer');if(typeof draw==='function')draw();}
    if(funding){MunongsaFarmProfile.money[funding.kind]=funding.won;}
    if(funding?.kind==='required'&&globalThis.MunongsaInputUX?.setFunds(funding.won))message('입력 확인','필요 자금 '+MunongsaAmounts.wonText(funding.won)+'으로 반영했어요. 보유 자금이나 대출 승인액을 뜻하지 않아요.','answer');
    if(funding?.kind==='own')message('입력 확인','말씀하신 보유 자금은 '+MunongsaAmounts.wonText(funding.won)+'이에요. 필요 사업비·희망 대출금과 달라 자동으로 대입하지 않았어요.','answer');
    if(funding&&['loan','project'].includes(funding.kind))message('입력 확인',(funding.kind==='loan'?'희망 대출금: ':'필요 사업비: ')+MunongsaAmounts.wonText(funding.won)+'으로 따로 기억했어요. 필요 자금과 같은 금액으로 비교하려면 농업금융의 필요 자금에 입력해 주세요.','answer');
    const selectedSearch=/(?:선택|입력|설정|저장)(?:한|된)?\s*(?:영농\s*)?조건/.test(question)&&/검색|찾|탐색|지원\s*사업/.test(question);
    const namedFinance=(typeof financeMvp!=='undefined'?financeMvp?.products||[]:[]).some(p=>question.replace(/\s/g,'').includes(p.title.replace(/\([^)]*\)/g,'').replace(/\s/g,'')));
    const financeFollow=!namedFinance&&!conversation.search_action&&!selectedSearch&&(financeState?.active||conversation.service==='finance')&&!/지원사업|공고|보조금|초기화|지워|비워/.test(question)&&/그\s*(?:사업|제도)|신청|서류|접수|준비|등록|조건|빌리|이자|상환|첫\s*번째|두\s*번째|세\s*번째|^응[?？]?$|무슨\s*뜻|다시\s*설명/.test(question);
    const financeExcluded=/(?:융자|대출|금융)\s*(?:말고|제외|아닌)/.test(question);
    const finance=!conversation.search_action&&!financeExcluded&&(!!financeFollow||/대출|융자|정책자금|금융|농신보|농지연금|귀산촌|농업인행복|농업종합자금|농촌주택개량|식품가공원료|농촌융복합.*자금|사료.*자금|태양광.*자금|경영회생.*농지|농지\s*매매|(?:돈|자금)(?:이|이\s*더)?\s*부족|시설\s*(?:설치\s*)?자금/.test(question));
    const mixed=finance&&/지원사업|보조금/.test(question);
    if(!finance&&!/^(?:응|네|무슨|다시)/.test(question))financeState=null;
    const requestRevision=stateRevision,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:requestQuestion(finance&&!mixed&&question.length<=985?'농업금융 상담: '+question:question)}),signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer'});
      const errors={400:'질문을 1~1,000자로 다시 입력해 주세요.',403:'무농사 대표 주소에서 이용해 주세요.',413:'질문이 너무 길어요. 1,000자 이내로 줄여주세요.',415:'질문 전송 형식을 확인해야 해요.',429:'질문 요청이 많아요. 1분 정도 기다린 뒤 다시 보내주세요.',503:'공고 근거를 확인하지 못했거나 서버가 처리 중이에요. 잠시 후 다시 시도해 주세요.',504:'처리 시간이 초과됐어요. 질문을 짧게 바꿔 다시 보내주세요.'};
      if(!response.ok)throw new Error(errors[response.status]||'질문을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
      if(response.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')throw new Error('서버 응답 형식을 확인해야 해요.');
      const raw=await response.text();if(raw.length>262144)throw new Error('답변이 너무 커서 표시하지 않았어요. 질문을 나눠 보내주세요.');
      let data;try{data=JSON.parse(raw)}catch{throw new Error('서버 응답 형식을 확인해야 해요.');}
      if(!validResponse(data))throw new Error('답변의 공식 근거 항목을 확인해야 해요.');
      if(requestRevision!==stateRevision){if(status.isConnected)status.replaceChildren(text('p','응답을 기다리는 동안 조건이 변경되어 이전 조건의 답변은 표시하지 않았어요. 현재 조건으로 다시 검색해 주세요.'));return;}
      if(data.reset_scope){resetLocal(data.reset_scope);if(!status.isConnected)history.append(status);}
      updateContext(data.conversation);
      if(data.catalogue_total!==undefined){lastNext=data.catalogue_next||null;lastDiscovery=data.catalogue_total>0;}
      else if(data.kind==='condition_edit'||finance||data.kind==='cultivation'||data.conversation?.conversation_topic||!data.conversation?.list_ids?.length){lastNext=null;lastDiscovery=false;}
        if(data.reset_scope){renderAnswer(status,data);}
        else if(data.kind==='context'&&data.conversation?.conversation_topic){financeState=null;renderAnswer(status,data);offerConditions(status,data);}
        else if(finance&&!mixed&&!data.programs.length)await financeAnswer(status,question,false,financeFollow);else{if(data.programs.length)financeState=null;renderAnswer(status,data);offerConditions(status,data);if(mixed)await financeAnswer(status,question,true,false);}if(question!==selectionQuestion)input.value='';
    }catch(error){
      const value=error.name==='AbortError'?'응답 대기 시간이 초과됐어요. 잠시 후 다시 보내주세요.':error instanceof Error&&error.name==='Error'?error.message:'서버에 연결하지 못했어요. 잠시 후 다시 보내주세요.';
      status.className='chat-message chat-message-error';status.replaceChildren(text('p','다시 시도해 주세요','chat-message-label'),text('p',value),text('p',question===selectionQuestion?'선택한 조건은 유지돼요. 내 조건 선택·수정에서 다시 검색해 주세요.':'작성한 질문은 입력창에 그대로 남아 있어요.'));
    }finally{clearTimeout(timer);pending=false;status.removeAttribute('role');sync();if(dialog.open){input.focus({preventScroll:true});status.scrollIntoView({block:'start',behavior:'instant'});}}
  }
  async function financeAnswer(node,question,append=false,follow=false,offset=0){
    if(!append){node.replaceChildren(text('p','무농사 · 농업금융 안내','chat-answer-label'));node.className='chat-message chat-message-answer';}
    node.append(text('p','보조금은 공고별 지원이고, 정책자금·융자는 갚아야 하는 자금이에요. 입력한 영농 조건을 그대로 사용하되 대출 승인·중복 수혜·자부담 충당은 보장하지 않아요.'));
    if(/만약|가정|등록하면|이라면/.test(question))node.append(text('p','가정한 조건은 실제 프로필에 저장하지 않았어요. 아래 금융 후보는 현재 입력된 실제 조건 기준이며, 가정에 따른 대출 가능 여부를 확정한 결과가 아니에요.'));
    try{
      const r=await fetch('./data/finance-mvp.json',{cache:'no-cache'});if(!r.ok)throw Error('finance');const data=await r.json();
      const p=typeof readProfile==='function'?readProfile():{},search=follow?financeState?.query||question:question,terms=['귀농','청년','후계','농지','시설','농신보'].filter(t=>search.includes(t));
      const guide=/신청|서류|접수|준비/.test(question),ordinal=question.match(/(첫|두|세)\s*번째/),position=ordinal?{첫:0,두:1,세:2}[ordinal[1]]:null;
      const selected=follow?(position!==null?financeState?.ids[position]:financeState?.selected|| (financeState?.ids.length===1?financeState.ids[0]:null)):null;
      if(guide&&selected){const item=data.products.find(p=>p.id===selected);if(item){node.append(text('h3',item.title),text('p',MunongsaFinance.comparisonView(item,MunongsaFinance.compare(item,p)).scope));const content=text('section','','chat-finance-guide');content.innerHTML=MunongsaFinance.applicationGuide(item);node.append(content);const action=conditionButton('금융 상세정보에서 내 조건 확인',()=>{dialog.close();navigateTo('bank','',{kind:'financeMvp',key:item.id});});node.append(action);return;}}
      let found=MunongsaFinance.filter(data.products,MunongsaFinance.discoveryQuery(data.products,search),'all');
      found=MunongsaFinance.rank(found,p).filter(item=>MunongsaFinance.compare(item,p).state!=='mismatch');
      node.append(text('p',found.length?'공식 금융 안내에서 찾은 관련 제도예요. 일부 조건 비교이며 신청 가능 확정이 아니에요.':'현재 조건으로 안내할 관련 금융제도가 부족해요. 조건을 확인하거나 취급기관에 문의해 주세요.'));
      financeState={query:search,ids:found.slice(offset,offset+3).map(p=>p.id),active:!append,selected:null};
      if(guide)node.append(text('p','어느 금융제도인지 선택하면 해당 제도의 공식 신청 안내만 보여드릴게요.'));
      for(const item of found.slice(offset,offset+3)){const card=text('section','','chat-finance-result');card.append(text('h3',item.title),text('p',item.target));const link=conditionButton('공식 조건·신청 방법 확인',()=>{dialog.close();navigateTo('bank','',{kind:'financeMvp',key:item.id});});card.append(link,conditionButton('이 제도 신청 준비 안내',()=>{if(!pending){financeState.selected=item.id;sendQuestion('이 금융제도의 신청 방법과 서류를 알려주세요.');}}));node.append(card);}
      if(found.length>offset+3)node.append(conditionButton('다음 금융제도 보기',()=>{node.replaceChildren();financeAnswer(node,search,append,false,offset+3)}));
      const row=text('div','','chat-followups');row.append(conditionButton('농업금융 전체 보기',()=>{dialog.close();navigateTo('bank');}),conditionButton('같은 조건으로 지원사업 찾기',()=>{if(!pending)sendQuestion(selectionQuestion);}));node.append(row);
    }catch{node.append(text('p','금융자료를 불러오지 못했어요. 농업금융 메뉴에서 다시 확인해 주세요.'));}
  }
  byId('clearChat').addEventListener('click',()=>{if(pending)return;closeEditor();history.replaceChildren();updateContext(state.transition(conversation,'conversation'),false);financeState=null;lastNext=null;lastDiscovery=false;stateRevision++;pullProfile();showConversation(false);input.value='';byId('chatFormStatus').textContent='새 대화: 실제 영농 조건은 유지하고 검색·공고·이전 상담 참조는 지웠어요.';sync();body.scrollTop=0;input.focus({preventScroll:true});});
  document.querySelectorAll('[data-chat-select]').forEach(b=>{if(!b.classList.contains('chat-header-condition'))b.textContent='검색 조건 선택·수정';});
  if(!localPage){byId('chatAvailability').replaceChildren(text('span','질문 상담은 '),Object.assign(text('a','무농사 대표 주소 ↗'),{href:'https://munongsa.duckdns.org/'}),text('span','에서 이용할 수 있어요. 조건 검색은 이 화면에서도 이용할 수 있어요.'));byId('chatPrivacy').textContent='현재 주소에서는 질문을 전송하지 않아요. 대표 주소에서 상담을 이용해 주세요.';}
  const discovery=byId('supportDiscovery');
  document.querySelector('[data-scroll-services]').addEventListener('click',event=>{
    event.preventDefault();event.stopPropagation();byId('discoveryHeading').focus({preventScroll:true});
    discovery.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
  });
  if('IntersectionObserver' in window&&!matchMedia('(prefers-reduced-motion:reduce)').matches){
    const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){entry.target.classList.add('discovery-arrived');observer.unobserve(entry.target)}},{threshold:0.12});
    document.querySelectorAll('.discovery-card').forEach(card=>observer.observe(card));
  }
  sync();
})();
