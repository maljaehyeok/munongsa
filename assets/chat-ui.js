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
  const contextLine=text('p','','chat-context');contextLine.hidden=true;byId('chatQuestion').closest('.chat-composer-inner').prepend(contextLine);
  function updateContext(value){
    conversation=value||{};
    const labels=[conversation.region&&conversation.region+' 거주',conversation.farm_region&&'영농지역 '+conversation.farm_region,conversation.age!==undefined&&conversation.age+'세',conversation.planned===true&&'영농 시작 예정',conversation.farming_years!==undefined&&'영농 '+conversation.farming_years+'년',conversation.facility_sqm!==undefined&&'시설 '+conversation.facility_sqm+'㎡',conversation.crop&&'관심 작물 '+conversation.crop,
      conversation.farm_registered==='no'?'경영체 미등록':conversation.farm_registered==='yes'?'경영체 등록':null].filter(Boolean);
    contextLine.textContent=labels.length?'이번 대화 참고 · '+labels.join(' · '):'';contextLine.hidden=!labels.length;
  }
  function requestQuestion(question){return Object.keys(conversation).length?'[무농사 대화 참고]\n'+JSON.stringify(conversation)+'\n[질문]\n'+question:question;}
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
    return data&&validContext&&(data.suggestions===undefined||(strings(data.suggestions)&&data.suggestions.length<=3))&&data.mode==='local'&&['answered','needs_verification','no_evidence'].includes(data.status)
      &&str(data.answer)&&data.answer.length<=100000&&Array.isArray(data.programs)&&data.programs.length<=3
      &&Array.isArray(data.sources)&&data.sources.length<=100
      &&data.sources.every(s=>s&&str(s.url)&&str(s.location)&&str(s.checked_at))
      &&data.programs.every(p=>p&&str(p.name)&&str(p.source_url)&&str(p.checked_at)
        &&strings(p.required_conditions)&&strings(p.additional_checks)&&str(p.evidence_level)&&str(p.evidence_note)
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
  function message(label,value,kind){const node=text('article','','chat-message chat-message-'+kind);node.append(text('p',label,'chat-message-label'),text('p',value));history.append(node);return node;}
  byId('openChat').addEventListener('click',event=>{opener=event.currentTarget;dialog.showModal();document.documentElement.classList.add('chat-ui-open');input.focus({preventScroll:true});resizeInput();});
  byId('closeChat').addEventListener('click',()=>dialog.close());
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
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(pending||!localPage)return;const question=input.value.trim();
    if(!question||input.value.length>1000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(question)){input.setCustomValidity('질문을 1~1,000자로 입력하고 사용할 수 없는 특수문자는 지워주세요.');input.reportValidity();return;}
    showConversation(true);byId('chatFormStatus').textContent='';message('내 질문',question,'user');
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
      renderAnswer(status,data);updateContext(data.conversation);input.value='';
    }catch(error){
      const value=error.name==='AbortError'?'응답 대기 시간이 초과됐어요. 잠시 후 다시 보내주세요.':error instanceof Error&&error.name==='Error'?error.message:'서버에 연결하지 못했어요. 잠시 후 다시 보내주세요.';
      status.className='chat-message chat-message-error';status.replaceChildren(text('p','다시 시도해 주세요','chat-message-label'),text('p',value),text('p','작성한 질문은 입력창에 그대로 남아 있어요.'));
    }finally{clearTimeout(timer);pending=false;status.removeAttribute('role');sync();if(dialog.open){input.focus({preventScroll:true});status.scrollIntoView({block:'start',behavior:'instant'});}}
  });
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
