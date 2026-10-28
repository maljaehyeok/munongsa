# AWS 수집 운영 전환

현재는 준비 단계이며 설치·예약 활성화는 승인 후에만 실행합니다.

- Python 3.10 이상, 기존 `ubuntu` 계정, 기존 Docker/Nginx 사용.
- 비공개 DB·권한 명세·백업·로그: `/var/lib/munongsa` (700).
- 공개 마운트: `/var/lib/munongsa-public`의 `support-public.json` 하나만 읽기 전용으로 제공.
- 시험 DB를 복사하지 않으며 빈 운영 검토 DB에서 시작합니다.
- 수집은 승인 상태를 만들지 않습니다. 기존 `support_monitor.py review/publish`, `support_eligibility.py`로 사람이 검토하고, 공고별 공개 이용 근거를 비공개 `publication-rights.json`에 기록해야 출력됩니다.
- 참고 승인은 추천과 분리됩니다. 추천은 기존 기간·조건 검증과 승인 및 조건 버전 결합 검사를 모두 유지합니다.
- 모든 신청 자격을 확인해야 공고를 안내할 수 있는 것은 아닙니다. 기관·사업명·공식 공고 근거만 사람이 확인한 경우 `review --notice-basics-verified --verification-status verified`로 기본 사실의 확인 범위를 기록할 수 있습니다. 근거 URL·위치·검토자·사유는 필수이며, 이 명령만으로 공개 승인되지는 않습니다.
- 이후 `approved_reference`와 공고별 공개 이용 근거를 모두 충족하면 `공식 공고 안내`로 출력합니다. 미확인 자격은 그대로 유지하고 확인된 조건만 비교합니다. `approved` 추천의 자격·기간 검증 요건은 유지합니다.
- 인증키는 필요할 때만 서버의 `/etc/munongsa/collector.env`에 설정합니다. 파일은 `root:root`, 600이며 저장소에 넣지 않습니다. 기업마당은 현재 비활성입니다.

## 실행과 확인

수동 실행: `.venv-collector/bin/python -B scripts/run_support_collection.py --live`

승인 후 출력 갱신: 같은 명령의 `--live` 대신 `--export-only` 사용.

로그: `journalctl -u munongsa-collector.service`와 `/var/lib/munongsa/logs/`.
종료 코드: 0 정상·당일 생략, 1 일부 기관 실패, 2 치명 오류, 3 잠금 중복 실행.
기관 실패는 다른 기관의 저장 결과를 취소하지 않습니다. 자동 재시도는 없으며 로그 확인 후 필요한 경우 `--force`로 재실행합니다.

예약 파일을 설치하는 것과 활성화는 별개입니다. 승인·수동 수집·홈페이지 확인 후에만 `sudo systemctl enable --now munongsa-collector.timer`를 실행합니다. 매일 한국시간 07:00, 서버 중지 중 놓친 실행은 재시작 후 한 번 실행합니다.

## 배포·복구

`deploy/collector/prepare-release.sh`는 승인된 커밋의 서버 반영 후 `--apply-approved`와 전체 커밋 해시를 지정해야 실행됩니다. 기존 컨테이너 설정이 예상과 다르면 교체 전에 중단합니다. 컨테이너·이미지·공개 파일을 보존하고 새 컨테이너를 임시 포트에서 검사한 뒤 교체합니다. 타이머를 자동 활성화하지 않습니다.

복구 시 새 타이머·수집 서비스를 중지하고, 출력된 기존 컨테이너 이름을 `munongsa`로 복원하여 시작합니다. 기존 이미지를 삭제하거나 DB를 과거 백업으로 덮어쓰지 않습니다. DB 복구가 필요한 경우 먼저 실행을 중지하고 별도 복사본에서 `PRAGMA integrity_check`와 이력 확인 후 결정합니다.

현재 코드·단위 파일은 로컬 검증 대상입니다. 실제 서버 권한·메모리·디스크·백업·systemd 실행은 서버 접속 후 별도로 확인해야 합니다. 백업 자동 삭제는 없으므로 디스크 사용량과 보존 기간을 운영자가 정해야 합니다.

사전 점검: 일반 PowerShell에서 `python -B deploy/collector/check_server.py --ssh`를 실행합니다. Git 원격 조회와 SSH의 컨테이너·파일 메타데이터·백업 경로 조회만 수행합니다. Git 인덱스 갱신·호스트키 자동 등록·SSH 에이전트 키 추가도 비활성화했습니다. SSH 인증 로그와 HTTP GET 접근 로그 같은 정상적인 시스템 기록은 남을 수 있습니다.

최종 격리 검증은 같은 명령에 `--preflight`를 추가합니다. 선별된 34개 소스만 SSH로 임시 디렉터리에 전달하고, 임시 가상환경의 의존성 설치·빈 SQLite 재실행과 백업 복원·루프백 임시 컨테이너의 홈페이지 복원을 검사합니다. 기존 이미지만 사용하며 새 이미지 다운로드·운영 컨테이너 교체·정기 실행 설정은 하지 않습니다. 임시 컨테이너는 메모리 128MB·CPU 0.25개로 제한하고 검증 후 제거합니다. 실패 시 실제 배포는 중단합니다.

venv 지원 패키지의 최소 설치를 별도로 승인받은 경우에만 `--preflight --prepare-python-approved`를 사용합니다. Ubuntu/Python 버전과 설치 상태를 조회한 뒤 APT 모의 실행으로 기존 패키지 변경이 없는지 확인합니다. 해당 Python 버전의 venv 및 필요한 pip/setuptools wheel 패키지만 새로 설치할 수 있으며, 예상 밖 의존성·업그레이드·삭제·용량 부족은 중단합니다. 정확한 버전과 제한된 APT 정책으로 두 번째 모의 실행 후 설치하며, 저장소 갱신·서비스 재시작·예약 활성화는 하지 않습니다. 설치 결과와 격리 검사는 동일한 JSON 보고서에 기록됩니다. 기본 `--ssh` 조회에는 이 설치 과정이 포함되지 않습니다.
