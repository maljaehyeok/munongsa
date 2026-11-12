/* Same-origin consultation UI. Rendering only; no profile uploads or eligibility rules. */
(function(){
  'use strict';
  const byId=id=>document.getElementById(id),dialog=byId('supportChat');
  if(!dialog||!byId('chatConversation'))return;
  const input=byId('chatQuestion'),form=byId('chatForm'),history=byId('chatHistory'),body=byId('chatBody');
  const productionPage=location.protocol==='https:'&&location.hostname==='munongsa.duckdns.org';
  const localPage=productionPage||(location.protocol==='http:'&&['localhost','127.0.0.1'].includes(location.hostname));
  const endpoint=productionPage?'/api/chat':'http://127.0.0.1:8765/api/chat';
  const officialHosts=new Set(['www.buan.go.kr','www.gochang.go.kr','www.rda.go.kr','www.jeonbuk.go.kr','www.oads.or.kr','global.at.or.kr','www.jeonju.go.kr']);
  let opener=null,pending=false,conversation={};
  const selectionQuestion='선택한 조건으로 지원사업을 찾아주세요.';
  // Reuse the API's bounded conversation fields; no separate profile or engine.
  const areas=['전주','부안','고창','파주','포항','부산','서울','전북','전남','경북','경남','경기','충남','충북','강원','제주'];
  const crops=['마늘','고추','배추','딸기','토마토','상추','감자','벼','쌀','사과','포도','콩','오이','버섯'];
  const fields=[
    {key:'region',label:'현재 거주지',options:areas},
    {key:'farm_region',label:'영농·영농 예정 지역',options:areas},
    {key:'applicant',label:'신청자 유형',options:[['individual_farmer','개인 농업인'],['group','단체·모임'],['agricultural_corporation','농업법인'],['business','사업체']]},
    {key:'farm_registered',label:'농업경영체 등록',options:[['yes','등록'],['no','미등록']]},
    {key:'crop',label:'관심·재배 작물',options:crops},
    {key:'planned',label:'영농 시작 상태',options:[['true','시작 예정'],['false','이미 시작']]},
    {key:'age',label:'나이 (세)',min:0,max:120,step:1},
    {key:'cultivating',label:'선택한 작물을 실제 재배하나요?',options:[['true','현재 재배'],['false','아직 재배하지 않음']]},
    {key:'group_size',label:'단체 구성원 수 (명)',min:1,max:100000,step:1},
    {key:'farming_years',label:'영농 경력 (년)',min:0,max:100,step:0.01},
    {key:'facility_sqm',label:'시설면적 (㎡)',min:0,max:100000000,step:0.0001}
  ];
  let editor=null;
  const contextLine=text('p','','chat-context');contextLine.hidden=true;byId('chatQuestion').closest('.chat-composer-inner').prepend(contextLine);
  function updateContext(value){
    conversation=value||{};
    const labels=fields.filter(f=>conversation[f.key]!==undefined).map(f=>{
      const value=conversation[f.key],option=f.options?.find(v=>String(Array.isArray(v)?v[0]:v)===String(value));
      return f.label+': '+(Array.isArray(option)?option[1]:option||value)+(f.key==='group_size'&&conversation.group_min?' 이상':'');
    });
    contextLine.textContent=labels.length?'이번 대화 참고 · '+labels.join(' · '):'';contextLine.hidden=!labels.length;
  }
  function requestQuestion(question){return Object.keys(conversation).length?'[무농사 대화 참고]\n'+JSON.stringify(conversation)+'\n[질문]\n'+question:question;}
  function conditionButton(label,fn){const b=text('button',label);b.type='button';b.addEventListener('click',fn);return b;}
  function openConditions(missing=[]){
    if(pending)return;
    if(editor?.isConnected)editor.remove();
    editor=text('section','','chat-message chat-message-answer chat-condition-editor');editor.setAttribute('aria-label','내 조건 선택');
    editor.append(text('h3','내 조건을 한 번에 선택해요'),text('p','알려주신 값은 채워 두었어요. 모르는 항목은 비워 두어도 검색할 수 있어요. 거주지와 영농지는 따로 선택해요.'));
    const form=document.createElement('form');form.className='chat-condition-form';
    const core=text('div','','chat-condition-grid'),extra=document.createElement('details');extra.className='chat-condition-extra';
    extra.append(text('summary','나이·경력·인원·시설면적 더 선택'));const advanced=text('div','','chat-condition-grid'),controls=new Map();
    fields.forEach((f,i)=>{
      const label=text('label','','chat-condition-field');label.append(text('span',f.label));
      const control=document.createElement(f.options?'select':'input');control.name=f.key;control.dataset.condition=f.key;
      if(f.options){const blank=text('option','잘 모르겠어요 / 건너뛰기');blank.value='';control.append(blank);
        f.options.forEach(v=>{const option=text('option',Array.isArray(v)?v[1]:v);option.value=Array.isArray(v)?v[0]:v;control.append(option);});
      }else{control.type='number';control.min=f.min;control.max=f.max;control.step=f.step;control.inputMode=f.step===1?'numeric':'decimal';control.placeholder='선택 입력';}
      control.value=conversation[f.key]===undefined?'':String(conversation[f.key]);
      if(f.key==='group_size'&&conversation.group_min)label.append(text('small','앞서 알려주신 값은 최소 인원이에요. 수정하면 정확한 인원으로 비교해요.'));
      controls.set(f.key,{control,initial:control.value});label.append(control);(i<6?core:advanced).append(label);
      if(i>=6&&(conversation[f.key]!==undefined||missing.includes(f.key)))extra.open=true;
    });
    extra.append(advanced);form.append(core,extra,text('p','나이·경력·거주지 선택만으로 공고 기준일의 자격이나 독립경영을 확정하지 않아요.','chat-condition-note'));
    const actions=text('div','','chat-condition-actions'),apply=text('button','선택한 조건으로 찾기');apply.type='submit';
    actions.append(apply,conditionButton('건너뛰고 검색',()=>{editor.remove();sendQuestion(selectionQuestion,'현재 알려진 조건으로 검색');}),conditionButton('닫기',()=>{editor.remove();input.focus();}));form.append(actions);editor.append(form);history.append(editor);
    form.addEventListener('submit',event=>{
      event.preventDefault();if(pending||!form.reportValidity())return;
      const next={...conversation};delete next.notice_ids;
      for(const f of fields){const {control,initial}=controls.get(f.key),value=control.value;
        if(value===''){delete next[f.key];if(f.key==='age')delete next.age_basis;if(f.key==='group_size')delete next.group_min;continue;}
        next[f.key]=f.options?(['planned','cultivating'].includes(f.key)?value==='true':value):Number(value);
        if(f.key==='age'&&value!==initial)next.age_basis='unspecified';
        if(f.key==='group_size'&&value!==initial)next.group_min=false;
      }
      updateContext(next);editor.remove();sendQuestion(selectionQuestion,'선택한 조건으로 검색');
    });
    showConversation(true);sync();editor.scrollIntoView({block:'start',behavior:'instant'});
    const first=fields.find(f=>missing.includes(f.key)&&conversation[f.key]===undefined)||fields[0];controls.get(first.key).control.focus({preventScroll:true});
  }
  function offerConditions(node,data){
    const map=[[/경영체/,'farm_registered'],[/거주|주소/,'region'],[/영농지역|농지/,'farm_region'],[/개인|단체·법인|신청자/,'applicant'],[/구성원|인원/,'group_size'],[/시설면적/,'facility_sqm'],[/나이|연령/,'age'],[/작물/,'crop']];
    const missing=[...new Set((data.followup_questions||[]).flatMap(q=>map.filter(([re,key])=>re.test(q)&&conversation[key]===undefined).map(([,key])=>key)))];
    if(!missing.length)return;
    const row=text('div','','chat-followups');row.append(conditionButton('필요한 조건 함께 선택',()=>openConditions(missing)));node.append(row);
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
      &&Object.keys(context).every(k=>['region','crop','farm_registered','notice_ids','farm_region','age','age_basis','applicant','group_size','group_min','farming_years','planned','cultivating','facility_sqm'].includes(k))
      &&['age','group_size','farming_years','facility_sqm'].every(k=>context[k]===undefined||(typeof context[k]==='number'&&Number.isFinite(context[k])&&context[k]>=0&&context[k]<=100000000))
      &&['planned','cultivating','group_min'].every(k=>context[k]===undefined||typeof context[k]==='boolean')
      &&['region','crop','farm_registered','farm_region','age_basis','applicant'].every(k=>context[k]===undefined||(str(context[k])&&context[k].length<=24))
      &&(context.notice_ids===undefined||(strings(context.notice_ids)&&context.notice_ids.length<=3)));
    return data&&validContext&&(data.followup_questions===undefined||(strings(data.followup_questions)&&data.followup_questions.length<=2))&&(data.suggestions===undefined||(strings(data.suggestions)&&data.suggestions.length<=3))&&data.mode==='local'&&['answered','needs_verification','no_evidence'].includes(data.status)
      &&str(data.answer)&&data.answer.length<=100000&&Array.isArray(data.programs)&&data.programs.length<=3
      &&Array.isArray(data.sources)&&data.sources.length<=100
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
    node.replaceChildren(text('p',data.programs.length?'무농사 · 공식 근거 안내':'무농사 · 상담 안내','chat-answer-label'));
    const answer=text('div','','chat-answer-text');
    readableAnswer(data).split(/\n{2,}/).filter(Boolean).forEach(paragraph=>answer.append(text('p',paragraph)));
    node.append(answer);node.className='chat-message chat-message-answer';
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
    const personal=Object.keys(data.conversation||{}).some(k=>!['notice_ids','region','crop'].includes(k));
    const heading=text('header','','chat-result-heading');
    heading.append(text('h3',personal?'맞춤 추천 결과':'지원사업 검색 결과'),text('p',data.programs.length+'건을 안내합니다. 모집기간과 내 조건 비교를 함께 확인하세요.'));
    node.replaceChildren(heading);node.className='chat-message chat-message-answer chat-result-message';
    for(const program of data.programs){
      const card=text('section','','card notice-card chat-notice');card.dataset.noticeId=program.id;
      const d=MunongsaSupportReview.presentation({reference_application_dates:program.application_period});
      const status=text('div','','notice-status');
      const periodLabel={window:'기재 모집기간 내',upcoming:'모집 예정',elapsed:'모집기간 경과',unknown:'기간 확인 필요'}[d.state];
      status.append(text('span',periodLabel,'notice-chip '+d.tone),text('strong',d.headline,'deadline-badge '+d.tone));
      card.append(status,text('h3',program.name,'chat-notice-title'));
      if(program.card.institution!=='확인 필요')card.append(text('p',program.card.institution,'notice-institution'));
      const comparison=text('section','','chat-condition-block');
      const mismatch=program.comparison?.label==='조건 불일치';
      const comparisonLabel=mismatch?'확인된 조건 불일치':program.card.group==='elapsed'&&program.comparison?.label==='관련 가능성 있음'?'일부 조건 일치 · 모집기간 경과':program.comparison?.label||'추가 확인 필요';
      comparison.append(text('h4','내 조건과 비교'),text('strong',comparisonLabel,'condition-result '+(mismatch?'mismatch':program.card.group)));
      const reasons=program.comparison?.reasons||[],checks=program.comparison?.checks||[];
      const points=[...new Set([...reasons,...checks])].slice(0,2);
      if(points.length){const ul=document.createElement('ul');points.forEach(v=>ul.append(text('li',v)));comparison.append(ul);}
      else comparison.append(text('p','지역 관련성만으로 전체 신청 자격을 판단하지 않습니다.'));
      if(program.card.group==='elapsed')comparison.append(text('p','기재된 모집기간이 지났습니다. 연장·재공고 여부는 별도 확인이 필요합니다.'));
      card.append(comparison);
      const facts=document.createElement('dl');facts.className='chat-notice-facts';
      function fact(label,value){const row=text('div','','notice-fact');row.append(text('dt',label,'notice-fact-label'),text('dd',Array.isArray(value)?value.join('\n'):value,'notice-fact-value'));facts.append(row);}
      const f=program.card.facts;
      fact('대상 지역',f.region);fact('신청 대상',f.target);fact('모집기간',d.periodText);fact('지원 내용',f.support);
      if(f.funding.length)fact('지원 규모·금액',f.funding);
      if(f.method.length)fact('신청 방법',f.method);
      if(f.documents.length)fact('필요 서류',f.documents);
      const required=program.required_conditions.map(v=>v.replace(/^(신청 대상|지원 지역):\s*/,''))
        .filter(v=>v!==f.target&&v!==f.region);
      if(required.length)fact('필요 조건',required);
      card.append(facts);
      const footer=text('footer','','notice-footer chat-notice-footer');
      const meta=text('div','','chat-notice-meta');meta.append(text('span',checked(program.checked_at)),text('span',program.evidence_level));
      footer.append(meta,officialLink(program.source_url,'공식 원문'));
      const detail=text('a','사이트 상세보기 ↗');detail.href='#categories?'+new URLSearchParams({category:'support',kind:'supportPublic',key:program.id});
      detail.addEventListener('click',event=>{if(typeof navigateTo!=='function'||typeof publicSupport==='undefined'||!publicSupport?.notices?.some(p=>p.id===program.id))return;
        event.preventDefault();dialog.close();navigateTo('support','',{kind:'supportPublic',key:program.id});});footer.append(detail);card.append(footer);
      const details=document.createElement('details');details.className='chat-evidence';details.append(text('summary','공식 근거 보기'));
      const content=text('div','','chat-evidence-content');content.append(text('p',program.evidence_note));
      list(content,'필수조건·조건별 근거',program.required_conditions);list(content,'추가 확인 사항',[...new Set([...program.additional_checks,...checks])]);
      for(const source of data.sources.filter(s=>s.url===program.source_url)){content.append(text('p',source.location+' · '+checked(source.checked_at)));}
      details.append(content);card.append(details);node.append(card);
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
  byId('openChat').addEventListener('click',event=>{opener=event.currentTarget;dialog.showModal();document.documentElement.classList.add('chat-ui-open');input.focus({preventScroll:true});resizeInput();});
  byId('closeChat').addEventListener('click',()=>dialog.close());
  document.querySelectorAll('[data-chat-select]').forEach(button=>button.addEventListener('click',()=>openConditions()));
  dialog.addEventListener('close',()=>{document.documentElement.classList.remove('chat-ui-open');if(opener?.isConnected)opener.focus({preventScroll:true});});
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
    if(editor?.isConnected)editor.remove();
    showConversation(true);byId('chatFormStatus').textContent='';message('내 질문',label,'user');
    const status=message('무농사','승인된 공고에서 공식 근거를 찾고 있어요.','status');status.setAttribute('role','status');
    pending=true;sync();status.scrollIntoView({block:'nearest',behavior:'instant'});
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:requestQuestion(question)}),signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer'});
      const errors={400:'질문을 1~1,000자로 다시 입력해 주세요.',403:'무농사 대표 주소에서 이용해 주세요.',413:'질문이 너무 길어요. 1,000자 이내로 줄여주세요.',415:'질문 전송 형식을 확인해야 해요.',429:'질문 요청이 많아요. 1분 정도 기다린 뒤 다시 보내주세요.',503:'공고 근거를 확인하지 못했거나 서버가 처리 중이에요. 잠시 후 다시 시도해 주세요.',504:'처리 시간이 초과됐어요. 질문을 짧게 바꿔 다시 보내주세요.'};
      if(!response.ok)throw new Error(errors[response.status]||'질문을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
      if(response.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')throw new Error('서버 응답 형식을 확인해야 해요.');
      const raw=await response.text();if(raw.length>262144)throw new Error('답변이 너무 커서 표시하지 않았어요. 질문을 나눠 보내주세요.');
      let data;try{data=JSON.parse(raw)}catch{throw new Error('서버 응답 형식을 확인해야 해요.');}
      if(!validResponse(data))throw new Error('답변의 공식 근거 항목을 확인해야 해요.');
      renderAnswer(status,data);updateContext(data.conversation);offerConditions(status,data);if(question!==selectionQuestion)input.value='';
    }catch(error){
      const value=error.name==='AbortError'?'응답 대기 시간이 초과됐어요. 잠시 후 다시 보내주세요.':error instanceof Error&&error.name==='Error'?error.message:'서버에 연결하지 못했어요. 잠시 후 다시 보내주세요.';
      status.className='chat-message chat-message-error';status.replaceChildren(text('p','다시 시도해 주세요','chat-message-label'),text('p',value),text('p',question===selectionQuestion?'선택한 조건은 유지돼요. 내 조건 선택·수정에서 다시 검색해 주세요.':'작성한 질문은 입력창에 그대로 남아 있어요.'));
    }finally{clearTimeout(timer);pending=false;status.removeAttribute('role');sync();if(dialog.open){input.focus({preventScroll:true});status.scrollIntoView({block:'start',behavior:'instant'});}}
  }
  byId('clearChat').addEventListener('click',()=>{if(pending)return;history.replaceChildren();updateContext({});showConversation(false);input.value='';byId('chatFormStatus').textContent='';sync();body.scrollTop=0;input.focus({preventScroll:true});});
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
