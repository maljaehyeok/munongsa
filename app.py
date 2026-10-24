from flask import Flask, render_template_string, request, abort

app = Flask(__name__)

# 멘토님이 보내주신 2026년 공모계획·시행지침에서 확인한 정보만 담았습니다.
# 공모 일정은 문서 기준이며, 현재 신청 가능 여부를 뜻하지 않습니다.
PROGRAMS = [
    {
        "id": "openfield-district-2026",
        "title": "2026년 노지 스마트농업 육성지구",
        "category": "지원사업",
        "audience": "단체·지자체",
        "region": "전국 공모(시·도 추천)",
        "crop": "대규모 주산지 품목",
        "scale": "재배면적 약 500ha 내외",
        "summary": "노지 스마트농업 생산단지와 전후방산업을 함께 조성하는 지구 단위 사업입니다.",
        "amount": "개소당 3년간 총 95억 원 기준",
        "deadline": "2026년 공모계획 기준 접수기간: 2026. 1. 26. ~ 1. 30. (종료)",
        "source": "농림축산식품부, 「2026년 노지 스마트농업 육성지구 지정 공모계획」 및 「2026년 사업 시행지침」",
        "requirements": [
            "시·군 단위 컨소시엄(생산자단체, 지방정부, 솔루션 기업 등)이 사업 주체입니다.",
            "생산자단체는 지구 내 참여 농업인으로 조직화된 단체이며, 지자체가 후보지를 신청합니다.",
            "생산면적은 약 500ha 내외를 기준으로 하며, 용수·전기·통신 등 기반 여건도 검토합니다.",
            "지원 규모와 부담 비율은 문서 기준입니다. 실제 적용 전 최신 공고와 담당 기관 안내를 확인해야 합니다.",
        ],
        "link": "https://www.mafra.go.kr/",
    }
]

