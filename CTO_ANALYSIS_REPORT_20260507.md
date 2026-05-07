# MH_DASHBOARD — CTO 관점 정밀 진단 보고서

**기준일:** 2026-05-07  
**대상 프로젝트:** guidbot (Hospital Management Dashboard + RAG Chatbot)  
**분석 규모:** ~32,000 LOC / 61개 Python 파일 / 4개 앱 진입점  
**작성:** Claude Code (Anthropic)

---

## EXECUTIVE SUMMARY

> **운영 투입 가능 여부 → ❌ 조건부 가능 (현재 상태로는 불가)**

이 프로젝트는 설계 방향성은 훌륭하다. Pydantic v2 설정 관리, 스레드 안전 싱글톤, Oracle VIEW 기반 보안 격리, PII 마스킹 프레임워크 등 실무 경험이 녹아 있다. 그러나 **기본 비밀번호 하드코딩, 테스트 부재, Docker/CI 없음, SQL Injection 방어 불완전** 등 운영 투입 전 반드시 해결해야 할 Critical 이슈가 존재한다. 특히 병원 전산 환경의 개인정보보호법 기준으로 보면 현재 상태는 **인증 심사 통과 불가** 수준이다.

### 종합 점수 요약

| 평가 항목 | 점수 (/100) | 등급 |
|---|---|---|
| 기술부채 총점 | 58 | C |
| 유지보수성 | 62 | C+ |
| 확장성 | 55 | C |
| 안정성 | 48 | D+ |
| 보안성 | 52 | C |

---

## 목차

