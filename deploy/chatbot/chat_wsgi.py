"""Production HTTP adapter. Reuses the local-only pipeline; no search duplication."""
from collections import deque
import json
import logging
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import rag_api

ORIGIN = 'https://munongsa.duckdns.org'
LOG = logging.getLogger('munongsa.chat')


class SafeServerLog(logging.Filter):
    def filter(self, record):
        if record.name.startswith('waitress'):
            record.msg = 'HTTP server event; request contents omitted'
            record.args = ()
            record.exc_info = record.exc_text = None
        return True


class Application:
    def __init__(self, pipeline=rag_api.run_pipeline, ready=False):
        self.pipeline, self.ready = pipeline, ready
        self.lock, self.requests = threading.Lock(), deque()

    def __call__(self, environ, start_response):
        started = time.monotonic()
        status, data = 503, rag_api.failure('현재 이용할 수 없습니다.')
        try:
            status, data = self.handle(environ)
        except Exception:
            status, data = 503, rag_api.failure('근거 자료 검증에 실패해 답변을 보류합니다.')
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        phrases = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found',
                   405: 'Method Not Allowed', 413: 'Content Too Large', 415: 'Unsupported Media Type',
                   429: 'Too Many Requests', 503: 'Service Unavailable', 504: 'Gateway Timeout'}
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(body))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        if status == 429:
            headers.append(('Retry-After', '60'))
        if environ.get('PATH_INFO') != '/healthz':
            LOG.info('request_complete status=%d duration_ms=%d', status, int((time.monotonic()-started)*1000))
        start_response(f'{status} {phrases[status]}', headers)
        return [body]

    def handle(self, env):
        fail = rag_api.failure
        path, method = env.get('PATH_INFO'), env.get('REQUEST_METHOD')
        if path == '/healthz' and method == 'GET' and env.get('HTTP_HOST') in ('127.0.0.1:8765', 'localhost:8765'):
            return (200 if self.ready else 503), {'ready': self.ready, 'mode': 'local'}
        if path != '/api/chat':
            return 404, fail('요청한 경로를 찾지 못했습니다.')
        if env.get('HTTP_HOST') != 'munongsa.duckdns.org' or env.get('HTTP_ORIGIN') != ORIGIN:
            return 403, fail('허용된 서비스 주소에서만 사용할 수 있습니다.')
        if method != 'POST':
            return 405, fail('질문은 POST 방식으로 보내 주세요.')
        if env.get('QUERY_STRING'):
            return 400, fail('질문은 주소가 아닌 JSON 본문으로 보내 주세요.')
        if not self.ready:
            return 503, fail('검증 자료 준비 상태를 확인해야 합니다.')
        with self.lock:
            now = time.monotonic()
            while self.requests and now-self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 10:
                return 429, fail('요청이 많습니다. 1분 후 다시 시도해 주세요.')
            self.requests.append(now)
        if env.get('CONTENT_TYPE', '').split(';')[0].strip() != 'application/json':
            return 415, fail('JSON 형식으로 질문을 보내 주세요.')
        try:
            length = int(env.get('CONTENT_LENGTH', ''))
            if not 1 <= length <= rag_api.MAX_BODY:
                return 413, fail('질문을 1,000자 이내로 줄여 주세요.')
            raw = env['wsgi.input'].read(length)
            if len(raw) != length:
                raise ValueError()
            question = rag_api.validate_input(json.loads(raw.decode('utf-8')))
        except (ValueError, UnicodeError, RecursionError):
            return 400, fail('질문만 포함한 JSON을 보내 주세요. 질문은 1~1,000자여야 합니다.')
        try:
            result = self.pipeline(question)
            if result.get('mode') != 'local':
                raise ValueError()
            return 200, result
        except subprocess.TimeoutExpired:
            return 504, fail('처리 시간이 초과됐습니다. 질문을 짧게 바꿔 주세요.')
        except Exception:
            return 503, fail('공고 근거를 검증하지 못해 답변을 보류합니다.')


def main(inherited_socket=None, application_wrapper=None):
    # Fail before listening if any snapshot/document/approval check fails.
    try:
        corpus = rag_api.load_api_corpus()
        if corpus['excluded'] or len(corpus['documents']) != rag_api.EXPECTED_DOCUMENTS:
            raise ValueError()
    except Exception:
        print('Verified corpus unavailable; server not started.', file=sys.stderr)
        return 2
    from waitress import serve
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    for handler in logging.getLogger().handlers:
        handler.addFilter(SafeServerLog())
    try:
        serve(application_wrapper(Application(ready=True)), sockets=[inherited_socket], threads=2,
              connection_limit=8, backlog=8, channel_timeout=10, cleanup_interval=1,
              max_request_header_size=8192, max_request_body_size=8192,
              inbuf_overflow=16384, outbuf_overflow=262144, channel_request_lookahead=0,
              expose_tracebacks=False, ident='Munongsa', clear_untrusted_proxy_headers=True)
    except KeyboardInterrupt:
        pass
    except Exception:
        print('HTTP server stopped; inspect sanitized status logs.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
