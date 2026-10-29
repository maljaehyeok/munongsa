"""Bounded official KoAT board adapter; facts only, never publication approval."""
import re
from bs4 import BeautifulSoup
from . import boards, periods, enrichment

BOARD = 'https://www.koat.or.kr/board/business/list.do'


def rows(body):
    result = {}
    for tr in BeautifulSoup(body, 'html.parser').select('tbody tr'):
        for a in tr.select('a[onclick]'):
            match = re.fullmatch(r'postLink\((\d+)\);?', a['onclick'].strip())
            if not match:
                continue
            title = boards.clean(a.get_text(' ', strip=True))
            date = re.search(r'20\d{2}-\d{2}-\d{2}', tr.get_text(' ', strip=True))
            result[match[1]] = {
                'original_id': 'business:' + match[1], 'title': title,
                'original_url': 'https://www.koat.or.kr/board/business/' + match[1] + '/view.do',
                'published_at': date[0] if date else None,
                'board_category': 'official business notice', 'department': 'unknown',
            }
    return list(result.values())


def candidate(row):
    # Selection results and recruitment of delivery institutions are separate
    # from a farmer/business funding opportunity. Never infer individual access.
    return (boards.classify(row) != 'excluded'
            and not re.search(r'선정|결과|교육기관|교육생|전문가\s*교육|인턴', row['title'])
            and bool(re.search(r'모집|지원|공모', row['title'])))


def collect(source, now, known=None, detail_policy=None):
    from . import discovery
    transport = discovery.Transport(source)
    transport.fact_enricher = enrichment.extra_facts
    group = {'kind': source['kind'], 'city': source['city'], 'analyses': [],
             'errors': [], 'list_count': 0, 'candidate_count': 0, 'requests': 0,
             'state': '연결 미완료', 'attempts': []}
    try:
        transport.get('https://www.koat.or.kr/robots.txt', True)
        listed = rows(transport.get(BOARD))
        group['list_count'] = len(listed)
        items = [r for r in listed if candidate(r)]
        group.update(candidate_count=len(items), list_rows=items, state='연결 성공')
        # No publication-age cutoff: an old announcement may still be open.
        items.sort(key=lambda r: ((source['kind'], r['original_id']) in (known or {}),
                                  '연장' not in r['title'], r['published_at'] or ''))
        for row in items[:min(int(source.get('detail_limit', 2)), 4)]:
            prior = (known or {}).get((source['kind'], row['original_id']))
            fetch = True
            if detail_policy:
                fetch, prior = detail_policy(source['kind'], row, prior, now)
            if not fetch and prior:
                group['analyses'].append(dict(prior, metadata=row, detail_fetched=False))
                continue
            entry = discovery.analyse({'kind': source['kind'], 'metadata': row}, transport, now)
            entry.update(detail_fetched=True, automatic_approval=False)
            group['analyses'].append(entry)
    except Exception as error:
        group['errors'].append({'stage': 'official_koat_board', 'error': boards.error_name(error)})
    group['requests'] = transport.count
    return group