1. [프로젝트 구조 분석](#1-프로젝트-구조-분석)
2. [코드 품질 진단](#2-코드-품질-진단)
3. [성능 분석](#3-성능-분석)
4. [DB 및 SQL 구조 분석](#4-db-및-sql-구조-분석)
5. [보안 점검](#5-보안-점검)
6. [아키텍처 평가](#6-아키텍처-평가)
7. [운영 관점 진단](#7-운영-관점-진단)
8. [기술부채 평가](#8-기술부채-평가)
9. [최우선 개선 TOP 10](#9-최우선-개선-top-10)
10. [리팩토링 로드맵](#10-리팩토링-로드맵)
11. [총평](#11-총평--운영-투입-가능성-판정)

---

## 1. 프로젝트 구조 분석

### 1-1. 앱 구조 개요

| 앱 | 포트 | 역할 |
|---|---|---|
| `main.py` | 8502 | AI 챗봇 + RAG |
| `dashboard_app.py` | 8501 | 병동/입원 대시보드 |
| `finance_app.py` | 8503 | 원무/수납 대시보드 |
| `admin_app.py` | 8504 | 관리자 패널 |

### 1-2. 디렉토리 구조

```
guidbot/
├── config/          # 설정 관리 (pydantic-settings v2)
├── core/            # RAG 파이프라인, LLM 클라이언트
├── db/              # Oracle 접근, PII 마스킹, 스키마
├── llm/             # SQL 생성기, 데이터 설명기
├── ui/              # Streamlit 대시보드 (finance/, panels/, 등)
├── services/        # 비즈니스 서비스 (부분 구현)
├── utils/           # 로깅, 파일 동기화, 자동 백업
├── scripts/         # 디버그, 빌드 유틸리티
├── docs/            # 1,000+ PDF 병원 규정 문서  ← ⚠️ 소스코드와 혼재
└── tests/           # rag_benchmark.py 1개만 존재  ← ⚠️ 사실상 없음
```

### 1-3. 항목별 진단표

| 항목 | 현재 상태 | 문제점 | 위험도 | 개선안 |
|---|---|---|---|---|
| **디렉토리 구조** | 9계층 기능별 분리 | `docs/` 에 1,000+ PDF 가 소스코드와 같은 레포 — git clone 시 수십 GB | 🟠 HIGH | docs/는 NAS/S3 분리, 코드만 git 관리 |
| **앱 진입점** | 4개 독립 프로세스, 포트 분리 | config/settings.py 공유하나 런타임 설정 변경이 즉각 전파 안 됨 | 🟡 MEDIUM | 공유 설정은 Redis/환경변수 기반으로 런타임 공유 |
| **모듈 분리** | `ui/finance/tab_*.py` 분리 양호, finance_dashboard.py 는 얇은 라우터 | `ui/panels/_shared.py` 가 Oracle SQL 딕셔너리 + 캐시 래퍼 + 날짜 유틸 혼재 | 🟡 MEDIUM | FQ dict → `db/queries.py`, 캐시 래퍼 → `db/cache_layer.py` 분리 |
| **레이어 구조** | UI → _shared.py → OracleClient 2.5계층 | 비즈니스 로직이 UI 레이어에 혼재. Service 레이어 없음 | 🟠 HIGH | UI → Service → Repository → DB 4계층 도입 |
| **의존성 관리** | requirements.txt 42개 패키지 단일 파일 | dev/prod 의존성 미분리. 버전 핀닝 (`==`) 미적용 시 업그레이드 사고 위험 | 🟡 MEDIUM | `requirements-base.txt` / `-dev.txt` / `-prod.txt` 분리 + `==` 핀닝 |
| **환경설정** | pydantic-settings v2, SecretStr 활용 우수 | `admin_password: SecretStr = Field(default=SecretStr("moonhwa"))` 하드코딩 | 🔴 CRITICAL | `default` 제거, required 필드로 변경, .env 없으면 앱 시작 실패 |
| **공통 모듈** | `ui/design.py` 색상/CSS 단일 소스 | 하위 호환 별칭 (`_kpi_card` 등) 100+ 곳에서 사용. Phase 2 리팩토링 주석 누적 → 사실상 영구화 위험 | 🟡 MEDIUM | alias 제거 마감일 설정, 일괄 직접 호출로 변환 |
| **중복 코드** | sys.path insert 패턴 40+ 파일 반복 | 실행 환경에 따라 경로 계산 오류 가능 | 🟡 MEDIUM | `guidbot/` 패키지 설치 (`pip install -e .`), sys.path 조작 전면 제거 |
| **배포 설정** | .streamlit/config.toml 존재. Dockerfile 없음 | 배포 자동화 0%. 운영 서버 설정이 구두 전달 또는 수동 | 🔴 CRITICAL | Dockerfile + docker-compose + GitHub Actions 즉시 작성 |

---

## 2. 코드 품질 진단

| 파일/모듈 | 문제 내용 | 심각도 | 개선 방향 |
|---|---|---|---|
| `config/settings.py:653` | `default=SecretStr("moonhwa")` — .env 없는 환경에서 기본 비밀번호로 관리자 패널 접근 가능 | 🔴 CRITICAL | `default` 제거. 미설정 시 `SystemExit` 처리 |
| `core/llm.py:88` | `"temperature": 0.1` 하드코딩. `settings.llm_temperature` 설정이 있음에도 무시됨 | 🟠 HIGH | `"temperature": settings.llm_temperature` 로 교체 |
| `ui/finance/tab_*.py` 전체 | 파일 상단 sys.path 조작 코드 40개 파일에 반복 | 🟡 MEDIUM | 패키지화 후 전면 제거 |
| `ui/finance_dashboard.py` | `with t1:` 블록 내 10개 `_fq()` 직렬 실행 — 탭 열릴 때마다 Oracle 쿼리 10개 순차 실행 | 🟠 HIGH | `ThreadPoolExecutor` 병렬 실행으로 전환 |
| `ui/admin_dashboard.py` | `Path.rglob("*.pdf")` 를 매 렌더링마다 호출. 수천 파일 존재 시 렌더링 지연 | 🟠 HIGH | `@st.cache_data(ttl=300)` 추가 |
| `utils/auto_backup.py` | `shutil.rmtree()` 호출 전 경로 트래버설 방어 없음 | 🟡 MEDIUM | backup_dir 가 settings.backup_dir 의 하위인지 검증 후 실행 |
| `core/rag_pipeline.py` | `reset()` 시 `_retriever = None` 설정 직후 다음 요청이 들어오면 None 상태에서 추론 시도 가능 | 🟡 MEDIUM | reset 중 lock 유지, 완료 후 release. Blue/Green 전환 패턴 |
| `llm/sql_generator.py:64-106` | UNION SELECT 패턴 차단 의도적 미적용. 정규식 기반 SQL 검증은 comment-based bypass 취약 | 🔴 CRITICAL | `sqlparse` 라이브러리 사용, 화이트리스트 테이블 강제 적용 |
| `db/oracle_client.py:349-352` | Oracle 11.2 / Thin 모드에서 `callTimeout` 미적용 → 쿼리 무한 대기 가능 | 🟠 HIGH | 타임아웃 미적용 경고 로그 필수. 네트워크 레벨 타임아웃 병행 |
| `tests/` 폴더 | `rag_benchmark.py` 1개만 존재. 전체 비즈니스 로직 테스트 커버리지 **0%** | 🔴 CRITICAL | 핵심 모듈 최소 60% 커버리지 확보 |
| `ui/finance/tab_chat.py` (신규) | `build_ctx_*()` 컨텍스트 빌더가 UI 레이어에 위치. 비즈니스 로직이 UI에 혼재 | 🟡 MEDIUM | `services/finance_service.py` 로 이동 |
| 전체 코드베이스 | docstring 한국어·영어 혼재. 일부 함수 docstring 없음 | 🟡 MEDIUM | 문서화 규칙 통일(한국어 우선) + pre-commit 훅으로 강제 |

### 2-1. 안티패턴 요약

```python
# ❌ 현재 — 40개 파일에 반복되는 sys.path 조작
_PR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../.."))
if _PR not in sys.path:
    sys.path.insert(0, _PR)

# ✅ 개선 — setup.py / pyproject.toml 로 패키지 설치
# pip install -e . 후 어디서든 import guidbot.xxx 가능

# ❌ 현재 — 온도 하드코딩
cfg = {"temperature": 0.1}

# ✅ 개선
cfg = {"temperature": settings.llm_temperature}

# ❌ 현재 — 기본 비밀번호
admin_password: SecretStr = Field(default=SecretStr("moonhwa"))

# ✅ 개선
admin_password: SecretStr = Field(...)  # required; .env 없으면 ValidationError
```

---

## 3. 성능 분석

| 영역 | 현재 방식 | 문제점 | 예상 영향 | 개선안 |
|---|---|---|---|---|
| **실시간 탭 Oracle 쿼리** | `with t1:` 블록에서 10개 `_fq()` 직렬 실행 | 쿼리 평균 200ms × 10 = **2초+ 렌더링 지연**. 동시 사용자 5명이면 DB 커넥션 50개 소비 | 페이지 응답 2-5초, Oracle pool 고갈 | `ThreadPoolExecutor(max_workers=5)` 병렬 실행 |
| **`_fq()` 캐시 TTL** | `@st.cache_data(ttl=1800)` 전체 동일 적용 | 실시간 현황 VIEW는 1분 단위 변동. 30분 캐시는 **실시간성 파괴** | 간호사·원무 직원이 최대 29분 전 데이터로 업무 판단 | 실시간 VIEW ttl=60, 주간/월간 분석 ttl=1800 으로 분리 적용 |
| **`V_MONTHLY_OPD_DEPT` 전체 조회** | 이전: `SELECT * ... ORDER BY` WHERE 없는 전체 스캔 | 뷰 베이스 테이블 Full Table Scan + Sort. 수십만 건 시 3-10초 | DB CPU 급등, 전체 사용자 응답 지연 | Lazy Loading 적용 완료(2026-05-07). 뷰 DDL 날짜 인덱스 추가 요청 필요 |
| **RAG 임베딩 캐시** | 인메모리 LRU 200개. 재시작 시 초기화 | 콜드 스타트 시 첫 200 쿼리 느림 | 서버 재시작 직후 응답시간 1-3초 | `joblib.dump()` 로 파일 영속화 |
| **FAISS 인덱스 재로딩** | `reset()` 시 전체 FAISS 재로딩. 재구축 중 블로킹 | 인덱스 크기 따라 10-60초 블로킹. 재구축 중 챗봇 서비스 중단 | 관리자 재구축 클릭 시 30-60초 서비스 완전 중단 | 비동기 재구축 + 구 인덱스 유지 → atomic swap 패턴 |
| **세션 상태 비대화** | `st.session_state['fin_weekly_data']` 에 Oracle 결과 rows 전체 저장 | 수천 rows × 동시 사용자 수 = 수 GB RAM 소비 가능 | 동시 사용자 20명 시 메모리 부족, OOM 가능 | 세션에는 요약 집계(수백 bytes)만 저장, 원본은 `@st.cache_data` 레이어 유지 |
| **LLM 응답 스트리밍** | 토큰 4개마다 `st.markdown()` (전체 문자열 DOM 교체) | 100토큰 응답 시 25회 DOM 업데이트 | 브라우저 렌더링 버벅임, 긴 응답에서 CPU 급등 | 토큰 16-32개마다 업데이트로 조정 |
| **파일시스템 스캔** | `Path.rglob("*.pdf")` 를 admin 페이지 매 렌더링 호출 | 1,000+ 파일 시 100ms+. NFS/네트워크 드라이브 마운트 시 수초 지연 | admin 페이지 응답 느림 | `@st.cache_data(ttl=300)` 추가 |
| **자동 백업 스케줄러** | `threading.Thread(daemon=True)` — `shutil.copytree()` 동기 I/O | 수 GB 인덱스 백업 중 GIL 경쟁으로 메인 스레드 영향 가능 | 백업 중 챗봇 응답 2-10초 지연 | `multiprocessing` 또는 야간 cron으로 분리 |

### 3-1. 병렬화 개선 예시

```python
# ❌ 현재 — 10개 쿼리 직렬 실행
dept_status  = _fq('opd_dept_status')
kiosk_status = _fq('kiosk_status')
discharge    = _fq('discharge_pipeline', _q)
# ... 7개 더

# ✅ 개선 — ThreadPoolExecutor 병렬 실행
from concurrent.futures import ThreadPoolExecutor, as_completed

REALTIME_QUERIES = {
    'opd_dept_status':    (False,),
    'kiosk_status':       (False,),
    'discharge_pipeline': (True,),   # _q 필요
    'ward_bed_detail':    (True,),
    'ward_room_detail':   (False,),
    'daily_dept_stat':    (True,),
    'day_inweon':         (True,),
    'opd_dept_trend':     (True,),
    'kiosk_by_dept':      (True,),
    'kiosk_counter_trend':(True,),
}

with ThreadPoolExecutor(max_workers=5) as ex:
    futs = {
        k: ex.submit(_fq, k, _q if needs_q else '')
        for k, (needs_q,) in REALTIME_QUERIES.items()
    }
    results = {k: f.result() for k, f in futs.items()}
```

---

## 4. DB 및 SQL 구조 분석

| SQL/테이블 | 문제 | 위험도 | 개선 SQL 또는 개선 구조 |
|---|---|---|---|
| `SELECT * FROM V_OPD_KPI WHERE ROWNUM = 1` | SELECT * 는 뷰 컬럼 변경 시 애플리케이션 파싱 오류 유발 | 🟡 MEDIUM | `SELECT 외래건수, 입원건수, ... FETCH FIRST 1 ROWS ONLY` 명시적 컬럼 지정 |
| `V_MONTHLY_OPD_DEPT` 전체 조회 (이전) | WHERE 없는 전체 스캔. 인덱스 없으면 Full Table Scan + Sort | 🔴 CRITICAL | Lazy Loading 적용 완료(2026-05-07). 뷰 베이스 테이블 `기준년월` 인덱스 DBA 요청 |
| `SELECT * FROM ALL_TABLES WHERE OWNER = :owner` | ALL_TABLES 메타데이터 조회 — 시스템 딕셔너리 락 경쟁 가능 | 🟡 MEDIUM | TTL 600초 이상 캐시. `USER_TABLES` 사용 시 락 감소 |
| **LLM 생성 SQL — UNION 미차단** | `UNION SELECT 1, USER, password FROM DUAL` 형태 injection 가능 | 🔴 CRITICAL | `sqlparse` 기반 파서 + SELECT-only 강제 + FROM 절 화이트리스트 |
| **Oracle 연결 풀 고갈** | pool_max=10, `acquire_timeout` 미설정 | 🟠 HIGH | `acquire_timeout=5.0` 설정, 초과 시 사용자에게 안내 메시지 |
| **복구 로직 — `shutil.rmtree()` 중간 실패** | 삭제 후 copytree 중 실패 시 빈 디렉토리 상태 (복구 불가) | 🔴 CRITICAL | 임시 경로에 copytree 완료 후 `os.rename()` (atomic). 실패 시 원본 유지 |
| Oracle 트랜잭션 | `execute_query()` 는 SELECT 전용. DML 구조 없음 | 🟡 MEDIUM | 현재 READ-ONLY 안전. 향후 DML 추가 시 명시적 BEGIN/COMMIT/ROLLBACK 필수 |
| 뷰 기반 접근 패턴 | 모든 조회가 JAIN_WM 스키마 VIEW 경유 | 🟢 GOOD | 현재 패턴 유지. 원본 테이블 구조 격리 우수 |
| N+1 문제 | 반복 내 execute_query 호출 없음. 단일 뷰 단일 쿼리 패턴 | 🟢 GOOD | 현재 구조 유지 |
| 테이블 파티셔닝 | 월별 집계 테이블 파티셔닝 전략 미확인 | 🟠 HIGH | DBA에 `기준년월` 기준 Range Partition 요청. 쿼리 성능 30-70% 향상 예상 |

### 4-1. SQL 보안 개선 예시

```python
# ❌ 현재 — 정규식 기반 SQL 검증 (UNION 미차단)
_DANGEROUS_PATTERNS = [
    (re.compile(r"\bINSERT\b", re.IGNORECASE), "INSERT 차단"),
    (re.compile(r"\bDROP\b",   re.IGNORECASE), "DROP 차단"),
    # UNION은 의도적으로 미차단 ← 취약점
]

# ✅ 개선 — sqlparse 기반 구조적 검증
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML

def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    parsed = sqlparse.parse(sql.strip())
    if not parsed:
        raise ValueError("빈 SQL")

    stmt = parsed[0]
    # 1. SELECT 문만 허용
    if stmt.get_type() != 'SELECT':
        raise ValueError(f"SELECT 문만 허용: {stmt.get_type()}")

    # 2. 서브쿼리 내 UNION 차단
    flat_tokens = list(stmt.flatten())
    for tok in flat_tokens:
        if tok.ttype is Keyword and tok.normalized in ('UNION', 'INTERSECT', 'EXCEPT'):
            raise ValueError(f"{tok.normalized} 연산자 차단")

    # 3. 테이블 화이트리스트 검증
    for table in extract_tables(stmt):
        if table.upper() not in allowed_tables:
            raise ValueError(f"허용되지 않은 테이블: {table}")

    return sql
```

---

## 5. 보안 점검

| 취약 항목 | 현재 상태 | 위험도 | 개선안 |
|---|---|---|---|
| **기본 관리자 비밀번호** | `settings.py:653` — `default=SecretStr("moonhwa")`. .env 미설정 시 기본값으로 관리자 패널 접근 가능 | 🔴 CRITICAL | `default` 제거. 앱 시작 시 .env 확인, 미설정 시 `SystemExit` |
| **SQL Injection (LLM 생성)** | 정규식 다층 방어 존재. UNION SELECT 의도적 미차단. 화이트리스트 선택적 설정 | 🔴 CRITICAL | sqlparse 사용, 화이트리스트 **필수** 설정으로 변경, UNION 차단 |
| **XSS** | `unsafe_allow_html=True` 60+ 곳 사용. 사용자 입력이 HTML에 직접 삽입되는 경로 존재 가능 | 🟠 HIGH | 사용자 입력값은 `html.escape()` 후 삽입. LLM 응답도 sanitize |
| **PII LLM 전달** | `pii_masker.py` 존재. 대시보드 context builder 에서 마스킹 적용 여부 코드 경로별 미검증 | 🟠 HIGH | `context_builder.py` 전체 리뷰. LLM 전달 전 PII 컬럼 자동 마스킹 강제 |
| **Pickle 역직렬화** | `core/hybrid_retriever.py` — `pickle.load(f)` 로 FAISS 인덱스 로드. 신뢰된 경로이므로 현재는 안전 | 🟡 MEDIUM | `faiss.read_index()` + 별도 JSON 메타로 pickle 제거. 또는 파일 SHA256 무결성 체크 |
| **관리자 세션 만료** | `adm_authed` session_state 설정 후 만료 없음. 브라우저 탭 닫아도 재접속 시 재인증 불필요 가능 | 🟠 HIGH | `adm_login_time` 비교, 30분 후 자동 로그아웃 로직 추가 |
| **파일 업로드 검증** | PDF 업로드 시 확장자 확인. MIME 타입 검증 여부 불명 | 🟡 MEDIUM | `python-magic` 으로 실제 MIME 타입 검증. 파일명 `../` 경로 트래버설 방어 |
| **환경변수 노출** | `.env` 파일 git 추적 제외 여부 확인 필요 | 🟠 HIGH | `.gitignore` 에 `.env` 확인. `git-secrets` 또는 `pre-commit` 훅으로 비밀 커밋 방지 |
| **로그 PII 노출** | `query_audit.log` 에 실행 SQL 전체 기록. SQL 파라미터 값에 주민번호 등 포함 시 로그에 PII 저장 | 🟠 HIGH | 로그 기록 전 SQL 파라미터 값 마스킹 적용 |
| **CSRF** | Streamlit 단일 페이지 앱. 전통적 CSRF 벡터 낮음. iframe 임베딩 공격 가능 | 🟡 MEDIUM | `.streamlit/config.toml` 에 `[server] enableCORS = false`, X-Frame-Options 헤더 추가 |
| **HTTPS 미적용** | 배포 설정 파일 없음. HTTP 운영 시 Oracle 비밀번호, API 키 평문 전송 | 🔴 CRITICAL | Nginx 리버스 프록시 + 병원 내부 CA 인증서 또는 Let's Encrypt |
| **관리자 권한 분리** | admin_app.py 단일 비밀번호 → 모든 관리 기능 접근. 권한 등급 없음 | 🟡 MEDIUM | 뷰어/편집자/관리자 3단계 역할 기반 권한. 벡터DB 재구축은 최고 권한만 |
| **HMAC 비밀번호 비교** | `hmac.compare_digest()` 사용 — 타이밍 공격 방어 | 🟢 GOOD | 현재 패턴 유지 |
| **SecretStr 활용** | API 키, DB 비밀번호 모두 SecretStr — repr/로그 자동 마스킹 | 🟢 GOOD | 현재 패턴 유지 |

### 5-1. 즉시 적용 보안 패치

```python
# ❌ 현재 config/settings.py:653
admin_password: SecretStr = Field(
    default=SecretStr("moonhwa"),  # 기본 비밀번호 — 절대 안 됨
    description="관리자 비밀번호",
)

# ✅ 수정 (30분 작업)
admin_password: SecretStr = Field(
    ...,  # required — .env 에 ADMIN_PASSWORD= 반드시 설정
    description="관리자 비밀번호 (.env 에 ADMIN_PASSWORD= 설정 필수)",
)
```

```python
# ✅ 관리자 세션 만료 추가 (admin_app.py)
from datetime import datetime, timedelta

def _check_session_valid() -> bool:
    if not st.session_state.get("adm_authed"):
        return False
    login_time_str = st.session_state.get("adm_login_time", "")
    try:
        login_time = datetime.fromisoformat(login_time_str)
        if datetime.now() - login_time > timedelta(minutes=30):
            st.session_state.pop("adm_authed", None)
            return False
    except Exception:
        return False
    return True
```

---

## 6. 아키텍처 평가

| 항목 | 현재 평가 | 개선 권장사항 |
|---|---|---|
| **현재 아키텍처 스타일** | Streamlit 기반 모놀리식 멀티앱. 4개 독립 프로세스(포트 분리). Shared Nothing 패턴 | 현재 규모(병원 1개, 동시 사용자 20명 이하)에 적합. 급격한 MSA 전환 불필요 |
| **레이어 구조** | UI → _shared.py → OracleClient 2.5계층. Service 레이어 없음 | `services/finance_service.py`, `services/ward_service.py` 등 비즈니스 로직 격리 |
| **RAG 아키텍처** | FAISS + sentence-transformers + Gemini. CrossEncoder 재순위. 부서별 서브인덱스 | 현재 구조 양호. 부서 수 100+ 시 pgvector 또는 Chroma 전환 검토 |
| **LLM 통합** | Gemini 단일 제공자. 멀티키 풀링으로 할당량 대응 | `LLMProvider` 추상 인터페이스 → OpenAI/Claude 폴백 추가 |
| **상태 관리** | Streamlit session_state 전적 의존. 재시작 시 모든 상태 초기화 | 중요 상태(사용자 설정, 조회 필터)는 Redis 또는 DB 영속화 |
| **확장성 한계** | 동시 사용자 50명+ 시 Streamlit 단일 서버 CPU 포화. Oracle pool_max=10 병목 | `--server.numWorkers 4` 또는 Gunicorn+Uvicorn 전환. Oracle pool 동적 조정 |
| **MSA 전환 필요성** | 현재 규모 불필요. 무리한 MSA 도입 시 운영 복잡도만 증가 | 2-3년 후 다병원 확장 시 RAG 서비스 ↔ 대시보드 서비스 분리 고려 |
| **캐시 구조** | `@st.cache_data` + 인메모리 LRU(임베딩 캐시) 2계층. Redis 없음 | 현재 단일 서버로 충분. 다중 서버 배포 시 Redis 전환 필수 |
| **비동기 처리** | 전체 동기 처리. LLM 스트리밍만 제너레이터 패턴 | 무거운 Oracle 쿼리는 `ThreadPoolExecutor` 병렬화 |
| **이벤트 기반** | 장시간 작업에 `threading.Thread` 사용 | Celery/RQ 도입 시 더 안정적. 현재 규모는 threading으로 충분 |

---

## 7. 운영 관점 진단

| 운영 항목 | 현재 상태 | 리스크 | 개선안 |
|---|---|---|---|
| **장애 대응** | Oracle 실패 시 demo mode 전환. 자동 복구 없음 | Oracle 복구 후에도 앱 재시작 전까지 demo mode 유지 | 헬스체크 루프(5분마다) → Oracle 복구 감지 시 자동 정상 모드 복귀 |
| **로그 체계** | TimedRotatingFileHandler 30일 보관. 텍스트 포맷 | Elasticsearch/Loki 연동 불가. grep 수동 분석만 가능 | JSON 구조화 로그 (structlog) + Loki/Grafana 연동 |
| **모니터링** | 없음. Streamlit 기본 URL만 존재 | 서버 다운을 관리자가 직접 접속해서 확인. 자동 알림 없음 | UptimeRobot(무료) + Prometheus metrics 엔드포인트 |
| **알림 시스템** | 없음 | 새벽 3시 Oracle 연결 끊겨도 아침 출근 후 인지 | 카카오알림톡 또는 이메일 SMTP 장애 알림 |
| **백업 전략** | `auto_backup.py` — 주 1회 자동, 최대 4주 보관. FAISS 인덱스만 | Oracle DB 자체 백업 미확인. PDF 원본 백업 전략 없음 | PDF 원본 → NAS 자동 동기화. Oracle → DBA팀 RMAN 백업 확인 |
| **배포 안정성** | `streamlit run main.py` 직접 실행 추정. 프로세스 관리자 없음 | 서버 재시작, 예외 종료 시 수동 재기동 필요 | `systemd` 서비스 등록 또는 `supervisord` 즉시 적용 |
| **롤백 전략** | 없음. `git reset` 수동 실행 | 배포 후 장애 시 수동 롤백. 실수로 main 직접 수정 가능 | git tag 기반 릴리즈. 롤백 스크립트 작성 |
| **CI/CD** | 없음 | 코드 리뷰 없이 main 브랜치 직접 push 가능. 테스트 없이 배포 | GitHub Actions: PR → lint+test → staging → prod |
| **Docker/K8s** | 없음 | 환경 재현 불가. Python/Oracle driver 버전 의존 | Dockerfile + docker-compose 최우선 작성 |
| **환경 분리** | `.env` 하나로 dev/prod 혼용 추정 | 개발 중 실수로 prod Oracle DB 접속 가능 | `.env.dev`, `.env.prod` 분리. `APP_ENV` 변수로 구분 |
| **자동 재시작** | 없음 | OOM, 예외 종료 시 서비스 즉시 중단 | `systemd Restart=always` 또는 Docker `restart: unless-stopped` |
| **Oracle 연결 복구** | 실패 시 None 반환 → 이후 모든 쿼리 실패 | Oracle RAC failover, 네트워크 순단 후 앱이 계속 None 상태 | 5분마다 재연결 시도 루프 추가 |

### 7-1. systemd 서비스 즉시 적용 예시

```ini
# /etc/systemd/system/mh-finance.service
[Unit]
Description=MH Finance Dashboard
After=network.target

[Service]
Type=simple
User=mh_service
WorkingDirectory=/opt/mh/guidbot
EnvironmentFile=/opt/mh/.env.prod
ExecStart=/opt/mh/venv/bin/streamlit run finance_app.py --server.port 8503
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
# 적용 명령 (2시간 작업)
sudo systemctl daemon-reload
sudo systemctl enable mh-finance mh-dashboard mh-chatbot mh-admin
sudo systemctl start mh-finance
```

---

## 8. 기술부채 평가

### 8-1. 종합 점수

| 평가 항목 | 점수 (/100) | 등급 | 근거 |
|---|---|---|---|
| **기술부채 총점** | **58** | C | Critical 이슈 4개, CI/CD·테스트·Docker 전무, 하드코딩 다수 |
| **유지보수성** | **62** | C+ | 모듈 분리 양호, 그러나 sys.path 40곳, 하위 호환 별칭 100+곳, Service 레이어 없음 |
| **확장성** | **55** | C | 단일 서버 Streamlit 한계, Redis 없음, 세션 상태 비대화, Oracle pool 고정 |
| **안정성** | **48** | D+ | 테스트 0%, Docker 없음, 모니터링 없음, 자동 재시작 없음, 기본 비밀번호 |
| **보안성** | **52** | C | PII 마스킹·HMAC·SecretStr 우수하나, SQL Injection 방어 불완전, HTTPS 미확인 |

### 8-2. 항목별 부채 상세

**유지보수 난이도 — 중상**
`finance_dashboard.py` 는 300줄 라우터로 정리됐으나, `ui/panels/_shared.py` 는 SQL 딕셔너리·캐시·날짜 유틸 혼재. 신입 개발자가 수정 포인트를 찾는 데 30분+ 소요.

**신규 기능 추가 난이도 — 중**
탭 추가는 `tab_*.py` 생성 + `__init__.py` + `finance_dashboard.py` 3곳 수정으로 일관성 있음. 단, Oracle 뷰 추가는 DBA 협업 필요해 리드타임 길다.

**장애 위험도 — 높음**
모니터링·알림 없음. Oracle 연결 끊김, LLM 할당량 소진을 실시간 감지 불가. 병원 원무 직원이 아침에 출근해서 "화면이 안 나와요"로 인지하는 구조.

**코드 복잡도 — 중**
최대 함수 길이 `tab_realtime.py` 약 500줄. 단일 함수 내 렌더링·데이터 처리·분기 혼재. Cyclomatic complexity 미측정.

**테스트 부족 — 심각**
비즈니스 로직(PII 마스킹, SQL 검증, 설정 검증) 테스트 커버리지 0%. 리팩토링 시 회귀 오류 감지 불가.

**문서화 수준 — 중상**
파일 헤더 한국어 주석 상세함. 단, API 스펙 문서, 아키텍처 다이어그램, 운영 매뉴얼 없음.

**의존성 노후화**
현재는 최신 버전 사용. `google-genai`, `langchain` 은 6개월 단위 breaking change 多 → 버전 핀닝(`==` 고정) 필수.

---

## 9. 최우선 개선 TOP 10

| 우선순위 | 문제 | 영향도 | 예상 난이도 | 예상 효과 |
|---|---|---|---|---|
| **1** | 기본 관리자 비밀번호 "moonhwa" 하드코딩 | 🔴 보안 침해 시 전체 시스템 장악 | ⭐ 30분 | 즉시 Critical 위험 제거 |
| **2** | systemd/supervisord 프로세스 관리 등록 | 🔴 서버 재시작·크래시 시 서비스 완전 중단 | ⭐ 2시간 | 무중단 자동 재시작 확보 |
| **3** | Dockerfile + docker-compose 작성 | 🔴 환경 재현 불가, 배포 표준화 불가 | ⭐⭐ 1일 | 재현 가능 환경, 배포 표준화 |
| **4** | LLM 생성 SQL — sqlparse + 화이트리스트 강제 | 🔴 SQL Injection → 병원 DB 전체 노출 | ⭐⭐ 2일 | 병원 개인정보 유출 사고 방지 |
| **5** | 실시간 탭 `_fq()` 10개 직렬 → 병렬화 | 🟠 사용자 2-5초 대기, Oracle pool 고갈 | ⭐⭐ 1일 | 실시간 탭 렌더링 80% 단축 |
| **6** | 실시간 VIEW 캐시 TTL 1800 → 60초 분리 | 🟠 30분 전 데이터로 업무 오판 발생 | ⭐ 30분 | 실시간성 복구, 업무 신뢰도 회복 |
| **7** | Oracle 복구 자동 재연결 루프 추가 | 🟠 네트워크 순단 후 앱 재시작 전까지 전체 불능 | ⭐⭐ 4시간 | Oracle HA/RAC failover 대응 |
| **8** | 핵심 모듈 단위 테스트 작성 | 🟠 리팩토링·업그레이드 시 회귀 오류 무감지 | ⭐⭐⭐ 3일 | 안전한 코드 변경 기반 확보 |
| **9** | FAISS reset atomic swap 구현 | 🟠 재구축 중 30-60초 서비스 중단 | ⭐⭐ 1일 | 무중단 벡터DB 재구축 |
| **10** | 최소 모니터링 구축 (UptimeRobot + 이메일 알림) | 🟠 장애를 사용자 신고로 인지하는 구조 | ⭐ 2시간 | 장애 인지 시간 수시간 → 수분 단축 |

---

## 10. 리팩토링 로드맵

### Phase 1 — 즉시 수정 (이번 주, 1-2일)

> **목표: Critical 위험 제거 + 최소 운영 기반 확보**

```
[ ] config/settings.py:653 — admin_password default 제거
[ ] systemd 서비스 파일 작성 (4개 앱 각각)
[ ] .streamlit/config.toml — enableCORS=false, maxMessageSize=50 추가
[ ] requirements.txt — 버전 핀닝(==) 적용
[ ] .gitignore — .env, *.pkl, logs/ 확인 및 추가
[ ] ui/panels/_shared.py — 실시간 VIEW 캐시 TTL 60초 분리 적용
[ ] 관리자 세션 30분 자동 만료 로직 추가
```

### Phase 2 — 구조 개선 (2-4주)

> **목표: 배포 표준화 + 보안 강화 + 테스트 기반 확보**

```
[ ] Dockerfile + docker-compose.yml 작성
    - Multi-stage build (dependencies → app)
    - Oracle Instant Client 포함
    - .env 마운트 전략 (비밀값 외부 주입)

[ ] llm/sql_generator.py — sqlparse 기반 재작성
    - SELECT-only 강제
    - FROM 절 화이트리스트 검증 (ORACLE_WHITELIST_TABLES 필수 설정)
    - UNION/UNION ALL 차단
    - 통합 테스트: known injection payloads 방어 검증

[ ] Service 레이어 도입
    - services/finance_service.py
    - services/ward_service.py
    - UI는 Service만 호출 (Oracle 직접 접근 금지)

[ ] 단위 테스트 작성
    - tests/test_settings.py  (validator 전체)
    - tests/test_sql_generator.py  (injection 방어)
    - tests/test_pii_masker.py  (마스킹 정확도)
    - pytest + pytest-cov, 목표 60% 커버리지

[ ] sys.path 조작 전면 제거
    - guidbot/ 를 패키지로 pip install -e . 설치
    - 40개 파일 상단 sys.path 코드 일괄 제거

[ ] context_builder.py PII 마스킹 전수 감사
    - LLM 전달 전 모든 데이터 경로에서 pii_masker 호출 확인
```

### Phase 3 — 성능 최적화 (1-2달)

> **목표: 응답속도 개선 + 메모리 안정화**

```python
# [ ] 실시간 탭 Oracle 쿼리 병렬화
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as ex:
    futs = {k: ex.submit(_fq, k, _q) for k in REALTIME_KEYS}
    results = {k: f.result() for k, f in futs.items()}

# [ ] 세션 상태 최적화
# fin_weekly_data: Oracle 원본 rows → 집계 요약(수백 bytes)으로 교체
# 원본은 @st.cache_data 레이어에서 관리

# [ ] FAISS atomic swap 구현
NEW_IDX = settings.rag_db_path / "_new"
OLD_IDX = settings.rag_db_path / "_old"
# 1. 새 인덱스 _new/ 에 구축 완료
# 2. 현재 인덱스 → _old/ rename (atomic)
# 3. _new/ → current/ rename (atomic)
# 4. RAGPipeline.reset()
# 5. _old/ 삭제 (지연)

# [ ] 임베딩 캐시 영속화
import joblib
joblib.dump(_EMBED_CACHE, settings.cache_dir / "embed_cache.pkl")
# 재시작 시 로드

# [ ] Oracle 연결 자동 재연결
def _reconnect_oracle_loop():
    while True:
        time.sleep(300)
        if get_oracle_pool() is None:
            initialize_pool()
            logger.info("Oracle 재연결 성공")
```

### Phase 4 — 운영 안정화 (2-3달)

> **목표: 무중단 운영 + 장애 자동 감지**

```yaml
# [ ] GitHub Actions CI/CD 파이프라인
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -r requirements-dev.txt
      - run: flake8 guidbot/
      - run: mypy guidbot/core/ guidbot/config/
      - run: pytest tests/ --cov=guidbot --cov-report=xml
      - uses: codecov/codecov-action@v4
```

```python
# [ ] 구조화 로그 (structlog)
import structlog
log = structlog.get_logger()
log.info("oracle_query", key=key, duration_ms=elapsed, rows=len(result))

# [ ] Oracle 자동 복구
class OracleHealthChecker(threading.Thread):
    def run(self):
        while True:
            time.sleep(300)
            ok, _ = test_connection()
            if ok and _pool is None:
                initialize_pool()
                logger.info("Oracle 자동 복구 완료")

# [ ] 장애 알림
def notify_ops(msg: str):
    if settings.slack_webhook_url:
        requests.post(settings.slack_webhook_url, json={"text": f"🚨 {msg}"})
    # 또는 이메일 SMTP

# [ ] 환경 분리
APP_ENV = os.getenv("APP_ENV", "dev")
env_file = f".env.{APP_ENV}"
```

### Phase 5 — 장기 아키텍처 개선 (3-6달, 선택적)

> **목표: 다병원 확장 대비 + 기술 현대화**

```
[ ] FastAPI 백엔드 분리 (선택)
    - /api/finance/*, /api/ward/* REST API
    - Streamlit은 프론트엔드만 담당
    - 다른 클라이언트(모바일앱, 외부 연동) 지원 가능

[ ] pgvector 또는 Chroma 전환 검토 (부서 100개+ 시)
    - FAISS는 단일 파일 기반 → 분산 불가
    - pgvector: 기존 PostgreSQL 에 벡터 검색 통합

[ ] Redis 캐시 레이어 도입 (다중 서버 배포 시)
    - @st.cache_data 는 로컬 캐시 → 서버 증설 시 캐시 미공유
    - Redis로 전환 시 N대 서버에서 캐시 공유

[ ] LLM 제공자 추상화
    from abc import ABC, abstractmethod
    class LLMProvider(ABC):
        @abstractmethod
        def generate_stream(self, query: str, context: str) -> Generator: ...
    
    class GeminiProvider(LLMProvider): ...
    class ClaudeProvider(LLMProvider): ...  # 폴백

[ ] 병원 AD/LDAP 인증 연동
    - 현재 단일 비밀번호 → 직원 계정 기반 인증
    - 역할(Role): 원무/간호/의사/관리자 권한 분리
```

---

## 11. 총평 — 운영 투입 가능성 판정

### ❌ 현재 상태: **운영 불가** (조건부)

**투입 전 필수 조건 4가지 (1-2주 내 해결 가능):**

```
1. [ ] 기본 비밀번호 제거 + HTTPS 구성          (30분 + 2시간)
2. [ ] systemd/Docker 프로세스 관리 적용         (2시간)
3. [ ] SQL Injection 방어 강화 (화이트리스트 필수) (2일)
4. [ ] 최소 모니터링 + 알림 구성                 (2시간)
```

위 4가지 완료 시 → **병원 내부망 Pilot 운영 가능**

**중장기 생산 운영 기준 추가 조건 (1-2달):**

```
5. [ ] 단위 테스트 60% 커버리지
6. [ ] CI/CD 파이프라인
7. [ ] Oracle 자동 재연결
8. [ ] 로그 → 모니터링 시스템 연동
```

---

### 냉정한 평가

> 이 프로젝트는 **1인 또는 소규모 팀이 만든 병원 내부 도구로서는 수준 높은 코드**다. Pydantic v2 설정 관리, PII 마스킹 프레임워크, 멀티키 LLM 풀링, 스레드 안전 RAG 파이프라인 — 대기업 SI 프로젝트에서도 보기 드문 설계가 들어 있다.

> 그러나 **"운영 서비스"의 기준은 다르다.** 장애가 나면 입원환자 원무 업무 전체가 멈춘다. 테스트 없이 배포하고, 모니터링 없이 운영하고, 기본 비밀번호로 관리자 페이지가 열려 있는 상태는 기술적 실수가 아니라 **운영 리스크이자 법적 리스크**다.

> **지금 당장 해야 할 일은 코드 리팩토링이 아니다.** `systemd` 등록 2시간, 비밀번호 수정 30분, UptimeRobot 설정 1시간 — 이 3가지가 현재 가장 높은 ROI를 가진 작업이다. **코드를 더 짜기 전에 이것부터 하라.**

---

## 부록 A — 배포 전 체크리스트

```
SECURITY
□ ADMIN_PASSWORD 설정 (.env 에 기본값 "moonhwa" 아닌 값)
□ GOOGLE_API_KEY 설정 (2-5개 키 폴백)
□ ORACLE_USER = 읽기 전용 계정 (SELECT only grant)
□ ORACLE_WHITELIST_TABLES 명시적 설정
□ HTTPS 구성 (Nginx 리버스 프록시 or 병원 CA)
□ .env 파일 git 추적 제외 확인
□ 로그 파일 권한 600 확인

PERFORMANCE
□ 실시간 VIEW 캐시 TTL = 60 (opd_kpi, opd_dept_status 등)
□ Oracle pool_min, pool_max 동시 사용자 기준 조정
□ LLM 스트리밍 업데이트 주기 = 16토큰

OPERATIONS
□ systemd 서비스 4개 등록 및 자동 시작 확인
□ 로그 디렉토리 존재 및 쓰기 권한 확인
□ Oracle 연결 테스트 통과
□ UptimeRobot 또는 동등 모니터링 설정
□ 장애 알림 수신 이메일/채널 지정

COMPLIANCE
□ 감사 로그 활성화 (logs/query_audit.log)
□ PII 마스킹 전체 코드 경로 검증
□ SQL Injection 방어 테스트 (known payloads)
□ 관리자 접근 로그 별도 파일 확인
```

## 부록 B — 긴급 수정 코드 스니펫 모음

```python
# 1. 기본 비밀번호 제거 (config/settings.py)
# BEFORE
admin_password: SecretStr = Field(default=SecretStr("moonhwa"), ...)
# AFTER
admin_password: SecretStr = Field(..., description="필수: .env 에 ADMIN_PASSWORD= 설정")

# 2. 관리자 세션 만료 (admin_app.py)
from datetime import datetime, timedelta
_SESSION_TIMEOUT = timedelta(minutes=30)

def _is_session_valid() -> bool:
    if not st.session_state.get("adm_authed"):
        return False
    try:
        t = datetime.fromisoformat(st.session_state.get("adm_login_time", ""))
        if datetime.now() - t > _SESSION_TIMEOUT:
            st.session_state.pop("adm_authed", None)
            return False
    except Exception:
        return False
    return True

# 3. 실시간 캐시 TTL 분리 (ui/panels/_shared.py)
_REALTIME_KEYS = frozenset({
    "opd_kpi", "opd_dept_status", "kiosk_status",
    "discharge_pipeline", "ward_bed_detail",
})

@st.cache_data(show_spinner=False)
def _fq(key: str, date_str: str = "", max_rows: int = 5000):
    ttl = 60 if key in _REALTIME_KEYS else 1800
    # TTL은 decorator 에 동적 전달 불가하므로 별도 함수 분리
    ...

# 실제 구현: 두 함수로 분리
@st.cache_data(ttl=60, show_spinner=False)
def _fq_realtime(key: str, date_str: str = "") -> List[Dict]:
    return _execute_fq(key, date_str)

@st.cache_data(ttl=1800, show_spinner=False)
def _fq_analysis(key: str, date_str: str = "") -> List[Dict]:
    return _execute_fq(key, date_str)

# 4. LLM 온도 설정 반영 (core/llm.py:88)
# BEFORE
cfg: dict = {"max_output_tokens": settings.llm_max_output_tokens, "temperature": 0.1}
# AFTER
cfg: dict = {
    "max_output_tokens": settings.llm_max_output_tokens,
    "temperature": settings.llm_temperature,
}
```

---

*보고서 작성: Claude Code (Anthropic) — 2026-05-07*  
*다음 검토 권장일: 2026-08-07 (분기 1회)*