BASE = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>무농사 | 농업 정보 큐레이션</title>
  <style>
    :root{--ink:#18231d;--green:#245b43;--mint:#e8f3ec;--muted:#68766e;--line:#e3e9e5;--paper:#f7f9f7}
    *{box-sizing:border-box}body{margin:0;color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--paper)}
    a{color:inherit;text-decoration:none}.top{height:68px;background:#111714;color:white;display:flex;align-items:center;justify-content:space-between;padding:0 max(5vw,24px);position:sticky;top:0;z-index:2}
    .brand{font-size:24px;font-weight:850;letter-spacing:-1px}.brand span{color:#76bd8e}.nav{display:flex;gap:28px;font-size:14px}.nav a:hover{color:#a6d6b4}
    .wrap{width:min(1180px,92vw);margin:auto}.hero{background:linear-gradient(115deg,#1c4935,#70946e);color:white;padding:58px max(5vw,24px);min-height:310px}
    .hero-inner{max-width:1180px;margin:auto}.eyebrow{font-size:14px;opacity:.88}.hero h1{font-size:48px;line-height:1.1;margin:12px 0}.hero p{font-size:17px;line-height:1.7;max-width:580px}
    .button{display:inline-block;background:white;color:#1b4935;border:0;border-radius:999px;padding:13px 20px;font-weight:750;cursor:pointer;margin-top:10px}
    .section{padding:34px 0}.section h2{font-size:23px;margin:0 0 18px}.lead{color:var(--muted);margin-top:-8px}
    .categories{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.cat{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;font-weight:750;min-height:86px}.cat small{display:block;color:var(--muted);font-weight:450;margin-top:7px}
    .layout{display:grid;grid-template-columns:310px 1fr;gap:22px;align-items:start}.panel,.card,.detail{background:white;border:1px solid var(--line);border-radius:16px;box-shadow:0 5px 18px #213b2a0a}
    .panel{padding:22px;position:sticky;top:88px}.panel h2{font-size:20px;margin:0 0 6px}.field{margin-top:17px}.field label{display:block;font-size:14px;font-weight:700;margin-bottom:7px}.field select,.field input{width:100%;border:1px solid #ccd7d0;border-radius:9px;padding:12px;background:white;font:inherit;color:var(--ink)}
    .submit{width:100%;border:0;border-radius:10px;padding:13px;background:var(--green);color:white;font-weight:750;font-size:15px;margin-top:20px;cursor:pointer}.hint{font-size:12px;color:var(--muted);line-height:1.6;margin-top:14px}
    .results-head{display:flex;justify-content:space-between;align-items:end;margin-bottom:14px}.results-head h2{margin:0}.count{color:var(--muted);font-size:14px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}.card{padding:21px;display:flex;flex-direction:column;min-height:270px}.badge{display:inline-block;background:var(--mint);color:var(--green);border-radius:99px;padding:5px 10px;font-size:12px;font-weight:750;align-self:flex-start}.card h3{font-size:20px;line-height:1.4;margin:15px 0 8px}.card p{color:var(--muted);font-size:14px;line-height:1.65;margin:0 0 14px}.meta{font-size:13px;line-height:1.8;border-top:1px solid var(--line);padding-top:12px;margin-top:auto}.more{display:inline-block;color:var(--green);font-weight:750;margin-top:13px}
    .empty{padding:30px;background:white;border:1px dashed #b9c9bf;border-radius:14px;color:var(--muted);line-height:1.7}.detail{padding:28px}.detail h1{font-size:30px;margin:14px 0 8px}.detail h2{font-size:19px;margin-top:26px}.detail p,.detail li{line-height:1.75;color:#435148}.detail li{margin:8px 0}.source{background:#f2f6f3;border-radius:10px;padding:15px;font-size:13px;color:#516057;line-height:1.7}.back{color:var(--green);font-weight:700}.footer{border-top:1px solid var(--line);padding:24px 0 38px;color:var(--muted);font-size:12px;line-height:1.7}
    @media(max-width:800px){.nav{gap:12px;font-size:12px}.hero h1{font-size:38px}.layout{grid-template-columns:1fr}.panel{position:static}.cards{grid-template-columns:1fr}.categories{grid-template-columns:1fr}.top{padding:0 18px}.wrap{width:calc(100% - 32px)}}
  </style>
</head><body>
<header class="top"><a class="brand" href="/">무농사<span>🌱</span></a><nav class="nav"><a href="/">홈</a><a href="/support">지원사업</a><a href="/#categories">농자재·장비</a><a href="/#categories">영농 노하우</a></nav></header>
{{ body|safe }}
<footer class="wrap footer">무농사는 농업 정보를 찾기 쉽게 정리하는 학습 프로젝트입니다. 실제 신청 가능 여부와 세부 조건은 반드시 각 사업의 최신 공고 및 담당 기관에서 확인하세요.</footer>
</body></html>"""


@app.get("/")
def home():
    body = """<section class="hero"><div class="hero-inner"><div class="eyebrow">농업 정보, 내 조건에 맞게 한눈에</div><h1>무농사</h1><p>지원사업부터 농자재와 영농 정보까지<br>필요한 정보를 더 쉽게 찾아보세요.</p><a class="button" href="/support">지원사업 둘러보기 →</a></div></section>
    <main class="wrap"><section class="section" id="categories"><h2>무엇을 찾고 계신가요?</h2><div class="categories"><a class="cat" href="/support">🏛️ 지원사업<small>대상과 조건을 확인해요</small></a><div class="cat">🌱 농자재·장비<small>자료를 준비하고 있어요</small></div><div class="cat">📖 영농 노하우<small>자료를 준비하고 있어요</small></div></div></section>
    <section class="section"><h2>먼저 확인할 수 있는 정보</h2><p class="lead">멘토님이 공유해주신 공식 지침을 바탕으로 정리한 사업입니다.</p><div class="cards">""" + card_html(PROGRAMS[0]) + """</div></section></main>"""
    return render_template_string(BASE, body=body)


def card_html(item):
    return f'''<article class="card"><span class="badge">{item["category"]} · {item["audience"]} 대상</span><h3>{item["title"]}</h3><p>{item["summary"]}</p><div class="meta"><b>{item["scale"]}</b><br>{item["amount"]}<br>{item["deadline"]}</div><a class="more" href="/program/{item["id"]}">사업 정보 보기 →</a></article>'''


@app.get("/support")
def support():
    audience = request.args.get("audience", "")
    crop = request.args.get("crop", "")
    region = request.args.get("region", "")
    found = [p for p in PROGRAMS if (not audience or p["audience"] == audience)
             and (not crop or crop in p["crop"] or p["crop"] == "대규모 주산지 품목")
             and (not region or region == "전국")]
    cards = "".join(card_html(p) for p in found)
    if not cards:
        cards = '<div class="empty">선택한 조건에 해당하는 자료를 찾지 못했어요.<br>조건을 바꾸거나, 새 공고가 등록되었는지 공식 사이트에서 확인해 주세요.</div>'
    body = f'''<main class="wrap section"><div class="layout"><form class="panel" method="get"><h2>조건으로 찾아보기</h2><div class="lead">정보를 찾을 대상을 선택하세요.</div>
      <div class="field"><label for="audience">대상 구분</label><select id="audience" name="audience"><option value="">전체</option><option value="개인 농업인" {"selected" if audience=="개인 농업인" else ""}>개인 농업인</option><option value="단체·지자체" {"selected" if audience=="단체·지자체" else ""}>생산자단체·지자체</option></select></div>
      <div class="field"><label for="region">지역</label><select id="region" name="region"><option value="">전체 지역</option><option value="전국" {"selected" if region=="전국" else ""}>전국 공모</option></select></div>
      <div class="field"><label for="crop">작물</label><select id="crop" name="crop"><option value="">전체 작물</option><option value="대규모 주산지 품목" {"selected" if crop else ""}>대규모 주산지 품목</option></select></div>
      <button class="submit" type="submit">조건 적용하기</button><p class="hint">이 사업은 개인 농가 단독 신청 사업이 아닙니다. 공고문 기준 사업 대상과 규모를 카드에 함께 표시합니다.</p></form>
      <section><div class="results-head"><div><h2>지원사업 정보</h2><div class="count">공식 지침을 확인한 자료 {len(found)}건</div></div></div><div class="cards">{cards}</div></section></div></main>'''
    return render_template_string(BASE, body=body)


@app.get("/program/<program_id>")
def program_detail(program_id):
    item = next((p for p in PROGRAMS if p["id"] == program_id), None)
    if item is None:
        abort(404)
    requirements = "".join(f"<li>{x}</li>" for x in item["requirements"])
    body = f'''<main class="wrap section"><a class="back" href="/support">← 지원사업 목록으로</a><article class="detail" style="margin-top:18px"><span class="badge">{item["category"]} · {item["audience"]} 대상</span><h1>{item["title"]}</h1><p>{item["summary"]}</p><h2>핵심 내용</h2><ul><li><b>사업 규모:</b> {item["scale"]}</li><li><b>지원 기준:</b> {item["amount"]}</li><li><b>공모 일정:</b> {item["deadline"]}</li></ul><h2>대상과 확인 조건</h2><ul>{requirements}</ul><h2>출처 및 주의사항</h2><div class="source">{item["source"]}<br>이 페이지는 제공된 문서의 내용을 학습용으로 요약했습니다. 공고 일정이 지난 문서이므로 현재 신청 가능 여부를 뜻하지 않습니다. 세부 내용은 최신 공고와 담당 기관에 확인하세요.</div><p><a class="more" href="{item["link"]}" target="_blank" rel="noopener">농림축산식품부 사이트 열기 ↗</a></p></article></main>'''
    return render_template_string(BASE, body=body)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
