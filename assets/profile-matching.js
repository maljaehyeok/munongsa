/* Browser-local relevance ordering. This does not decide eligibility or availability. */
(function (root) {
  'use strict';
  const regionAliases = {
    '전북': ['전북', '전라북도'], '전남': ['전남', '전라남도'],
    '경북': ['경북', '경상북도'], '경남': ['경남', '경상남도'],
    '충북': ['충북', '충청북도'], '충남': ['충남', '충청남도'],
    '강원': ['강원'], '제주': ['제주'], '경기': ['경기'],
    '서울': ['서울'], '인천': ['인천'], '대전': ['대전'], '세종': ['세종'],
    '광주': ['광주'], '대구': ['대구'], '울산': ['울산'], '부산': ['부산']
  };
  const cropNames = {rice:'벼',garlic:'마늘',onion:'양파',apple:'사과',cabbage:'배추',radish:'무',potato:'감자',sweetpotato:'고구마',soybean:'콩',wheat:'밀',pepper:'고추',greenonion:'파',scallion:'쪽파',strawberry:'딸기'};
  const asList = v => Array.isArray(v) ? v : [];
  function regionScope(text) {
    const value = typeof text === 'string' ? text : '';
    // General cropping/climate terms do not establish nationwide applicability.
    if (value.includes('전국')) return {national:true, provinces:[], districts:[], text:value};
    return {national:false, provinces:Object.keys(regionAliases).filter(k=>regionAliases[k].some(a=>value.includes(a))), districts:[], text:value};
  }
  function describe(kind, item) {
    const r = item.raw && ['equipment','guideline'].includes(kind) ? item.raw : item;
    const record = {regions:[],districts:[],crops:[],stages:[],modes:[],audiences:[],regionText:'',national:false};
    if (kind === 'program') {
      record.regions = asList(r.regions);
      record.national = record.regions.includes('all');
      record.districts = asList(r.districts);
      record.crops = asList(r.cropCodes);
      record.modes = asList(r.cultivationModes);
      record.audiences = asList(r.audiences);
      // Same early-career flag used by the existing profile filter; relevance only.
      record.stages = r.needYouthCareer ? ['planned','under1','1to3'] : record.audiences.includes('prospective') ? ['planned'] : [];
    } else if (kind === 'cultivationRecord' || kind === 'cultivationReview') {
      const scope = regionScope(r.regionAndCropping);
      record.regions=scope.provinces;record.national=scope.national;record.regionText=scope.text;
      record.crops = Object.keys(cropNames).filter(k=>cropNames[k] === r.crop);
      if (r.crop && !record.crops.length) record.crops=['other'];
    } else if (kind === 'catalog') {
      const scope=regionScope(r.region);
      record.regions=scope.provinces;record.national=scope.national;record.regionText=scope.text;
      const parts=typeof r.crop==='string'?r.crop.split(/[·,、/\s]+/):[];
      record.crops=Object.keys(cropNames).filter(k=>parts.includes(cropNames[k]));
      record.modes=r.cultivationMode?[r.cultivationMode]:[];
    } else if (kind === 'equipment' || kind === 'guideline') {
      record.modes=asList(r.cultivationModes);
      if(r.cultivationMode)record.modes=[r.cultivationMode];
      // Candidate names, team matching drafts and use descriptions are not verified crop/region criteria.
    }
    return record;
  }
  function evaluate(kind,item,profile) {
    const r=describe(kind,item), matched=[],unknown=[],different=[];
    let score=0;
    const selected=v=>v && !['all','unknown'].includes(v);
    if(selected(profile.region)) {
      if(r.national){matched.push('전국 범위 자료');score+=2;}
      else if(r.regions.includes(profile.region)){matched.push('시·도 관련');score+=5;}
      else if(r.regions.length){different.push('시·도 기록 다름');score-=5;}
      else unknown.push('지역');
    }
    if(selected(profile.district)) {
      if(r.districts.includes(profile.district)||r.regionText.includes(profile.district)){matched.push('시·군·구 관련');score+=8;}
      else if(r.districts.length){different.push('시·군·구 기록 다름');score-=8;}
      else unknown.push('시·군·구 적용');
    }
    if(selected(profile.crop)) {
      if(r.crops.includes(profile.crop)){matched.push('작물 관련');score+=7;}
      else if(r.crops.length){different.push('작물 기록 다름');score-=7;}
      else unknown.push('작물');
    }
    if(selected(profile.experience)) {
      if(r.stages.includes(profile.experience)){matched.push('영농 단계 관련');score+=3;}
      else if(r.stages.length){different.push('영농 단계 기록 다름');score-=3;}
      else unknown.push('영농 단계');
    }
    if(selected(profile.cultivation)) {
      if(r.modes.includes(profile.cultivation)||r.modes.includes('both')){matched.push('재배 방식 관련');score+=2;}
      else if(r.modes.length){different.push('재배 방식 기록 다름');score-=2;}
      else unknown.push('재배 방식');
    }
    if(selected(profile.applicant)) {
      if(r.audiences.includes(profile.applicant)){matched.push('신청자 유형 관련');score+=2;}
      else if(r.audiences.length){different.push('신청자 유형 기록 다름');score-=2;}
      else unknown.push('신청자 유형');
    }
    return {score,matched,unknown,different,needsCheck:unknown.length>0||different.length>0};
  }
  function rank(kind,rows,profile) {
    return rows.map((item,index)=>({item,index,match:evaluate(kind,item,profile)}))
      .sort((a,b)=>b.match.score-a.match.score||a.index-b.index);
  }
  root.MunongsaMatching={evaluate,rank,describe};
})(globalThis);
