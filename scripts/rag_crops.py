"""Read the existing browser crop directory; no second crop catalogue."""
import ast,re
from pathlib import Path

def catalogue():
    here=Path(__file__).resolve()
    source=next(p for p in (here.parent/'assets/crop-directory.js',here.parents[1]/'assets/crop-directory.js') if p.is_file()).read_text('utf8')
    groups=ast.literal_eval(re.search(r'const groups=(\[.*?\]);',source,re.S)[1])
    names=tuple(n for _,text in groups for n in text.split())
    if len(names)!=67 or len(set(names))!=67:raise ValueError('crop_directory_changed')
    return names

CROPS=catalogue()+('버섯','쌀') # Existing generic/alias profile values remain compatible.
SAFE_ALIASES={'키위':'참다래','쌀':'벼','논벼':'벼'}

def find(question):
    names=sorted((*CROPS,*SAFE_ALIASES),key=len,reverse=True)
    matches=list(re.finditer(r'(?<![가-힣])('+'|'.join(map(re.escape,names))+r')(?=\s|[?!.,]|$|은|는|이|가|을|를|에|로|과|와|의|도)',question))
    return SAFE_ALIASES.get(matches[-1][1],matches[-1][1]) if matches else None

def technology(question):
    return bool(re.search(r'재배기술|재배\s*방법|병해충|농약|비료\s*(?:사용|처방)|물\s*관리',question)) and not re.search(r'지원사업|보조금|공고',question)

def topic(question):
    return 3 if re.search(r'병해충|농약|생육\s*문제',question) else 2 if re.search(r'비료|관비|물\s*관리|관수',question) else 4 if re.search(r'수확|저장',question) else 1 if re.search(r'준비|환경|재배\s*방법',question) else 0
