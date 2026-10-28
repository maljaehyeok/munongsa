const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={URL};vm.runInNewContext(fs.readFileSync('assets/support-public.js','utf8'),context);
const api=context.MunongsaSupport;
const item={id:'SYNTHETIC-REFERENCE',publication:'approved_reference',verification_status:'verified',freshness:'current',
  last_checked_at:'2026-10-28T03:00:00Z',url:'https://www.mafra.go.kr/test',recommendation_eligible:false,
  rights:{public_display:'allowed',evidence_url:'https://www.mafra.go.kr/test-policy',checked_at:'2026-10-28'},
  application_status:'unknown',application_period:{},eligibility:{conditions:[],logic:{op:'UNKNOWN',children:[]}},
  reference_application_dates:{start:{date:'2026-10-01'},end:{date:'2026-10-30'}}};
let passed=0;const check=(value)=>{assert.ok(value);passed++};
const at=value=>Date.parse(value);
check(api.status(item,at('2026-10-28T12:00:00+09:00')).includes('접수 시각·가능 여부 확인 필요'));
check(!api.eligible(item,at('2026-10-28T12:00:00+09:00')));
check(api.status(item,at('2026-10-30T23:59:00+09:00')).includes('기재 신청기간 내'));
check(api.status(item,at('2026-10-31T00:00:00+09:00')).includes('신청기한 경과'));
check(api.status(item,at('2026-09-30T23:59:00+09:00')).includes('시작일 전'));
const deadlineOnly={...item,reference_application_dates:{end:{date:'2026-10-30'}}};
check(api.status(deadlineOnly,at('2026-10-28T12:00:00+09:00'))==='신청 상태 확인 필요');
check(api.status(deadlineOnly,at('2026-10-31T00:00:00+09:00')).includes('신청기한 경과'));
check(api.status({...item,reference_application_dates:{end:{date:'2026-02-30'}}},at('2026-10-28T12:00:00+09:00'))==='신청 상태 확인 필요');
const feed={schema_version:api.schema,notices:[item]};const found=api.explore(feed,{applicant:'individual'},at('2026-10-28T12:00:00+09:00'));
check(found.references.length===1&&found.recommendations.length===0);
check(api.explore({schema_version:api.schema,notices:[{...item,publication:'review'}]},{}).references.length===0);
const timed={...item,reference_application_dates:{start:{date:'2026-10-27'},end:{date:'2026-11-11',time:'18:00',timezone:'Asia/Seoul'}}};
check(api.status(timed,at('2026-11-11T17:59:00+09:00')).includes('기재 신청기간 내'));
check(api.status(timed,at('2026-11-11T18:01:00+09:00')).includes('신청기한 경과'));
const fact={condition_id:'residence',kind:'residence',presence:'specified',value:{regions:['전북 전주시']},status:'verified',evidence:{fact_confirmed:true,url:item.url,location:'Confirmed target facts'}};
const factual={...item,eligibility:{conditions:[fact],logic:{condition_id:'residence'}}};
check(api.evaluate(factual,{residenceRegion:'전북',residenceDistrict:'전주시'}).conditionStatus==='match');
check(api.evaluate(factual,{residenceRegion:'전북',residenceDistrict:'부안군'}).conditionStatus==='mismatch');
check(api.evaluate({...factual,eligibility:{...factual.eligibility,conditions:[{...fact,status:'candidate'}]}},{residenceRegion:'전북',residenceDistrict:'전주시'}).conditionStatus==='check');
console.log(JSON.stringify({passed,failed:0,external_requests:0}));
