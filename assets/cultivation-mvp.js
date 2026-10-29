/* Official destination guide only. No copied prescriptions or legacy record approval. */
(function(root){
 'use strict';
 const topics=['재배 시작','재배환경','물·비료·생육 관리','병해충·생리장해','수확·저장','문제 해결·상담'];
 const directory=root.MunongsaCropDirectory,crops=directory.entries.map(e=>e.name),checked='2026.10.29';
 const sources=[
 {id:'pepper',crop:'고추',title:'고추 보통재배 농작업일정',institution:'농촌진흥청 · 농사로',type:'작물별 상세자료',topics:[0,1,2,4],conditions:'보통재배 기준입니다. 시설 작형에 그대로 적용하지 마세요.',url:'https://www.nongsaro.go.kr/portal/ps/psb/psbl/workScheduleDtl.ps?cntntsNo=30600&menuId=PS00087'},
 {id:'cabbage',crop:'배추',title:'배추 재배기술',institution:'농촌진흥청 · 국립원예특작과학원 협조',type:'작물별 상세자료',topics:[0,1,2,4],conditions:'김장용 가을배추 중심입니다. 여름 고랭지·겨울 작형은 별도로 확인하세요.',published:'2019년 제작',url:'https://www.nongsaro.go.kr/portal/ps/psb/psby/vodPlay.ps?cntntsNo=224491&menuId=PS65512&mvpNo=1800'},
 {id:'potato',crop:'감자',title:'감자 농작업일정',institution:'농촌진흥청 · 농사로',type:'작물별 상세자료',topics:[0,1,2,4],conditions:'봄·여름·가을·겨울시설 작형을 구분해 확인하세요.',url:'https://www.nongsaro.go.kr/portal/ps/psb/psbl/workScheduleDtl.ps?cntntsNo=30699&menuId=PS00087&sKidofcomdtySeCode=FC'},
 {id:'soil',title:'흙토람 비료사용처방',institution:'농촌진흥청 국립농업과학원',type:'공식 검색·처방 서비스',topics:[1,2],conditions:'공식 서비스에서 작물·필지·토양검정 조건을 직접 확인하세요. 개인별 처방 결과가 아닙니다.',url:'https://soil.rda.go.kr/sibi/sibiPrescript.do'},
 {id:'water',title:'흙토람 노지 밭 물사용 처방',institution:'농촌진흥청 국립농업과학원',type:'공식 검색·처방 서비스',topics:[2],conditions:'노지 밭용 서비스입니다. 시설재배에는 그대로 적용하지 마세요.',mode:'open',url:'https://soil.rda.go.kr/water/waterReport.do'},
 {id:'pest',title:'국가농작물병해충관리시스템 작물별 도감',institution:'농촌진흥청',type:'공식 검색·처방 서비스',topics:[3],conditions:'이동한 페이지에서 작물을 선택하세요. 증상만으로 병해충을 확정할 수 없습니다.',url:'https://ncpms.rda.go.kr/npms/FoodPhotoListR.np'},
 {id:'pesticide',title:'농약안전정보시스템 등록농약 검색',institution:'농촌진흥청',type:'공식 검색·처방 서비스',topics:[3],conditions:'해당 작물·병해충의 최신 등록 및 안전사용기준을 직접 확인하세요. 농약 처방을 제공하지 않습니다.',url:'https://psis.rda.go.kr/psis/agc/res/agchmRegistStusLst.ps?menuId=PS00263&pageUnit=20'},
 {id:'consult',title:'국가농작물병해충관리시스템 병해충 상담',institution:'농촌진흥청',type:'공식 상담 서비스',topics:[3,5],conditions:'공식 상담 목록으로 연결됩니다. 상담 신청 절차와 로그인 필요 여부는 해당 사이트에서 확인하세요.',url:'https://ncpms.rda.go.kr/npms/consult/ConsultListR.np'}
 ];
 sources.push({id:'guide',title:'농사로 작목별 매뉴얼 찾기',institution:'농촌진흥청 · 농사로',type:'공식 검색·처방 서비스',topics:[0,4],conditions:'작목 선택 화면입니다. 이동 후 작물을 다시 선택하고 지역·품종·작형을 확인하세요. 선택한 작물의 상세자료를 직접 연 링크가 아닙니다.',checked:'2026.10.30',url:directory.classificationSource});
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let selectedTopic=0;
 function choose(value){if(Number.isInteger(value)&&value>=0&&value<topics.length)selectedTopic=value}
 function select(crop,topic,mode){const name=directory.find(crop)?.name;if(!name)return [];return sources.filter(s=>(!s.crop||s.crop===name)&&s.topics.includes(topic)&&!(s.mode==='open'&&mode==='facility')&&!(s.id==='guide'&&sources.some(d=>d.crop===name&&d.topics.includes(topic))))}
 let query='',group='all',showAll=false;
 function options(){const matches=directory.search(query,group),limited=!query&&group==='all'&&!showAll,shown=limited?matches.slice(0,directory.representative.length):matches;
  return {matches,html:shown.map(e=>`<button type="button" data-crop-open="${esc(e.name)}" aria-pressed="${currentCrop===e.name}">${esc(e.name)}</button>`).join('')||'<p>찾는 작물이 없어요. 다른 이름으로 검색하거나 분류를 바꿔 보세요.</p>',limited}}
 let currentCrop='';
 function refresh(){const box=document.getElementById('cropDirectoryOptions');if(!box)return;const o=options();box.innerHTML=o.html;document.getElementById('cropDirectoryCount').textContent=o.limited?'먼저 찾기 쉬운 대표 작물 · 서비스 선정, 재배면적 순위 아님':`검색 결과 ${o.matches.length}종`;document.getElementById('cropDirectoryAll').hidden=!o.limited}
 function render(crop,profile={}){
  currentCrop=directory.find(crop)?.name||'';const list=select(currentCrop,selectedTopic,profile.cultivation),o=options();
  return `<section class="cultivation-guide"><h3>어떤 작물을 기르나요?</h3><div class="crop-directory-controls"><div><label for="cropDirectorySearch">작물 이름 검색</label><input id="cropDirectorySearch" type="search" value="${esc(query)}" placeholder="예: 벼, 토마토, 귤, 키위" autocomplete="off"></div><div><label for="cropDirectoryGroup">작물 분류</label><select id="cropDirectoryGroup"><option value="all">전체 분류</option>${directory.groups.map(g=>`<option${g===group?' selected':''}>${esc(g)}</option>`).join('')}</select></div></div><p class="hint">별칭·품종명은 대표 작물로 안내합니다. 세부 품종·작형은 원문에서 확인하세요.</p><p id="cropDirectoryCount" class="notice-meta">${o.limited?'먼저 찾기 쉬운 대표 작물 · 서비스 선정, 재배면적 순위 아님':`검색 결과 ${o.matches.length}종`}</p><div class="cultivation-options" id="cropDirectoryOptions">${o.html}</div><button type="button" id="cropDirectoryAll"${o.limited?'':' hidden'}>전체 ${crops.length}종 보기</button><details class="plain-help"><summary>작물 분류 기준</summary><p>농촌진흥청 작목 분류와 농작물생산조사 항목을 참고해 탐색하기 쉽게 묶었습니다. 세부 작형·용도에 따라 분류가 달라질 수 있습니다.</p><a href="${esc(directory.classificationSource)}" target="_blank" rel="noopener">농촌진흥청 작목 분류</a> · <a href="${esc(directory.statisticsSource)}" target="_blank" rel="noopener">농작물생산조사 참고자료</a></details>${!currentCrop?`<p class="data-note">${crop?esc(crop)+'은 현재 작물 목록에서 찾지 못했어요. ':''}작물을 선택하면 주제별 공식 자료를 볼 수 있어요. 기존 검토 자료는 그대로 보존합니다.</p>`:`<h3>${esc(currentCrop)} · 무엇이 궁금한가요?</h3><div class="cultivation-options">${topics.map((t,i)=>`<button type="button" data-cultivation-topic="${i}" aria-pressed="${selectedTopic===i}">${t}</button>`).join('')}</div><p class="data-note">공식 자료를 찾는 안내입니다. 지역·작형·토양과 실제 증상에 따라 적용 여부가 달라질 수 있습니다.</p><div class="cultivation-materials">${list.map(s=>`<article class="card cultivation-material" data-cultivation-source="${s.id}"><span class="tag">${s.type}</span><h3>${esc(s.title)}</h3><p>${esc(s.institution)}</p><p><b>이 자료를 안내하는 이유</b><br>${s.crop?esc(currentCrop)+'의 '+esc(topics[selectedTopic])+' 관련 내용을 확인할 수 있습니다.':esc(topics[selectedTopic])+'에 필요한 공식 '+(s.id==='consult'?'상담 경로':'검색·조회 경로')+'입니다. 이동 후 작물과 조건을 직접 선택하세요.'}</p><p><b>적용 전 확인</b><br>${esc(s.conditions)}</p><p class="notice-meta">자료 발행일: ${s.published||'원문에서 확인 필요'}<br>링크·내용 확인일: ${s.checked||checked}</p><a class="source-link source-action" href="${esc(s.url)}" target="_blank" rel="noopener">공식 자료 보기 ↗</a></article>`).join('')||'<p class="empty">이 주제에 맞는 공식 자료 연결을 준비 중입니다. 다른 주제를 선택해 주세요.</p>'}</div>`}</section>`;
 }
 if(typeof document!=='undefined'){
  document.addEventListener('input',e=>{if(e.target.id==='cropDirectorySearch'){query=e.target.value;refresh()}});
  document.addEventListener('change',e=>{if(e.target.id==='cropDirectoryGroup'){group=e.target.value;refresh()}});
  document.addEventListener('click',e=>{if(e.target.id==='cropDirectoryAll'){showAll=true;refresh()}});
 }
 root.MunongsaCultivation={topics,crops,sources,select,choose,render};
})(globalThis);
