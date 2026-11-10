/* Same-origin HTTPS/local API adapter. No keys, profile reads, storage or RAG logic. */
(function(){
  'use strict';
  const byId=id=>document.getElementById(id),dialog=byId('supportChat');
  if(!dialog)return;
  const input=byId('chatQuestion'),form=byId('chatForm'),history=byId('chatHistory');
  const productionPage=location.protocol==='https:'&&location.hostname==='munongsa.duckdns.org';
  const localPage=productionPage||(location.protocol==='http:'&&['localhost','127.0.0.1'].includes(location.hostname));
  const endpoint=productionPage?'/api/chat':'http://127.0.0.1:8765/api/chat',officialHosts=new Set(['www.buan.go.kr','www.gochang.go.kr','www.rda.go.kr','www.jeonbuk.go.kr','www.oads.or.kr','global.at.or.kr','www.jeonju.go.kr']);
  let opener=null,pending=false;
  function text(tag,value,className){const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;}
  function replace(id,value){byId(id).replaceChildren(text('p',value));}
  function resetEvidence(value){
    byId('chatAnswerMode').textContent=value;
    ['chatPrograms','chatSources','chatConditions','chatChecks'].forEach(id=>replace(id,'아직 표시할 검증 근거가 없어요.'));
  }
  function link(value,label){
    try{
      const url=new URL(value);
      if(url.protocol!=='https:'||!officialHosts.has(url.hostname)||url.username||url.password||url.port)throw Error();
      const a=text('a',label+' ↗');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';return a;
    }catch{return text('span','공식 출처 주소 확인 필요');}
  }
  function checked(value){
    const date=new Date(value);
    if(!Number.isFinite(date.getTime())||!/(Z|[+-]\d\d:\d\d)$/.test(value))return '확인일 미확인';
    return '확인일: '+new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',dateStyle:'medium',timeStyle:'short'}).format(date)+' (한국시간)';
  }
  function dateText(value){
    if(!value||!/^\d{4}-\d{2}-\d{2}$/.test(value.date||''))return '날짜 미확인';
    return value.date+(value.time?' '+value.time+(value.timezone==='Asia/Seoul'?' (한국시간)':' (시간대 확인 필요)'):'');
  }
  function list(parent,values){const ul=document.createElement('ul');values.forEach(v=>ul.append(text('li',v)));parent.append(ul);}
  function renderEvidence(data){
    dialog.querySelector('.chat-evidence').scrollTop=0;
    byId('chatAnswerMode').textContent='로컬 공식 근거 정리 · 외부 AI가 생성한 답변이 아니에요. 아래는 최근 완료된 답변의 근거예요.';
    ['chatPrograms','chatSources','chatConditions','chatChecks'].forEach(id=>byId(id).replaceChildren());
    if(!data.programs.length){resetEvidence('질문과 관련된 검증 근거를 찾지 못했어요. 사업명과 질문을 구체적으로 적어주세요.');return;}
    data.programs.forEach(program=>{
      const block=document.createElement('div');block.className='chat-program';
      block.append(text('strong',program.name),link(program.source_url,'공고 원문'),text('p',checked(program.checked_at)));
      block.append(text('strong',program.evidence_level),text('p',program.evidence_note));
      const period=program.application_period;
      block.append(text('p','신청기간: '+dateText(period.start)+' ~ '+dateText(period.end)),text('p',period.description));
      block.append(text('p','실제 접수 가능 여부는 별도 확인이 필요해요.'));
      byId('chatPrograms').append(block);
      for(const [id,values] of [['chatConditions',program.required_conditions],['chatChecks',program.additional_checks]]){
        const part=document.createElement('div');part.className='chat-program';part.append(text('strong',program.name));
        if(values.length)list(part,values);else part.append(text('p','확인된 추가 정보가 없어요.'));
        byId(id).append(part);
      }
    });
    data.sources.forEach(source=>{
      const part=document.createElement('div');part.className='chat-program';
      part.append(link(source.url,'공식 근거 보기'),text('p',source.location),text('p',checked(source.checked_at)));
      byId('chatSources').append(part);
    });
    if(!data.sources.length)replace('chatSources','표시할 검증 출처가 없어요.');
  }
  function validResponse(data){
    const str=v=>typeof v==='string',strings=v=>Array.isArray(v)&&v.length<=100&&v.every(str);
    return data&&data.mode==='local'&&['answered','needs_verification','no_evidence'].includes(data.status)
      &&str(data.answer)&&data.answer.length<=100000&&Array.isArray(data.programs)&&data.programs.length<=3
      &&Array.isArray(data.sources)&&data.sources.length<=100
      &&data.sources.every(s=>s&&str(s.url)&&str(s.location)&&str(s.checked_at))
      &&data.programs.every(p=>p&&str(p.name)&&str(p.source_url)&&str(p.checked_at)
        &&strings(p.required_conditions)&&strings(p.additional_checks)&&str(p.evidence_level)&&str(p.evidence_note)&&p.application_period&&str(p.application_period.description));
  }
  function sync(){
    input.setCustomValidity('');
    byId('submitChat').disabled=pending||!localPage||!input.value.trim();
    input.readOnly=pending;
    byId('submitChat').textContent=pending?'근거 확인 중…':'질문 보내기';
    byId('clearChat').disabled=pending||!history.childElementCount;
    document.querySelectorAll('[data-chat-example]').forEach(b=>b.disabled=pending);
    history.setAttribute('aria-busy',String(pending));
    byId('chatCharacterCount').textContent=input.value.length.toLocaleString('ko-KR')+' / 1,000';
  }
  byId('openChat').addEventListener('click',event=>{
    opener=event.currentTarget;dialog.showModal();document.documentElement.classList.add('chat-ui-open');
    byId('chatHeading').focus({preventScroll:true});
  });
  byId('closeChat').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{
    document.documentElement.classList.remove('chat-ui-open');
    if(opener?.isConnected)opener.focus({preventScroll:true});
  });
  document.querySelectorAll('[data-chat-example]').forEach(button=>button.addEventListener('click',()=>{
    input.value=button.textContent.trim();sync();input.focus();
  }));
  input.addEventListener('input',sync);
  input.addEventListener('keydown',event=>{
    if(event.key==='Enter'&&event.ctrlKey&&!event.isComposing){event.preventDefault();form.requestSubmit();}
  });
  function message(label,text,kind){
    const node=document.createElement('p'),name=document.createElement('strong'),body=document.createElement('span');
    node.className='chat-message chat-message-'+kind;name.textContent=label;body.textContent=text;
    node.append(name,body);history.append(node);return node;
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(pending||!localPage)return;const question=input.value.trim();
    if(!question||input.value.length>1000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(question)){
      input.setCustomValidity('질문을 1~1,000자로 입력하고 사용할 수 없는 특수문자는 지워주세요.');input.reportValidity();return;
    }
    message('내 질문',question,'user');
    const status=message('확인 중','승인된 공고에서 근거를 찾고 있어요.','status');
    byId('chatEmpty').hidden=true;pending=true;sync();resetEvidence('질문의 근거를 확인하고 있어요.');
    status.scrollIntoView({block:'nearest',behavior:'instant'});
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question}),signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error',referrerPolicy:'no-referrer'});
      const errors={400:'질문 형식을 확인하고 1~1,000자로 다시 입력해 주세요.',403:'무농사 대표 주소에서 이용해 주세요.',
        413:'질문이 너무 길어요. 1,000자 이내로 줄여주세요.',415:'질문 전송 형식을 확인해야 해요.',
        429:'질문 요청이 많아요. 1분 정도 기다린 뒤 다시 보내주세요.',
        503:'공고 근거를 검증하지 못했거나 서버가 처리 중이에요. 잠시 후 다시 시도해 주세요.',
        504:'답변 처리 시간이 초과됐어요. 질문을 짧게 바꿔 다시 보내주세요.'};
      if(!response.ok)throw new Error(errors[response.status]||'질문 서버가 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
      if(response.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')throw new Error('서버 응답 형식을 확인해야 해요.');
      const raw=await response.text();if(raw.length>262144)throw new Error('서버 응답이 너무 커서 표시하지 않았어요.');
      let data;try{data=JSON.parse(raw)}catch{throw new Error('서버 응답 형식을 확인해야 해요.')}
      if(!validResponse(data))throw new Error('서버 응답의 근거 항목을 확인해야 해요.');
      status.firstElementChild.textContent=data.status==='answered'?'공식 근거 정리 · 로컬':'확인 필요 · 로컬';
      status.lastElementChild.textContent=data.answer;
      status.classList.add('chat-message-answer');
      const note=text('small','외부 AI가 생성한 답변이 아니며, 전체 신청 자격·현재 접수 가능 여부를 확정하지 않아요.');status.append(note);
      renderEvidence(data);input.value='';
    }catch(error){
      const known=error instanceof Error&&error.name==='Error';
      status.firstElementChild.textContent='요청 안내';
      status.lastElementChild.textContent=error.name==='AbortError'?'응답을 기다리는 시간이 초과됐어요. 질문은 남겨두었으니 잠시 후 다시 시도해 주세요.':
        known?error.message:'질문 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요. 질문은 입력창에 남겨두었어요.';
      status.classList.add('chat-message-error');resetEvidence('이번 질문의 답변을 받지 못했어요. 입력창의 질문은 유지돼요.');
    }finally{
      clearTimeout(timer);pending=false;sync();
      if(dialog.open){input.focus({preventScroll:true});status.scrollIntoView({block:'start',behavior:'instant'});}
    }
  });
  byId('clearChat').addEventListener('click',()=>{
    history.replaceChildren();byId('chatEmpty').hidden=false;byId('clearChat').disabled=true;
    input.value='';resetEvidence('질문을 보내면 관련 공고와 확인된 근거를 표시해요.');sync();input.focus();
  });
  if(productionPage)byId('chatPrivacy').textContent='질문만 무농사 질문 서버로 보내요. 외부 AI에는 보내지 않아요. 대화는 새로고침하면 지워져요. 개인정보는 입력하지 마세요.';
  if(!localPage){
    byId('chatAvailability').replaceChildren(text('strong','챗봇은 대표 도메인에서 이용해 주세요.'),text('p','https://munongsa.duckdns.org/에서 이용할 수 있어요.'));
    byId('chatPrivacy').textContent='현재 화면에서는 질문을 전송하지 않아요. 개인정보는 입력하지 마세요.';
  }
  sync();
})();
