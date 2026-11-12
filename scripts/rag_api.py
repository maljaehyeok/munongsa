"""Loopback-only, local-evidence API. No keys, remote LLM, DB or result-file writes."""
import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import rag_answer
import rag_search

API_PATH = '/api/chat'
MAX_QUESTION = 2000  # Includes bounded transient context; the user question stays <=1,000.
MAX_BODY = 8192
PIPELINE_TIMEOUT = 8
REQUEST_TIMEOUT = 15
EXPECTED_DOCUMENTS = 11


def load_api_corpus():
    # Explicit server selection; request parameters cannot change the corpus or mode.
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory:
        import rag_sync
        return rag_sync.load(directory)
    return rag_search.load_corpus(expanded=True)


def corpus_ready(corpus):
    if corpus.get('sync_generation'):
        return corpus.get('sync_verified') is True
    return not corpus['excluded'] and len(corpus['documents']) == EXPECTED_DOCUMENTS


class VerificationError(Exception):
    pass


def validate_input(data):
    if not isinstance(data, dict) or set(data) != {'question'}:
        raise ValueError('invalid_input')
    question = data['question']
    if (not isinstance(question, str) or not 1 <= len(question.strip()) <= MAX_QUESTION
            or len(question) > MAX_QUESTION
            or any((ord(c) < 32 and c not in '\n\t\r') or 0xD800 <= ord(c) <= 0xDFFF for c in question)):
        raise ValueError('invalid_question')
    import rag_dialogue
    rag_dialogue.decode(question)
    return question.strip()


def failure(message):
    return {'mode': 'local', 'status': 'error', 'answer': message, 'programs': [], 'sources': []}


def checked_at(value):
    value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        raise VerificationError()
    return value.astimezone(rag_answer.KST).isoformat()


def public_source(value):
    if not rag_search.valid_url(value['url']):
        raise VerificationError()
    return {'url': value['url'], 'location': value['location'], 'checked_at': checked_at(value['checked_at'])}


def public_response(result):
    """Allowlist public fields; never serialize retrieval internals or raw exceptions."""
    if result.get('excluded') or result.get('status') == 'data_unavailable':
        raise VerificationError()
    if result.get('status') == 'not_found':
        return {'mode': 'local', 'status': 'no_evidence',
                'answer': '공개 승인된 공고의 저장 근거에서 질문에 답할 내용을 찾지 못했습니다. 사업명이나 질문을 바꿔 주세요.',
                'programs': [], 'sources': []}
    groups = result.get('businesses', [])
    if not groups or any(g.get('evidence_status') == 'data_unavailable' for g in groups):
        raise VerificationError()
    generation = result['answer_generation']
    if generation.get('llm_called') or not result.get('local_only'):
        raise VerificationError()
    programs = []
    for group in groups:
        if not rag_search.valid_url(group['official_source']):
            raise VerificationError()
        period = group['recruitment']
        dates = period['recorded_dates']
        programs.append({
            'id': group['notice_id'], 'name': group['business_name'],
            'source_url': group['official_source'], 'checked_at': checked_at(group['checked_at']),
            'required_conditions': [v for c in group['key_eligibility'] for v in c['approved_values']],
            'additional_checks': list(group['unconfirmed_conditions']['statements']) + list(group.get('conflicts', [])),
            'evidence_level': '승인된 요약 근거' if group.get('source_material_kind') == 'approved_summary' else '저장 원문 발췌',
            'evidence_note': ('원문 직접 인용이 아닌 기존 승인 요약입니다. 최신 원문 전체를 다시 검증한 답변이 아닙니다.'
                              if group.get('source_material_kind') == 'approved_summary' else
                              '저장된 원문에서 검토한 구간입니다. 최신 변경·전체 자격·실제 접수 여부는 별도 확인이 필요합니다.'),
            'application_period': {
                'start': {k: (dates.get('start') or {}).get(k) for k in ('date', 'time', 'timezone')},
                'end': {k: (dates.get('end') or {}).get(k) for k in ('date', 'time', 'timezone')},
                'description': period['date_message'], 'actual_reception_confirmed': False},
            'needs_verification': group['answer_policy'] != 'grounded_explanation_only'})
    response = {'mode': 'local', 'status': 'needs_verification' if any(p['needs_verification'] for p in programs) else 'answered',
                'answer': generation['local_answer'], 'programs': programs,
                'sources': [public_source(s) for s in generation['local_citations']]}
    # Defense against accidentally introducing local paths into a public text field.
    serialized = json.dumps(response, ensure_ascii=False)
    if re.search(r'(?i)(?:(?<![a-z])[a-z]:[\\/]|file://|(?:work|scripts|assets)[\\/])', serialized):
        raise VerificationError()
    return response


