# 챗봇 운영 소스와 재배포 기준

## 확인한 범위 (2026-11-10)

읽기 전용 AWS 조회로 실행 코드 6개, 비공개 자료 9개, 웹 UI 3개의 SHA-256이
`source-manifest.json`과 일치함을 확인했다. 서비스·소켓 파일은 서버 내부 값으로
렌더링한 두 템플릿과 바이트 단위로 일치했다. Waitress는 3.0.2다.
이것은 모든 서버 파일이나 운영 DB를 Git과 동일하게 만든다는 의미가 아니다.
이번 소스 정리는 운영 서버를 변경하지 않는다.

## 공개 소스와 비공개 자료

- 루트 `Dockerfile`이 `index.html`, `assets/chat-ui.js`, `assets/chat-ui.css`를 포함한다.
  기존 이미지의 쓰기 계층에만 있던 UI가 향후 새 이미지에도 포함된다.
- Python 실행 코드 3개는 `scripts/`, 운영 진입점 3개는 이 디렉터리에 있다.
- 승인 스냅샷·원문·추출문 9개는 **새로 공개하지 않는다**. 공개 피드만으로는
  챗봇을 재현할 수 없다. 서버의 기존 읽기 전용 자료 또는 허가된 비공개 백업이 필요하다.
  이 자료의 재배포 권한이 확인됐다고 주장하지 않는다.
- `source-manifest.json`은 파일 경로·해시만 포함한다. 운영 DB·로그·인증서·키·
  실제 서비스 계정/경로/내부 IP 설정은 커밋하지 않는다.
- 기존 3건은 원문 발췌 23구간, 나머지 8건은 승인 요약 47구간이다. 승인 요약을
  최신 원문 전체 검증 또는 직접 인용으로 표시하지 않는다.
- 자료 갱신은 자동 반영되지 않는다. 승인·공개 상태와 근거를 다시 검토하고
  고정 해시 및 검색 사례를 검증한 뒤 별도로 배포해야 한다.

## 비공개 릴리스 조립 (로컬, 서비스 변경 없음)

```text
python -B deploy/chatbot/stage_host_release.py --private-corpus PRIVATE_INPUT --output NEW_PRIVATE_RELEASE
python -B deploy/chatbot/check_source.py --release NEW_PRIVATE_RELEASE
```

입력에는 manifest의 `private_corpus` 9개 상대 경로가 모두 있어야 한다.
출력은 저장소 밖의 새 비공개 디렉터리여야 한다. 허용된 15개 파일만 복사하며
승인·해시 및 3건/23구간·11건/70구간 검증에 실패하면 배포하지 않는다.
해시가 다르면 무조건 새 값을 받아들이지 말고 승인 근거부터 검토한다.

## 호스트 서비스 재구성 (추후 승인된 배포에 한함)

1. 기존 웹 이미지·컨테이너 실행 옵션·전체 Nginx 설정·인증서/공개 피드 마운트·
   API 릴리스·venv·두 systemd unit을 비공개로 백업한다. 수집·DB는 변경하지 않는다.
2. 별도 로그인 불가 계정과 venv를 재사용한다. 새 venv가 필요하면 격리 경로에
   `python -m pip install --require-hashes -r deploy/chatbot/requirements.txt`로 설치한다.
   전역/수집용 Python은 변경하지 않는다. 자료는 root 소유·서비스 계정 읽기만 허용한다.
3. 실제 Docker gateway·Nginx 컨테이너 IP·bridge interface·릴리스/venv 경로·전용 계정을
   확인한다. 저장소 밖 비공개 JSON에 `RELEASE_DIR`, `VENV_DIR`, `SERVICE_USER`,
   `BRIDGE_GATEWAY`, `NGINX_PEER`, `BRIDGE_INTERFACE` 여섯 문자열만 설정한다.
4. `python -B deploy/chatbot/render_units.py --settings PRIVATE_SETTINGS --output NEW_PRIVATE_UNITS`
   로 후보만 만든다. `systemd-analyze verify`로 검사한 후에만 설치한다.
   unit의 trial 문구는 검증된 운영 파일에 남아 있는 설명이며 개발 서버를 뜻하지 않는다.
5. 두 unit을 설치하고 daemon-reload 후 socket/service를 시작한다. PrivateNetwork,
   connect 금지, 상속 소켓 FD3, 실제 peer 제한, 메모리 128MiB·스왑 0을 확인한다.
   API 키·collector.env·운영 DB를 전달하지 않는다. 외부 8765는 열지 않는다.
6. 기존 전체 Nginx 후보에 http/domain/IP 조각만 병합한다. placeholder를 실제 private
   gateway로 치환한다. 기존 TLS·ACME·공개 피드·SEO 설정을 보존한다. 실제 마운트 경로와
   후보 전체 설정으로 `nginx -t`를 통과한 경우에만 원자적으로 반영하고 reload한다.
7. canonical HTTPS에서 Origin 헤더를 포함한 POST로 부안·고창·파주 및 11건을 확인한다.
   IP 사이트의 채팅은 404가 정상이다. 도메인/IP HTTPS·공개 피드·기존 메뉴·모바일과
   API 메모리/OOM·DB/승인 건수·수집/인증서 타이머 보존을 전후 대조한다.

## 웹 이미지 재생성 주의

루트에서 `docker build -t REVIEWED_WEB_IMAGE .`로 빌드한다. API·비공개 RAG 자료를
Nginx 이미지에 넣지 않는다. `.dockerignore`는 SEO·Google/Naver 확인 파일을 허용한다.
Docker가 없는 개발 PC에서는 실제 빌드 성공으로 보고하지 않는다.

기존 TLS 설정·인증서·ACME·공개 피드의 마운트와 포트/재시작 옵션은 별도로 복원해야 한다.
**컨테이너 재생성 시 IP가 바뀔 수 있다.** 기존 PeerOnly는 실제 소켓 상대 IP를 검사한다.
새 IP와 bridge를 확인해 API 템플릿 및 필요한 프록시를 재검증하지 않으면 채팅이 차단된다.
차단을 풀려고 `0.0.0.0`, 임의 peer 허용, connect 제한 해제를 사용하지 않는다.

## 롤백

API 변경 실패 시 새 socket/service만 중지하고 이전 릴리스·unit·venv를 복원한 뒤
daemon-reload 및 기존 API만 시작한다. Nginx 변경 실패 시 백업한 전체 설정을 복원하고
`nginx -t` 후 reload한다. 웹 변경 실패 시 백업 웹 파일 또는 이전 이미지와 **동일한**
마운트·네트워크·옵션으로 복구한다. 컨테이너 교체를 기본 복구 수단으로 사용하지 않는다.
DB·승인·수집·인증서 갱신 설정은 롤백 대상이 아니다. 백업 원문/로그는 Git에 올리지 않는다.
이 문서는 수동 절차이며 AWS에서 이번에 재배포·롤백을 실행했다는 뜻이 아니다.
