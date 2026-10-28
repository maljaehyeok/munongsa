"""Promoted from the working local collector (2026-10-28).
Senior project row/link/date parsing reused with the operator's permission.
No trial data, automatic approval or publication side effects.
"""
import re

def extra_facts(lines,url):
    rules={'target_description':r'(?:사업대상|지원대상|신청대상)',
           'support_description':r'(?:사업내용|지원내용|지원내역|지원단가|지원금액)',
           'budget_total':r'(?:사업비|총사업비)',
           'application_method':r'(?:신청방법|접수방법|신청장소|접수장소|접수처|신청접수처)',
           'required_documents':r'(?:제출서류|신청서류|구비서류)',
           'exclusion_description':r'(?:제외대상|지원제외|신청제외)'}
    result={}
    for key,label in rules.items():
        label=re.sub(r'([가-힣])(?=[가-힣])',r'\1\\s*',label)
        found=[]
        for i,line in enumerate(lines):
            clean=re.sub(r'^\s*(?:[가-하][.．)]|[○❍□▪※▶\d.]+)\s*','',line)
            if re.fullmatch(label+r'\s*[:：]\s*',clean) and i+1<len(lines):
                clean+=' '+lines[i+1];line+=' '+lines[i+1]
            match=re.match(label+r'\s*[:：]\s*(.+)',clean)
            if match and match[1].strip() and len(line)<=500:found.append((match[1].strip(),line))
        if found:
            result[key]={'value':' / '.join(dict.fromkeys(x[0] for x in found))[:350],
                'evidence':{'url':url,'location':'공식 상세의 명시된 항목명','quote':' / '.join(dict.fromkeys(x[1] for x in found))[:420]}}
    return result


def rate_facts(lines,url):
    """Preserve per-litre rates as rates, never fabricate a per-applicant grant."""
    for i,line in enumerate(lines):
        if re.search(r'지원\s*유종.*단가',line):
            following=' '.join(lines[i:min(i+3,len(lines))])
            if re.search(r'단가\s*[:：]',following) and re.search(r'원\s*/\s*[ℓLl리터]',following):
                evidence={'url':url,'location':'공식 상세의 지원유종 및 단가 항목','quote':(line+' '+following)[:420]}
                return {'support_unit_rates':{'value':following,'evidence':evidence},'support_description':{'value':line+' '+following,'evidence':evidence}}
    return {}

