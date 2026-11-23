const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
vm.runInThisContext(fs.readFileSync('assets/readability.js','utf8'));
const samples=[
 '왕우렁이 종패 구입비 50% 지원. 기준단가는 kg당 6,000원, 친환경 인증면적 ha당 50kg(300,000원) 기준이며 이를 개인 지급액으로 확정하지 않음. 신분증·농업경영체등록증·친환경 인증서류 안내. 제외 조건과 예외는 공식 원문에서 확인하세요.',
 '연 1.5% 가정. 대출금 50,000,000원. 월평균 62,500원은 실제 월 상환액이 아님. 보증료·원금 상환은 제외. '+'확인 필요. '.repeat(20),
 '<script>alert(1)</script>\n지원하지 않음.\n\n예외 조건. '+'자료 확인 '.repeat(30),
 '', '0원', '300,000원', '1.5%', '공식 근거 없음'
];
for(const s of samples)assert.equal(MunongsaReadable.segments(s).join(''),s,'all characters and qualifications preserved');
assert.ok(MunongsaReadable.segments(samples[0]).length>1);
if(process.argv[2]){
 let strings=0;const walk=v=>{if(typeof v==='string'){assert.equal(MunongsaReadable.segments(v).join(''),v);strings++;}else if(v&&typeof v==='object')Object.values(v).forEach(walk)};
 walk(JSON.parse(fs.readFileSync(process.argv[2],'utf8')));console.log(JSON.stringify({approved_data_strings_preserved:strings}));
}
const html=fs.readFileSync('index.html','utf8');const hero=html.slice(html.indexOf('<section class="brand-home"'),html.indexOf('<section class="support-discovery"'));
assert.ok(!hero.includes('data-start-chat')&&!hero.includes('data-home-service'));
assert.ok(html.includes('id="openChat"')&&html.includes('data-start-conditions')&&hero.includes('href="#supportDiscovery"'));
const css=fs.readFileSync('assets/readability.css','utf8');assert.ok(css.includes('prefers-reduced-motion:reduce')&&css.includes('animation:none'));
assert.ok(css.includes('border-top:1px solid #aaa;color:#505050;font-weight:400'),'examples need dark text on light cards');
console.log('표시 문자·단위·부정·예외 보존과 홈 탐색·움직임 최소화 검사 통과');
