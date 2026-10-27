/* UI shell only. No data, eligibility, publication or recommendation changes. */
(function(root){
  'use strict';
  const labels={support:'지원사업',bank:'농업금융',cultivation:'공식 재배정보',equipment:'농업장비 · 보존된 이전 화면'};
  const byId=id=>document.getElementById(id);
  let profileCategory=null;
  function closeMenu(){byId('mainNav').classList.remove('is-open');byId('menuToggle').setAttribute('aria-expanded','false')}
  function sync({homeView,serviceHomeView,activeCategory}){
    document.body.dataset.view=homeView?(serviceHomeView?'service':'brand'):'explore';
    byId('top').hidden=!homeView||serviceHomeView;
    byId('serviceHome').hidden=!homeView||!serviceHomeView;
    byId('exploreToolbar').hidden=homeView;
    byId('serviceNotice').hidden=homeView&&!serviceHomeView;
    byId('currentServiceLabel').textContent=labels[activeCategory]||'자료 탐색';
    document.querySelector('#modal h3').textContent=activeCategory==='cultivation'?'어디에 적용할 수 있나요? · 확인할 조건':'누가 신청할 수 있나요? · 확인할 조건';
    const serviceLink=document.querySelector('[data-nav-service]');
    serviceLink.classList.toggle('active',homeView&&serviceHomeView);
    if(homeView&&serviceHomeView)serviceLink.setAttribute('aria-current','page');else serviceLink.removeAttribute('aria-current');
    document.querySelectorAll('[data-nav-category]').forEach(link=>{
      const current=!homeView&&link.dataset.navCategory===activeCategory;
      link.classList.toggle('active',current);
      if(current)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');
    });
    // Presentation only: existing inputs and matching semantics stay unchanged.
    const support=activeCategory==='support';
    byId('interestField').hidden=support;
    byId('profileAvatar').hidden=support;
    document.querySelector('.filters-intro').textContent=support
      ?'먼저 영농 지역과 현재 나이, 영농 단계를 알려주세요. 정확한 자격 비교가 필요하면 추가 정보를 입력할 수 있어요.'
      :'관심 분야와 내 상황을 선택하면 기록된 조건과 관련된 자료부터 보여드려요. 조건이 없는 자료는 확인이 필요한 후보로 표시합니다.';
    if(!homeView&&profileCategory!==activeCategory){
      byId('additionalProfileFields').open=!support;
      profileCategory=activeCategory;
    }
    // Preserve the old budget control and value, but it has no place in the new menu.
    byId('budget').closest('.field').hidden=activeCategory!=='equipment'||homeView;
  }
  function mount(navigate){
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
      if(event.target.closest('.skip-link')){event.preventDefault();const target=document.body.dataset.view==='brand'?byId('brandHeading'):document.body.dataset.view==='service'?byId('serviceHeading'):byId('results');target.tabIndex=-1;target.focus({preventScroll:true});target.scrollIntoView({block:'start'});return}
      if(event.target.closest('[data-service-home],[data-nav-service]')){event.preventDefault();navigate('service');return}
      if(event.target.closest('[data-open-support]')){event.preventDefault();navigate('support')}
    });
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&byId('mainNav').classList.contains('is-open')){closeMenu();byId('menuToggle').focus()}});
  }
  root.MunongsaUI={mount,sync,closeMenu};
})(globalThis);