def grounded_response(question, corpus, notice=None):
    retrieved = rag_search.search(question, corpus, notice=notice, limit=3)
    result = rag_answer.generate(retrieved, local_only=True, manifest={}, environ={})
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory:
        import rag_sync
        current = rag_sync.load(directory)
        for business in result.get('businesses', []):
            key = business['notice_key']
            if key not in current['documents'] or key not in corpus['documents']:
                raise VerificationError()
            before, after = corpus['documents'][key], current['documents'][key]
            if (rag_search.record_sha(before['record']) != rag_search.record_sha(after['record'])
                    or rag_sync.material(before['public']) != rag_sync.material(after['public'])):
                raise VerificationError()
    return public_response(result)


def local_pipeline(question):
    # No server session or DB writes. Every factual response uses the existing
    # approval/hash loader, including contextual follow-ups and discovery lists.
    corpus = load_api_corpus()
    if not corpus_ready(corpus):
        raise VerificationError()
    import rag_dialogue
    response = rag_dialogue.respond(question, corpus,
        lambda query, notice: grounded_response(query, corpus, notice))
    directory = os.environ.get('MUNONGSA_RAG_SYNC_DIR')
    if directory and response['programs']:
        import rag_sync
        current = rag_sync.load(directory)
        before = {d['public']['id']: d for d in corpus['documents'].values()}
        after = {d['public']['id']: d for d in current['documents'].values()}
        for program in response['programs']:
            identity = program['id']
            if (identity not in after or identity not in before
                    or rag_search.record_sha(before[identity]['record']) != rag_search.record_sha(after[identity]['record'])
                    or rag_sync.material(before[identity]['public']) != rag_sync.material(after[identity]['public'])):
                raise VerificationError()
    return response


