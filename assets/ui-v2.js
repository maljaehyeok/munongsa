/* UI shell only. No data, eligibility, publication or recommendation changes. */
(function(root){
  'use strict';
  const labels={support:'지원사업',bank:'농업금융',cultivation:'재배기술',equipment:'농업장비 · 보존된 이전 화면'};
  const byId=id=>document.getElementById(id);
  let profileCategory=null;
  let browseState={homeView:true,activeCategory:'support'},browseQueued=false;
  function queueBrowseContext(){if(browseQueued)return;browseQueued=true;requestAnimationFrame(()=>{browseQueued=false;updateBrowseContext()})}
  function updateBrowseContext(){
    const summary=byId('selectionSummary'),order=byId('browseOrder');if(!summary||!order)return;
    summary.hidden=browseState.homeView;order.hidden=browseState.homeView;if(browseState.homeView)return;
    const category=browseState.activeCategory,filters=[],add=(label,value)=>{if(value&&value!=='all')filters.push({label,value})},value=id=>byId(id)?.value?.trim(),selected=id=>{const el=byId(id);return el&&el.value!=='all'?el.selectedOptions[0]?.textContent.trim():''};
    if(category==='support'){
      add('검색',value('supportSearch'));
      const state=document.querySelector('[data-support-status].active');if(state&&state.dataset.supportStatus!=='all')add('상태',state.childNodes[0]?.textContent.trim());
      add('기간',selected('supportPeriodFilter'));
      order.textContent='표시 순서 · 모집기간 → 조건 비교 → 관련도 → 마감일';
    }else if(category==='bank'){
      add('검색',value('financeSearch'));add('자금 목적',selected('financePurpose'));
      order.textContent='표시 순서 · 기본 조건 비교 우선 / 대출·보증 승인과는 별개';
    }else if(category==='cultivation'){
      add('작물 검색',value('cropDirectorySearch'));add('분류',selected('cropDirectoryGroup'));
      add('선택 작물',document.querySelector('[data-crop-open][aria-pressed="true"]')?.textContent.trim());
      add('주제',document.querySelector('[data-cultivation-topic][aria-pressed="true"]')?.textContent.trim());
      order.textContent='표시 순서 · 작물 검색은 이름·별칭 일치도 우선 / 자료는 검증된 직접 연결 우선';
    }
    const list=byId('browseFilterSummary');list.replaceChildren(...filters.map(({label,value})=>{const chip=document.createElement('span'),name=document.createElement('span'),chosen=document.createElement('strong');chip.className='selection-chip';name.className='condition-label';chosen.className='condition-value';name.textContent=label;chosen.textContent=value;chip.append(name,chosen);return chip}));
    const hasProfile=byId('profileSummary').childElementCount>0;byId('profileSelectionRow').hidden=!hasProfile;byId('browseSelectionRow').hidden=!filters.length;byId('browseSelectionEmpty').hidden=hasProfile||filters.length>0;
  }
  function closeMenu(){byId('mainNav').classList.remove('is-open');byId('menuToggle').setAttribute('aria-expanded','false')}
  function sync({homeView,serviceHomeView,activeCategory}){
    browseState={homeView,activeCategory};queueBrowseContext();
    document.body.dataset.view=homeView?'brand':'explore';
    byId('top').hidden=!homeView;
    byId('brandServices').hidden=!homeView;
    byId('serviceHome').hidden=true;
    byId('exploreToolbar').hidden=homeView;
    byId('serviceNotice').hidden=homeView;
    byId('currentServiceLabel').textContent=labels[activeCategory]||'자료 탐색';
    document.querySelector('#modal h3').textContent=activeCategory==='cultivation'?'어디에 적용할 수 있나요? · 확인할 조건':'누가 신청할 수 있나요? · 확인할 조건';
    const serviceLink=document.querySelector('[data-nav-service]');
    serviceLink.classList.toggle('active',homeView);
    if(homeView)serviceLink.setAttribute('aria-current','page');else serviceLink.removeAttribute('aria-current');
    document.querySelectorAll('[data-nav-category]').forEach(link=>{
      const current=!homeView&&link.dataset.navCategory===activeCategory;
      link.classList.toggle('active',current);
      if(current)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    });
    // Presentation only: existing inputs and matching semantics stay unchanged.
    const support=activeCategory==='support';
    byId('interestField').hidden=true;
    byId('profileAvatar').hidden=support||activeCategory==='bank';
    byId('profileStatus').hidden=support||activeCategory==='bank';
    byId('farmingSituationField').hidden=homeView||!['support','bank'].includes(activeCategory);
    byId('supportNeedField').hidden=homeView||!support;
    document.querySelector('.filters-intro').textContent=support||activeCategory==='bank'
      ?'지역과 현재 농업 상황만 알려주세요. 잘 모르는 항목은 비워두고 둘러볼 수 있어요.'
      :'작물은 입력창이나 작물 목록에서 선택하세요. 재배 방식은 자료의 적용 범위를 살펴볼 때 사용해요.';
    if(!homeView&&profileCategory!==activeCategory){
      byId('additionalProfileFields').open=!['support','bank'].includes(activeCategory);
      profileCategory=activeCategory;
    }
    // Preserve the old budget control and value, but it has no place in the new menu.
    byId('budget').closest('.field').hidden=activeCategory!=='equipment'||homeView;
  }
  function mount(navigate){
    // Reuse the 67 discovery names, retaining legacy values used by saved profiles.
    const cropSelect=byId('crop'),directory=root.MunongsaCropDirectory;
    for(const crop of directory.entries){
      const existing=[...cropSelect.options].find(o=>directory.find(o.textContent)?.name===crop.name);
      if(existing)existing.textContent=crop.name;
      else{const option=document.createElement('option');option.value=crop.name;option.textContent=crop.name;cropSelect.append(option)}
    }
    cropSelect.append(cropSelect.querySelector('option[value="other"]'));
    document.addEventListener('input',event=>{if(event.target.id==='cropDirectorySearch')queueBrowseContext()});
    document.addEventListener('change',event=>{if(event.target.id==='cropDirectoryGroup')queueBrowseContext()});
    const media=window.matchMedia('(max-width:760px)');
    function setProfileExpanded(expanded){byId('filterForm').classList.toggle('is-collapsed',!expanded);byId('profileToggle').setAttribute('aria-expanded',String(expanded));byId('profileToggle').textContent=expanded?'접기':'내 조건 입력'}
    setProfileExpanded(!media.matches);
    media.addEventListener('change',()=>setProfileExpanded(!media.matches));
    byId('profileToggle').addEventListener('click',()=>setProfileExpanded(byId('profileToggle').getAttribute('aria-expanded')!=='true'));
    byId('menuToggle').addEventListener('click',()=>{
      const open=byId('menuToggle').getAttribute('aria-expanded')!=='true';
      byId('mainNav').classList.toggle('is-open',open);
      byId('menuToggle').setAttribute('aria-expanded',String(open));
    });
    document.addEventListener('click',event=>{
      if(event.target.closest('[data-scroll-services]')){
        event.preventDefault();
        const target=byId('brandServicesHeading');
        target.focus({preventScroll:true});
        byId('brandServices').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth',block:'start'});
        return;
      }
      const homeService=event.target.closest('[data-home-service]');
      if(homeService){event.preventDefault();navigate(homeService.dataset.homeService);return}
      if(event.target.closest('.skip-link')){event.preventDefault();const target=document.body.dataset.view==='brand'?byId('brandHeading'):document.body.dataset.view==='service'?byId('serviceHeading'):byId('results');target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'start'});return}
      if(event.target.closest('[data-service-home],[data-nav-service]')){event.preventDefault();navigate(null);return}
      if(event.target.closest('[data-open-support]')){event.preventDefault();navigate('support')}
    });
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&byId('mainNav').classList.contains('is-open')){closeMenu();byId('menuToggle').focus()}});
  }
  root.MunongsaUI={mount,sync,closeMenu};
})(globalThis);
