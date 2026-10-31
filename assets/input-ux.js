/* Input adapters only. Unknown entries are saved as notes, never eligibility facts. */
(function(root){
 'use strict';
 const by=id=>document.getElementById(id),norm=v=>String(v||'').normalize('NFKC').replace(/\s/g,'').toLowerCase();
 const provinceNames={전북:'전북특별자치도',전남:'전라남도',경북:'경상북도',경남:'경상남도',충북:'충청북도',충남:'충청남도',강원:'강원특별자치도',제주:'제주특별자치도',경기:'경기도',서울:'서울특별시',부산:'부산광역시',대구:'대구광역시',인천:'인천광역시',광주:'광주광역시',대전:'대전광역시',울산:'울산광역시',세종:'세종특별자치시'};
 let custom={customCrop:'',customFarmRegion:'',customResidence:''},widgets=[],places=[],refresh=()=>{},ready=false,restored=false;
 function crop(value){return root.MunongsaCropDirectory.find(value)||null}
 function region(value){const q=norm(value);if(!q)return null;const found=places.filter(p=>p.aliases.some(a=>norm(a)===q));return found.length===1?found[0]:null}
 function validBirth(value,today=new Date(Date.now()+9*3600000).toISOString().slice(0,10)){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const d=new Date(value+'T00:00:00Z');return Number.isFinite(+d)&&d.toISOString().slice(0,10)===value&&value<=today&&Number(value.slice(0,4))>0;
 }
 let requiredFundsWon=null,fundsDirty=false;
 const validFunds=v=>Number.isSafeInteger(v)&&v>0&&v%10000===0;
 const fundsText=v=>root.MunongsaSelection.money(v);
 function profile(){return {...custom,requiredFundsWon}}
 function restore(p={}){for(const k of Object.keys(custom))custom[k]=typeof p[k]==='string'?p[k].slice(0,100):'';requiredFundsWon=validFunds(p.requiredFundsWon)?p.requiredFundsWon:null;fundsDirty=false;restored=!!Object.keys(p).length;sync(true)}
 function parseFunds(raw){const text=String(raw).trim();if(!text)return null;if(!/^(?:\d+|[1-9]\d{0,2}(?:,\d{3})+)$/.test(text))return NaN;const won=Number(text.replace(/,/g,''))*10000;return validFunds(won)?won:NaN}
 function syncFunds(force=false){const input=by('requiredFundsMan');if(!input||fundsDirty&&!force)return;fundsDirty=false;input.value=requiredFundsWon===null?'':(requiredFundsWon/10000).toLocaleString('ko-KR');input.setAttribute('aria-invalid','false');by('requiredFundsStatus').textContent=requiredFundsWon===null?'':'적용된 필요 자금: '+fundsText(requiredFundsWon);}
 function applyFunds(clear=false){const input=by('requiredFundsMan'),value=clear?null:parseFunds(input.value);if(Number.isNaN(value)){requiredFundsWon=null;fundsDirty=true;refresh('funds');input.setAttribute('aria-invalid','true');by('requiredFundsStatus').textContent='만원 단위의 0보다 큰 정수를 입력해 주세요. 잘못된 금액은 비교하지 않아요.';return}requiredFundsWon=value;fundsDirty=false;syncFunds(true);refresh('funds')}
 function mountFunds(){const input=by('requiredFundsMan');input.addEventListener('input',()=>{fundsDirty=true;input.setAttribute('aria-invalid','false');by('requiredFundsStatus').textContent=requiredFundsWon===null?(input.value.trim()?'아직 적용하지 않음':''):'적용 중: '+fundsText(requiredFundsWon)+' · 수정 내용 미적용'});input.addEventListener('change',e=>e.stopPropagation());input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();e.stopPropagation();applyFunds()}});by('applyRequiredFunds').addEventListener('click',()=>applyFunds());by('clearRequiredFunds').addEventListener('click',()=>{applyFunds(true);input.focus()})}
 function fieldCrop(){const f=by('crop');return f.value==='all'?'':root.MunongsaCropDirectory.find(f.selectedOptions[0]?.textContent)?.name||f.selectedOptions[0]?.textContent||''}
 function placeText(residence=false){const a=by(residence?'residenceRegion':'region').value,b=by(residence?'residenceDistrict':'district').value;return [provinceNames[a]||a,b].filter(v=>v&&!['all','unknown'].includes(v)).join(' ')}
 function applied(kind){return kind==='crop'?(custom.customCrop||fieldCrop()):kind==='farm'?(custom.customFarmRegion||placeText()):kind==='residence'?(custom.customResidence||placeText(true)):by('birthDate').value}
 function commit(kind,value){
  const raw=String(value||'').trim().slice(0,100);
  restored=false;
  if(kind==='birth'&&raw&&!validBirth(raw)){
   by('birthDate').value='';refresh(kind);const w=widgets.find(w=>w.kind===kind);w.dirty=true;w.input.value=raw;w.input.setAttribute('aria-invalid','true');w.status.dataset.state='invalid';w.status.textContent='날짜를 확인해 주세요. 미래 날짜나 존재하지 않는 날짜는 비교에 사용하지 않아요.';return;
  }
  if(kind==='crop'){
   const match=crop(raw),f=by('crop');custom.customCrop=match?'':raw;
   f.value=match?[...f.options].find(o=>crop(o.textContent)?.name===match.name)?.value||'all':'all';
   f.dispatchEvent(new Event('change',{bubbles:true}));
  }else if(kind==='farm'||kind==='residence'){
   const match=region(raw),residence=kind==='residence';custom[residence?'customResidence':'customFarmRegion']=match?'':raw;
   if(residence){by('residenceRegion').value=match?.region||'';by('residenceDistrict').value=match?.district||'';}
   else{by('region').value=match?.region||'all';by('region').dispatchEvent(new Event('change',{bubbles:true}));by('district').value=match?.district||'all';}
  }else if(kind==='birth'){
   by('birthDate').value=raw&&validBirth(raw)?raw:'';
  }
  const w=widgets.find(w=>w.kind===kind);if(w){w.dirty=false;w.close();}sync(true);refresh(kind);
 }
 function suggestions(kind,q){
  if(!norm(q))return [];
  if(kind==='crop')return root.MunongsaCropDirectory.search(q).slice(0,8).map(e=>e.name);
  const n=norm(q);return places.filter(p=>!n||p.aliases.some(a=>norm(a).includes(n))).sort((a,b)=>Number(norm(b.text)===n)-Number(norm(a.text)===n)).slice(0,8).map(p=>p.text);
 }
 function widget(kind,id,label,placeholder){
  const native=by(id),field=native.closest('.field');native.hidden=true;
  if(kind==='farm')native.parentElement.hidden=true;
  if(kind==='residence')by('residenceDistrict').closest('.field').classList.add('ux-native-only');
  field.classList.add('ux-field');const oldLabel=field.querySelector('label');oldLabel.textContent=label;
  const box=document.createElement('div');box.className='input-ux';
  const row=document.createElement('div');row.className='input-ux-row';
  const input=document.createElement('input');input.id=id+'Entry';input.type='text';input.maxLength=100;input.placeholder=placeholder;input.autocomplete='off';
  oldLabel.htmlFor=input.id;
  const apply=document.createElement('button');apply.type='button';apply.textContent='적용';apply.className='ux-apply';apply.setAttribute('aria-label',label+' 적용');
  const clear=document.createElement('button');clear.type='button';clear.textContent='지우기';clear.className='ux-clear';clear.setAttribute('aria-label',label+' 삭제');
  const actions=document.createElement('div');actions.className='input-ux-actions';actions.append(apply,clear);
  row.append(input,actions);const list=document.createElement('div');list.className='ux-suggestions';list.id=input.id+'List';list.setAttribute('role','listbox');list.hidden=true;
  const status=document.createElement('p');status.className='ux-status';status.id=input.id+'Status';status.setAttribute('role','status');input.setAttribute('aria-describedby',status.id);
  if(kind!=='birth'){input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls',list.id);input.setAttribute('aria-expanded','false');}
  else{input.inputMode='numeric';input.maxLength=10;by('birthDateHint').hidden=true;}
  box.append(row,list,status);field.append(box);
  const w={kind,input,status,dirty:false,active:-1,items:[],close(){list.hidden=true;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');w.active=-1;},open(){
   w.active=-1;w.items=suggestions(kind,input.value);list.replaceChildren();input.removeAttribute('aria-activedescendant');
   for(const [i,text]of w.items.entries()){const b=document.createElement('button');b.type='button';b.id=input.id+'Option'+i;b.setAttribute('role','option');b.setAttribute('aria-selected','false');b.textContent=text;b.addEventListener('click',()=>{commit(kind,text);input.focus()});list.append(b);}
   list.hidden=!w.items.length;input.setAttribute('aria-expanded',String(!!w.items.length));
  }};widgets.push(w);
  input.addEventListener('input',()=>{
   if(kind==='birth'&&/^[\d-]+$/.test(input.value)&&input.value.replace(/-/g,'').length<=8&&input.selectionStart===input.value.length){const d=input.value.replace(/-/g,'');input.value=d.slice(0,4)+(d.length>4?'-'+d.slice(4,6):'')+(d.length>6?'-'+d.slice(6,8):'');}
   w.dirty=true;status.dataset.state='draft';const v=input.value.trim();
   if(kind==='birth'){
    input.setAttribute('aria-invalid',String(!!v&&!validBirth(v)));
    if(v&&!validBirth(v))status.dataset.state='invalid';
    status.textContent=!v?'생년월일 없이 탐색 중':validBirth(v)?'아직 적용하지 않음':'날짜를 확인해 주세요. YYYY-MM-DD 형식의 실제 날짜만 입력할 수 있어요.';
    if(by('birthDate').value){by('birthDate').value='';refresh(kind);}
   }else{const current=applied(kind);status.textContent=current?'적용 중: '+current+' · 수정 내용 미적용':v?'아직 적용하지 않음':'조건 없음 · 전체 탐색';w.open();}
  });
  input.addEventListener('focus',()=>{if(kind!=='birth')w.open()});
  // Draft text must not trigger the legacy form's change redraw on blur.
  input.addEventListener('change',e=>e.stopPropagation());
  input.addEventListener('keydown',e=>{
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();w.close();return}
   if((e.key==='ArrowDown'||e.key==='ArrowUp')&&kind!=='birth'){e.preventDefault();if(list.hidden)w.open();if(!w.items.length)return;w.active=(w.active+(e.key==='ArrowDown'?1:-1)+w.items.length)%w.items.length;[...list.children].forEach((b,i)=>b.setAttribute('aria-selected',String(i===w.active)));input.setAttribute('aria-activedescendant',input.id+'Option'+w.active);return}
   if(e.key==='Enter'){e.preventDefault();e.stopPropagation();commit(kind,w.active>=0?w.items[w.active]:input.value);}
  });
  apply.addEventListener('click',()=>commit(kind,input.value));clear.addEventListener('click',()=>{commit(kind,'');input.focus()});
  box.addEventListener('focusout',()=>setTimeout(()=>{if(!box.contains(document.activeElement))w.close()},0));
 }
 function sync(force=false){if(!ready)return;for(const w of widgets){
  const value=applied(w.kind);if(w.dirty&&!force)continue;if(force)w.dirty=false;w.input.value=value;
  const customKey={crop:'customCrop',farm:'customFarmRegion',residence:'customResidence'}[w.kind];
  w.status.textContent=value?(custom[customKey]?'입력값 보관: '+value+' · 목록에서 확인되지 않아 자격 비교에 사용하지 않아요.':(restored?'복원된 조건: ':'적용된 조건: ')+value+(w.kind==='birth'?' · 공고·제도 기준으로 연령을 비교해요.':w.kind==='crop'?' · 지원사업·재배기술에서 함께 사용해요.':w.kind==='farm'?' · 거주지와 별도이며 재배자료의 지역별 처방을 뜻하지 않아요.':'')):'조건 없음 · 입력 없이 전체 탐색';
  w.status.dataset.state=value?(custom[customKey]?'unknown':'applied'):'empty';w.input.setAttribute('aria-invalid','false');
 }syncFunds(force)}
 function reset(){custom={customCrop:'',customFarmRegion:'',customResidence:''};requiredFundsWon=null;fundsDirty=false;for(const w of widgets){w.dirty=false;w.close()}sync(true)}
 function mount(districts,onApply){
  refresh=onApply;
  for(const [code,text]of Object.entries(provinceNames)){
   // Preserve the existing confirmed province options; do not invent district mappings.
   if(![...by('region').options].some(o=>o.value===code)){const o=document.createElement('option');o.value=code;o.textContent=text;by('region').append(o)}
   places.push({region:code,district:'',text,aliases:[code,text,...(code==='전북'?['전라북도']:code==='강원'?['강원도']:code==='제주'?['제주도']:[])]});
   for(const d of districts[code]||[])places.push({region:code,district:d,text:text+' '+d,aliases:[text+' '+d,code+' '+d,d,d.replace(/[시군]$/,'')]});
  }
  widget('farm','region','영농지역 검색','예: 전주, 전북');widget('crop','crop','재배 작물 검색','예: 딸기, 벼');widget('residence','residenceRegion','거주지 검색','예: 전주, 전북');widget('birth','birthDate','생년월일','YYYY-MM-DD');
  // Move the existing crop field out of the long optional section; keep its storage values.
  by('region').closest('.field').after(by('crop').closest('.field'));
  mountFunds();by('filterForm').addEventListener('submit',()=>{for(const w of widgets)if(w.dirty)commit(w.kind,w.input.value);if(fundsDirty)applyFunds()});
  by('crop').addEventListener('change',()=>{if(by('crop').value!=='all')custom.customCrop='';sync()});
  ready=true;sync(true);
 }
 root.MunongsaInputUX={mount,profile,restore,sync,reset,commit,validBirth,region,crop,parseFunds};
})(globalThis);
