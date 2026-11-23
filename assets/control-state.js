/* Presentation attributes derive only from real input/ARIA state; no fact mutation. */
(function(){
 'use strict';let queued=false;
 function sync(){queued=false;document.querySelectorAll('select').forEach(el=>{el.dataset.selected=String(!['','all','unknown'].includes(el.value))});}
 function schedule(){if(!queued){queued=true;requestAnimationFrame(sync)}}
 document.addEventListener('change',schedule);document.addEventListener('input',schedule);
 new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});schedule();
})();
