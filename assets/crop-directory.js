/* Discovery labels grouped for beginners; not area/popularity statistics or eligibility. */
(function(root){
 'use strict';
 const groups=[
 ['엽채·줄기채소','배추 양배추 상추 시금치 깻잎 부추 미나리 쑥갓'],
 ['과채류','토마토 오이 딸기 수박 참외 멜론 호박 가지 파프리카'],
 ['근채·조미채소','무 당근 고추 마늘 양파 대파 쪽파 생강 우엉'],
 ['곡류·두류','벼 보리 밀 콩 팥 녹두 옥수수 조 수수 메밀'],
 ['감자·고구마류','감자 고구마'],
 ['과수','사과 배 포도 감귤 복숭아 자두 매실 감 블루베리 참다래 무화과 유자'],
 ['특용·약용·버섯','인삼 황기 작약 당귀 구기자 참깨 들깨 땅콩 차 표고버섯 느타리버섯'],
 ['화훼·기타','국화 장미 백합 카네이션 거베라 난류']
 ];
 const aliases={벼:['쌀','논벼'],고추:['풋고추','홍고추','청양고추'],토마토:['방울토마토'],감귤:['귤','밀감'],참다래:['키위'],파프리카:['피망','단고추'],대파:['파'],콩:['대두','백태','검정콩','서리태'],감:['단감','떫은감'],차:['차나무','녹차'],난류:['난','난초']};
 const representative=['벼','고추','배추','감자','콩','마늘','양파','무','고구마','토마토','오이','딸기','사과','배','포도','감귤'];
 const entries=groups.flatMap(([group,names])=>names.split(' ').map(name=>({name,group,aliases:aliases[name]||[]})));
 const norm=s=>String(s||'').normalize('NFKC').replace(/\s/g,'').toLowerCase();
 function find(value){const q=norm(value);return entries.find(e=>norm(e.name)===q)||entries.find(e=>e.aliases.some(a=>norm(a)===q))}
 function search(query='',group='all'){
  const q=norm(query),score=e=>!q?0:norm(e.name)===q?0:e.aliases.some(a=>norm(a)===q)?1:norm(e.name).startsWith(q)?2:e.aliases.some(a=>norm(a).startsWith(q))?3:4;
  const priority=e=>{const i=representative.indexOf(e.name);return i<0?999:i};
  return entries.filter(e=>(group==='all'||e.group===group)&&(!q||[e.name,...e.aliases].some(v=>norm(v).includes(q)))).sort((a,b)=>score(a)-score(b)||priority(a)-priority(b)||a.name.localeCompare(b.name,'ko'));
 }
 root.MunongsaCropDirectory={groups:groups.map(g=>g[0]),entries,representative,find,search,
  classificationSource:'https://nongsaro.go.kr/portal/ps/psx/psxj/cropManualMain.mo?farmerMainFlag=VC011205',
  statisticsSource:'https://kostat.go.kr/boardDownload.es?bid=11843&list_no=434749&seq=1'};
})(globalThis);
