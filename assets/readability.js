/* Presentation only. Keep every source character, number, caveat and approval gate. */
(function(root){
 'use strict';
 function segments(value){
  const text=String(value??'');
  if(text.length<100)return [text];
  // Preserve delimiters and spaces verbatim; never infer semantic field labels.
  return text.match(/[^\n]+?(?:[.!?。](?:[ \t]+|$)|(?=\n)|$)|\n+/g)?.filter(Boolean)||[text];
 }
 function paragraph(el){
  if(el.dataset.readableText!==undefined||el.children.length||el.closest('script,style,textarea,output'))return;
  const original=el.textContent,parts=segments(original);if(parts.length<2)return;
  const fragment=document.createDocumentFragment();
  for(const part of parts){const span=document.createElement('span');span.className='readable-paragraph';span.textContent=part;fragment.append(span);}
  el.replaceChildren(fragment);el.dataset.readableText='';
 }
 function enhance(scope=document){
  for(const el of scope.querySelectorAll('.notice-fact-value,.finance-card-terms dd,.support-detail-list dd,.cultivation-material p,.chat-answer-text p,.chat-condition-block li,.finance-caution'))paragraph(el);
  for(const button of scope.querySelectorAll('.official-notice>.compact-open')){
   const title=button.querySelector(':scope>strong');if(title&&button.firstElementChild!==title)button.prepend(title);
  }
  for(const terms of scope.querySelectorAll('.finance-card-terms:not([data-readable-order])')){
   const priority=label=>/금리|비용/.test(label)?0:/한도|단가/.test(label)?1:/지원 대상/.test(label)?2:/자금 용도/.test(label)?3:4;
   [...terms.children].map((el,i)=>({el,i,p:priority(el.querySelector('dt')?.textContent||'')})).sort((a,b)=>a.p-b.p||a.i-b.i).forEach(({el})=>terms.append(el));terms.dataset.readableOrder='';
  }
  for(const status of scope.querySelectorAll('.notice-status')){
   const seen=new Set();for(const el of status.children){const value=el.textContent.trim();if(seen.has(value))el.remove();else seen.add(value);}
  }
 }
 function mount(){
  enhance();let scheduled=false;
  const observer=new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;enhance();});});
  for(const id of ['cards','modalSource','chatHistory']){const el=document.getElementById(id);if(el)observer.observe(el,{subtree:true,childList:true,characterData:true});}
 }
 root.MunongsaReadable={segments,enhance};
 if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();}
})(globalThis);