def run_pipeline(question, timeout=PIPELINE_TIMEOUT):
    # No inherited API keys. A child process can be killed when the deadline expires.
    env = {k: v for k, v in os.environ.items() if k.upper() in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    if os.environ.get('MUNONGSA_RAG_SYNC_DIR'):
        env['MUNONGSA_RAG_SYNC_DIR'] = os.environ['MUNONGSA_RAG_SYNC_DIR']
    completed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker'],
                               input=json.dumps({'question': question}, ensure_ascii=False),
                               encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               timeout=timeout, env=env, check=False)
    if completed.returncode != 0 or len(completed.stdout) > 262144:
        raise VerificationError()
    return json.loads(completed.stdout)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = True

    def __init__(self, port, origins, rate_limit=10, pipeline=run_pipeline):
        self.origins, self.rate_limit, self.pipeline = set(origins), rate_limit, pipeline
        self.recent, self.rate_lock, self.slots = deque(), threading.Lock(), threading.BoundedSemaphore(4)
        super().__init__(('127.0.0.1', port), Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(1)
                body = json.dumps(failure('처리 중인 질문이 많습니다. 잠시 후 다시 시도해 주세요.'), ensure_ascii=False).encode('utf-8')
                headers = ('HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\n'
                           f'Content-Length: {len(body)}\r\nCache-Control: no-store\r\nRetry-After: 5\r\nConnection: close\r\n\r\n')
                request.sendall(headers.encode('ascii') + body)
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # No request bodies, headers, paths or tracebacks in server logs.

    def take_request(self):
        now = time.monotonic()
        with self.rate_lock:
            while self.recent and now - self.recent[0] >= 60:
                self.recent.popleft()
            if len(self.recent) >= self.rate_limit:
                return False
            self.recent.append(now)
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = 'MunongsaLocal'
    sys_version = ''

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, failure('요청을 처리할 수 없습니다. 입력과 주소를 확인해 주세요.'))

    def handle(self):
        self.connection.settimeout(5)
        def expire():
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = threading.Timer(REQUEST_TIMEOUT, expire)
        deadline.daemon = True
        deadline.start()
        try:
            super().handle()
        finally:
            deadline.cancel()

    def reply(self, code, data=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if data is not None else b''
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Connection', 'close')
            origin = self.headers.get('Origin') if hasattr(self, 'headers') else None
            if origin in self.server.origins:
                self.send_header('Access-Control-Allow-Origin', origin)
                self.send_header('Vary', 'Origin')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            if code in (429, 503):
                self.send_header('Retry-After', '60' if code == 429 else '5')
            self.end_headers()
            if body:
                self.wfile.write(body)
        except OSError:
            pass
        self.close_connection = True

    def allowed(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host_headers = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if (len(host_headers) != 1 or host_headers[0] not in hosts
                or len(origins) > 1 or (origins and origins[0] not in self.server.origins)):
            self.reply(403, failure('허용된 로컬 화면에서만 사용할 수 있습니다.'))
            return False
        if self.path != API_PATH:
            self.reply(404, failure('요청한 API 경로를 찾지 못했습니다.'))
            return False
        return True

    def do_OPTIONS(self):
        if self.allowed():
            self.reply(204)

    def do_GET(self):
        if self.allowed():
            self.reply(405, failure('질문은 POST 방식으로 보내 주세요.'))

    def do_POST(self):
        if not self.allowed():
            return
        if not self.server.take_request():
            self.reply(429, failure('질문 요청이 많습니다. 잠시 후 다시 시도해 주세요.'))
            return
        if self.headers.get_content_type() != 'application/json':
            self.reply(415, failure('JSON 형식으로 질문을 보내 주세요.'))
            return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,8}', lengths[0]):
            self.reply(400, failure('요청 크기 정보를 확인할 수 없습니다.'))
            return
        length = int(lengths[0])
        if not 1 <= length <= MAX_BODY:
            self.reply(413, failure('요청이 너무 큽니다. 질문을 1,000자 이내로 줄여 주세요.'))
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            question = validate_input(json.loads(raw.decode('utf-8')))
        except (ValueError, UnicodeError, RecursionError):
            self.reply(400, failure('질문만 포함한 JSON을 보내 주세요. 질문은 공백을 제외해 1~1,000자여야 합니다.'))
            return
        except OSError:
            self.reply(408, failure('질문 수신 시간이 초과됐습니다. 다시 시도해 주세요.'))
            return
        try:
            self.reply(200, self.server.pipeline(question))
        except subprocess.TimeoutExpired:
            self.reply(504, failure('답변 처리 시간이 초과됐습니다. 질문을 짧게 바꿔 주세요.'))
        except Exception:
            self.reply(503, failure('근거 자료 검증 또는 처리에 실패해 답변을 보류합니다. 자료를 확인해 주세요.'))


def main():
    parser = argparse.ArgumentParser(description='무농사 로컬 전용 질문 API · 외부 AI 호출 없음')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--ui-origin', action='append', help='허용할 로컬 UI 주소. 예: http://127.0.0.1:8000')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        # This process cannot open sockets, even if a later pipeline edit tries to.
        def no_network(*args, **kwargs):
            raise RuntimeError('network_disabled')
        socket.socket = no_network
        try:
            data = json.loads(sys.stdin.buffer.read(MAX_BODY + 1))
            result = local_pipeline(validate_input(data))
            sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            return 0
        except Exception:
            return 2
    origins = args.ui_origin or ['http://127.0.0.1:8000', 'http://localhost:8000']
    for origin in origins:
        try:
            url = urlsplit(origin)
            valid = (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost')
                     and url.port and not url.username and not url.password and not url.path and not url.query and not url.fragment)
        except ValueError:
            valid = False
        if not valid:
            parser.error('UI 주소는 포트를 포함한 로컬 HTTP 주소여야 합니다.')
    if not 1 <= args.port <= 65535:
        parser.error('포트 범위를 확인해 주세요.')
    try:
        server = LocalServer(args.port, origins)
    except OSError:
        print('로컬 서버를 시작하지 못했습니다. 사용 중인 포트인지 확인해 주세요.', file=sys.stderr)
        return 1
    print(f'Local-only API: http://127.0.0.1:{args.port}{API_PATH}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
