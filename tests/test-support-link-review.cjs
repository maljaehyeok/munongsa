/* Synthetic metadata only. No operational notices, keys, original text or API calls. */
const assert=require('assert/strict'),fs=require('fs'),vm=require('vm'),path=require('path');
const root={location:{hostname:'example.test'},URL,URLSearchParams,Intl,Date,MunongsaSupport:{safeUrl:u=>u.startsWith('https://')}};root.globalThis=root;
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/support-details.js'),'utf8'),root);
const api=root.MunongsaSupportDetails,item={id:'synthetic',title:'Synthetic notice',url:'https://agency.go.kr/notice/1',source_id:'synthetic'};
const now=Date.now(),review={schema:'munongsa-official-link-review-v1',basis:{...item},state:'official_detail',checked_at:new Date(now-1000).toISOString(),expires_at:new Date(now+60000).toISOString(),field_locations:{target:'<script>invalid</script>'}};
const app={source_url:item.url,url:'https://agency.go.kr/apply',kind:'login_unverified',actual_submission_verified:false,evidence_chain:[{url:item.url,location:'Official link'},{url:'https://agency.go.kr/apply',location:'Login required'}]};
const install=r=>api.install({schema:'munongsa-support-details-v1',records:[],link_reviews:[r]});
install({...review,application:app});assert(api.application(item,now));assert.equal(api.get(item),null);
assert.equal(api.application({...item,title:'Changed'},now),null);assert.equal(api.application(item,now+120000),null);
for(const invalid of [{...app,url:item.url},{...app,url:'https://evil.test/apply'},{...app,source_url:'https://other.go.kr/notice'}, {...app,evidence_chain:[]},{...app,actual_submission_verified:true}]){install({...review,application:invalid});assert.equal(api.application(item,now),null);}
install({...review,state:'title_or_detail_unconfirmed',application:app});assert.equal(api.application(item,now),null);
install(review);const text=api.links(item,s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;'));assert(!text.includes('<script>'));assert(text.includes('확인되지 않았어요'));assert(!text.includes('official_detail'));
assert.equal(JSON.stringify(api.basis(item)),JSON.stringify(api.basis(item)));
console.log(JSON.stringify({passed:true,cases:11}));
