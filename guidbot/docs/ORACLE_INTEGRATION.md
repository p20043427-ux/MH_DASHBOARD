# Oracle DB 연동 매뉴얼
> 마지막 갱신: 2026-05-13  
> 대상 버전: guidbot v4.x  
> 작성 기준: `db/oracle_client.py`, `db/oracle_access_config.py`, `config/settings.py`

---

## 목차

1. [개요 및 아키텍처](#1-개요-및-아키텍처)
2. [Oracle DB 사용 목적 — 두 가지 역할](#2-oracle-db-사용-목적--두-가지-역할)
3. [필요 파일 목록](#3-필요-파일-목록)
4. [.env 설정 항목 전체](#4-env-설정-항목-전체)
5. [Thin Mode vs Thick Mode](#5-thin-mode-vs-thick-mode)
6. [설치 절차 (최초 설정)](#6-설치-절차-최초-설정)
7. [RAG_ACCESS_CONFIG 테이블 DDL](#7-rag_access_config-테이블-ddl)
8. [대시보드용 Oracle VIEW 목록](#8-대시보드용-oracle-view-목록)
9. [보안 고려사항](#9-보안-고려사항)
10. [초기 설정 체크리스트](#10-초기-설정-체크리스트)
11. [트러블슈팅](#11-트러블슈팅)

---

## 1. 개요 및 아키텍처

가이드봇의 Oracle DB 연동은 **두 가지 독립적인 경로**로 구성됩니다.

```
[ Oracle DB (병원 HIS) ]
         │
         ├─ ① 병동/원무 대시보드 ─────► db/oracle_client.py
         │     (VIEW 기반 실시간 조회)    └ db/ward_repository.py
         │                               └ db/finance_repository.py
         │
         └─ ② 자연어 데이터 분석 ─────► db/oracle_client.py
               (SQL 자동 생성·실행)       └ db/oracle_access_config.py
                                          └ db/pii_masker.py
                                          └ llm/sql_generator.py
                                          └ llm/data_explainer.py
```

| 경로 | 설정 키 | 목적 |
|------|---------|------|
| ① 대시보드 뷰 조회 | `oracle_enabled=true` | V_ 뷰에서 KPI, 병상, 외래 데이터 읽기 |
| ② 자연어 쿼리 분석 | `oracle_enabled=true` + `RAG_ACCESS_CONFIG` 등록 | 직원이 자연어로 질문 → AI가 SQL 생성 → 결과 반환 |

> **두 설정은 동일한 `oracle_*` 환경변수를 공유합니다.**  
> `ORACLE_ENABLED=true` 한 번만 설정하면 두 기능 모두 활성화됩니다.

---

## 2. Oracle DB 사용 목적 — 두 가지 역할

### ① 대시보드 뷰 조회 (병동/원무)

`db/ward_repository.py`와 `db/finance_repository.py`가 Oracle VIEW를 조회하여
병동 대시보드(`hospital_dashboard.py`)와 원무 대시보드(`finance_dashboard.py`)에 데이터를 공급합니다.

- 쿼리 재시도: **Circuit Breaker 패턴** (연속 3회 실패 → 30초 차단)
- TTL 캐시: 각 쿼리별 **2분 캐시** (Streamlit `@st.cache_data` 등가)
- 장애 시: 샘플 데이터(Mock) 자동 대체 → 앱은 계속 동작

### ② 자연어 데이터 분석 모드

직원이 챗봇에 "이번 주 수술 건수 알려줘" 같은 자연어 질문 입력 시:

1. `llm/sql_generator.py` → Gemini LLM이 Oracle SQL 자동 생성
2. `db/oracle_client.py` → 화이트리스트 테이블 대상으로 SQL 실행
3. `db/pii_masker.py` → PII(개인정보) 컬럼 자동 마스킹
4. `llm/data_explainer.py` → 결과를 자연어로 설명

접근 가능 테이블은 `JAIN_WM.RAG_ACCESS_CONFIG` 또는 `.env`의 `ORACLE_WHITELIST_TABLES`로 제어합니다.

---

## 3. 필요 파일 목록

### 핵심 파일 (Oracle 연동 필수)

| 파일 | 역할 |
|------|------|
| `db/oracle_client.py` | Oracle ConnectionPool 관리, 쿼리 실행, Thin/Thick Mode 제어 |
| `db/oracle_access_config.py` | RAG_ACCESS_CONFIG 테이블 캐시 관리 (화이트리스트 + PII 컬럼 정의) |
| `db/connector.py` | MySQL/MSSQL/PostgreSQL SQLAlchemy 커넥터 (Oracle과 독립) |
| `config/settings.py` | `oracle_*` 환경변수 정의 (Field 검증 포함) |

### 대시보드 데이터 계층

| 파일 | 역할 |
|------|------|
| `db/ward_repository.py` | 병동 대시보드용 VIEW 쿼리 딕셔너리 + Circuit Breaker |
| `db/finance_repository.py` | 원무 대시보드용 VIEW 쿼리 딕셔너리 |

### 자연어 분석 모드

| 파일 | 역할 |
|------|------|
| `db/pii_masker.py` | 주민번호/이름/전화번호 등 PII 이중 마스킹 엔진 |
| `llm/sql_generator.py` | 자연어 → Oracle SQL 변환 (LLM 프롬프트 포함) |
| `llm/data_explainer.py` | SQL 결과 → 자연어 설명 생성 |

### 스키마 벡터화 (RAG 지식화)

| 파일 | 역할 |
|------|------|
| `db/schema_oracle_loader.py` | Oracle ALL_TAB_COLUMNS + RAG_ACCESS_CONFIG → 벡터DB 저장 |
| `db/schema_vector_store.py` | 스키마 벡터DB CRUD (FAISS 기반) |
| `db/schema_extractor.py` | Oracle 시스템 테이블에서 스키마 정보 추출 |
| `db/knowledge_db_builder.py` | 전체 지식 DB 빌드 파이프라인 오케스트레이터 |

### SQL 예제 라이브러리

| 경로 | 형식 | 용도 |
|------|------|------|
| `docs/query_library/*.sql` | `.sql` 파일 | SQL 예제 벡터DB(`vector_store/query_db/`) 구축 소스 |
| `vector_store/query_db/` | FAISS 인덱스 | 자연어 질문 → 유사 쿼리 검색 |
| `vector_store/schema_db/` | FAISS 인덱스 | 자연어 질문 → 관련 테이블/컬럼 검색 |

---

## 4. .env 설정 항목 전체

`.env` 파일에 아래 항목을 추가합니다 (없는 항목은 기본값 사용).

### 기본 연결 설정

```dotenv
# ── Oracle 활성화 ──────────────────────────────────────────────
ORACLE_ENABLED=true              # 기본값: false. true 여야 Oracle 기능 전체 동작

# ── 접속 정보 ──────────────────────────────────────────────────
ORACLE_HOST=192.168.1.10         # Oracle 서버 IP 또는 호스트명
ORACLE_PORT=1521                 # Oracle 리스너 포트 (기본: 1521)
ORACLE_SERVICE_NAME=ORCL         # 서비스명 (예: ORCL, HOSPITAL, XE)
ORACLE_USER=rag_readonly         # DB 계정 (SELECT 전용 권장)
ORACLE_PASSWORD=your_password    # DB 패스워드 (SecretStr — 로그 자동 마스킹)

# ── DSN 직접 지정 (TNS Alias 사용 시) ──────────────────────────
# ORACLE_DSN=HOSPITAL_DB         # 비어있으면 host:port/service_name 자동 구성

# ── 스키마 ─────────────────────────────────────────────────────
ORACLE_SCHEMA=JAIN_WM            # 스키마(소유자)명. 비어있으면 ORACLE_USER와 동일
```

### 커넥션 풀 설정

```dotenv
# ── 커넥션 풀 ──────────────────────────────────────────────────
ORACLE_POOL_MIN=2                # 상시 유지 최소 연결 수 (기본: 2)
ORACLE_POOL_MAX=10               # 최대 동시 연결 수 (기본: 10)
ORACLE_MAX_ROWS=5000             # 쿼리 결과 최대 행 수 (기본: 5000, 최대: 100000)
```

> **풀 설정 가이드**
> - 소규모 병원 (동시 5명 이하): `POOL_MIN=1`, `POOL_MAX=5`
> - 중규모 병원 (동시 10~20명): `POOL_MIN=2`, `POOL_MAX=10` (기본값)
> - 대형 병원 (동시 20명 이상): `POOL_MIN=3`, `POOL_MAX=20`

### 화이트리스트 테이블

```dotenv
# 자연어 분석 모드에서 허용할 테이블 목록 (쉼표 구분)
# RAG_ACCESS_CONFIG 테이블이 있으면 이 값은 폴백(fallback)으로만 사용됨
ORACLE_WHITELIST_TABLES=OMTIDN02,EXMRQST01,V_WARD_BED_DETAIL
# 멀티 스키마: JAIN_OCS.EMIHPTMI 형식으로 스키마 명시 가능
# ORACLE_WHITELIST_TABLES=JAIN_WM.OMTIDN02,JAIN_OCS.EMIHPTMI
```

### Thick Mode (Oracle 10g/11g 구버전)

```dotenv
# Oracle 10g 또는 11g 사용 시만 설정 (12c 이상은 불필요)
ORACLE_THICK_MODE=true
ORACLE_CLIENT_LIB_DIR=C:\oracle\instantclient_11_2
```

---

## 5. Thin Mode vs Thick Mode

### Thin Mode (기본값, 권장)

| 항목 | 내용 |
|------|------|
| 적용 버전 | **Oracle 12.1 이상** |
| 설치 필요 | **없음** — 순수 Python 구현 |
| 설정 | `ORACLE_THICK_MODE=false` (기본값) |
| 장점 | 설치 간단, 배포 편리, Docker/Cloud 환경 적합 |
| 단점 | 구버전 Oracle 미지원 |

### Thick Mode (구버전 Oracle)

| 항목 | 내용 |
|------|------|
| 적용 버전 | **Oracle 10g / 11g** |
| 설치 필요 | **Oracle Instant Client** 별도 설치 필수 |
| 설정 | `ORACLE_THICK_MODE=true` + `ORACLE_CLIENT_LIB_DIR=경로` |
| 장점 | 구버전 HIS 시스템 호환 |
| 단점 | OS별 Instant Client 설치 필요 |

### Thick Mode 설치 절차

```
1. 다운로드 URL:
   https://www.oracle.com/database/technologies/instant-client/winx64-64-downloads.html
   → "Basic Light" 또는 "Basic" 패키지 선택 (64비트)

2. 압축 해제:
   C:\oracle\instantclient_11_2\
   (또는 원하는 경로 — ORACLE_CLIENT_LIB_DIR 에 동일하게 설정)

3. .env 설정:
   ORACLE_THICK_MODE=true
   ORACLE_CLIENT_LIB_DIR=C:\oracle\instantclient_11_2

4. 앱 재시작
```

> **버전 확인**: DBeaver → 연결 정보 → Oracle 버전 확인  
> 12.1 이상이면 Thin Mode 사용 권장.

---

## 6. 설치 절차 (최초 설정)

### Step 1. 패키지 설치

```bash
pip install oracledb>=2.0.0
```

이미 `requirements.txt`에 포함되어 있으므로 전체 설치 시 자동으로 설치됩니다:

```bash
pip install -r requirements.txt
```

### Step 2. .env 파일 설정

프로젝트 루트의 `.env` 파일에 Oracle 접속 정보를 추가합니다:

```dotenv
ORACLE_ENABLED=true
ORACLE_HOST=192.168.1.10
ORACLE_PORT=1521
ORACLE_SERVICE_NAME=ORCL
ORACLE_USER=rag_readonly
ORACLE_PASSWORD=your_secure_password
ORACLE_SCHEMA=JAIN_WM
```

### Step 3. Oracle 계정 및 권한 설정

DBA 계정으로 Oracle DB에서 읽기 전용 계정을 생성합니다:

```sql
-- 읽기 전용 계정 생성
CREATE USER rag_readonly IDENTIFIED BY "your_secure_password";
GRANT CREATE SESSION TO rag_readonly;

-- 대시보드 VIEW 접근 권한
GRANT SELECT ON JAIN_WM.V_WARD_DEPT_STAY TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_BED_DETAIL TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_OP_STAT TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_WARD_KPI_TREND TO rag_readonly;
GRANT SELECT ON JAIN_WM.V_FINANCE_TODAY TO rag_readonly;
-- ... (사용하는 모든 VIEW에 권한 부여)

-- 자연어 분석 모드 화이트리스트 테이블 권한
GRANT SELECT ON JAIN_WM.OMTIDN02 TO rag_readonly;
-- ... (RAG_ACCESS_CONFIG 에 등록할 테이블)

-- RAG_ACCESS_CONFIG 테이블 접근 권한 (자연어 분석 모드 사용 시)
GRANT SELECT ON JAIN_WM.RAG_ACCESS_CONFIG TO rag_readonly;
```

### Step 4. 연결 테스트

관리자 대시보드(admin_app.py) → **환경설정 탭** → **Oracle DB 연결 테스트** 버튼  

또는 Python으로 직접 테스트:

```python
from db.oracle_client import test_connection
result = test_connection()
print(result)  # {"success": True, "version": "Oracle 19c", ...}
```

### Step 5. 대시보드 VIEW 생성

`docs/create_views.sql` 파일을 DBA 계정으로 실행하여 필요한 VIEW를 생성합니다:

```bash
# DBeaver 또는 SQLPlus로 실행
# create_views.sql 내용 참고: docs/create_views.sql
```

### Step 6. 스키마 벡터DB 구축 (자연어 분석 모드 사용 시)

```bash
# Oracle 스키마 정보를 벡터DB에 저장
python -m db.schema_oracle_loader

# 강제 재구축
python -m db.schema_oracle_loader --force

# 저장 전 미리보기
python -m db.schema_oracle_loader --show-docs
```

실행 결과: `vector_store/schema_db/` 에 FAISS 인덱스 생성

### Step 7. RAG_ACCESS_CONFIG 테이블 등록 (자연어 분석 모드 사용 시)

[§7 RAG_ACCESS_CONFIG 테이블 DDL](#7-rag_access_config-테이블-ddl) 참고

---

## 7. RAG_ACCESS_CONFIG 테이블 DDL

자연어 분석 모드에서 허용할 테이블 목록과 컬럼 설명을 DB에서 동적으로 관리합니다.

> **이 테이블이 없으면**: `.env`의 `ORACLE_WHITELIST_TABLES` 값으로 폴백  
> (TABLE_DESC, COLUMN_DESCS 정보 없이 테이블명만 화이트리스트에 등록됨)

### 테이블 생성 DDL

```sql
-- JAIN_WM 스키마에서 DBA 계정으로 실행
CREATE TABLE JAIN_WM.RAG_ACCESS_CONFIG (
    TABLE_NAME    VARCHAR2(128)  NOT NULL,       -- 테이블명 (대문자)
    SCHEMA_NAME   VARCHAR2(128)  DEFAULT 'JAIN_WM' NOT NULL,  -- 스키마명
    IS_ACTIVE     NUMBER(1)      DEFAULT 1  NOT NULL,  -- 1=활성, 0=비활성
    MASK_COLUMNS  VARCHAR2(2000) DEFAULT NULL,   -- 마스킹 컬럼 (쉼표 구분)
    ALIAS         VARCHAR2(200)  DEFAULT NULL,   -- 테이블 별칭 (한국어)
    DESCRIPTION   VARCHAR2(1000) DEFAULT NULL,   -- 관리자 메모
    TABLE_DESC    VARCHAR2(1000) DEFAULT NULL,   -- [v1.1] LLM용 테이블 설명
    COLUMN_DESCS  CLOB           DEFAULT NULL,   -- [v1.1] 컬럼별 설명 (JSON)
    CONSTRAINT RAG_ACCESS_CONFIG_PK PRIMARY KEY (TABLE_NAME, SCHEMA_NAME)
);

-- rag_readonly 계정에 SELECT 권한 부여
GRANT SELECT ON JAIN_WM.RAG_ACCESS_CONFIG TO rag_readonly;
```

### 기존 테이블에 v1.1 컬럼 추가 (업그레이드)

```sql
ALTER TABLE JAIN_WM.RAG_ACCESS_CONFIG ADD (
    TABLE_DESC   VARCHAR2(1000) DEFAULT NULL,
    COLUMN_DESCS CLOB           DEFAULT NULL
);
```

### 테이블 등록 예시

```sql
-- 입원 환자 병실 현황 테이블 등록
INSERT INTO JAIN_WM.RAG_ACCESS_CONFIG (
    TABLE_NAME, SCHEMA_NAME, IS_ACTIVE, MASK_COLUMNS, ALIAS,
    DESCRIPTION, TABLE_DESC, COLUMN_DESCS
) VALUES (
    'OMTIDN02', 'JAIN_WM', 1,
    'OMT02NAME,OMT02IDNOA,OMT02AIDNOA',  -- PII 마스킹 컬럼
    '입원환자 병실현황',
    '입원 중인 환자의 병실 배치 현황 테이블',
    '입원 환자 병실 배치 현황. 병동/병실/침상 단위 관리. 퇴원 시 USEFLAG=N',
    '{
        "OMT02BLD":    "병동코드 (01=내과, 02=외과, 08=정형외과)",
        "OMT02BEDNO":  "병실번호 (예: 0801=8병동 1호실)",
        "OMT02BEDSEQ": "침상번호 (1~6)",
        "OMT02NAME":   "환자명 (PII - 마스킹)",
        "OMT02IDNOA":  "주민등록번호 (PII - 마스킹)",
        "OMT02USEFLAG":"사용여부 (Y=사용중/입원중, N=퇴원/공실)",
        "OMT02DEPT":   "진료과코드",
        "OMT02INDATE": "입원일자 (YYYYMMDD)",
        "OMT02PTNO":   "환자번호"
    }'
);
COMMIT;
```

### DBeaver에서 COLUMN_DESCS 탭 구분 형식 입력

DBeaver에서 Excel처럼 탭 구분 텍스트를 붙여넣기 할 수 있습니다:

```
컬럼명	타입	크기	설명
OMT02BLD	VARCHAR2	4	병동코드 (01=내과, 02=외과)
OMT02BEDNO	VARCHAR2	6	병실번호
OMT02NAME	VARCHAR2	30	환자명
```

> JSON과 탭 구분 텍스트 모두 자동으로 파싱됩니다 (`oracle_access_config.py`).

### 활성화/비활성화

```sql
-- 특정 테이블 비활성화 (삭제 없이 숨김)
UPDATE JAIN_WM.RAG_ACCESS_CONFIG SET IS_ACTIVE = 0 WHERE TABLE_NAME = 'OMTIDN02';
COMMIT;

-- 재활성화
UPDATE JAIN_WM.RAG_ACCESS_CONFIG SET IS_ACTIVE = 1 WHERE TABLE_NAME = 'OMTIDN02';
COMMIT;
```

> **캐시 TTL**: 변경 후 최대 5분 이내에 반영 (기본 TTL=300초)  
> 즉시 반영: 앱 재시작 또는 관리자 탭의 "캐시 초기화" 버튼

---

## 8. 대시보드용 Oracle VIEW 목록

전체 VIEW DDL은 `docs/create_views.sql` 및 `docs/oracle_views.md` 참고.

### 병동 대시보드 (`db/ward_repository.py`)

| VIEW | 용도 |
|------|------|
| `V_WARD_DEPT_STAY` | 진료과별 재원 현황 |
| `V_WARD_BED_DETAIL` | 병상 세부 현황 (환자 배치) |
| `V_WARD_OP_STAT` | 수술 건수 통계 |
| `V_WARD_KPI_TREND` | 병동 KPI 일별 추이 |
| `V_WARD_YESTERDAY` | 어제 병동 현황 |
| `V_WARD_DX_TODAY` | 오늘 진단명 현황 |
| `V_WARD_DX_TREND` | 진단명 추이 |
| `V_ADMIT_CANDIDATES` | 입원 대기 현황 |
| `V_WARD_ROOM_DETAIL` | 병실 요약 |

### 원무 대시보드 (`db/finance_repository.py`)

| VIEW | 용도 |
|------|------|
| `V_FINANCE_TODAY` | 오늘 원무 KPI |
| `V_OVERDUE_STAT` | 미수금 통계 |
| `V_FINANCE_BY_INS` | 보험 종류별 수납 |
| `V_OPD_KPI` | 외래 KPI |
| `V_OPD_BY_DEPT` | 진료과별 외래 |
| `V_OPD_HOURLY_STAT` | 시간대별 외래 |
| `V_NOSHOW_STAT` | 노쇼(예약 미래원) 통계 |

### 간호 대시보드

| VIEW | 용도 |
|------|------|
| `V_WARD_HIGH_RISK` | 고위험 환자 현황 |
| `V_WARD_INCIDENT` | 낙상·욕창 등 사건 사고 |

---

## 9. 보안 고려사항

### 필수 보안 설정

| 항목 | 권장 사항 |
|------|----------|
| **DB 계정** | SELECT 전용 `rag_readonly` 계정 사용. INSERT/UPDATE/DELETE 권한 부여 금지 |
| **패스워드** | `.env` 파일에만 저장. `git add .env` 절대 금지 (`.gitignore` 확인) |
| **네트워크** | Oracle 서버 방화벽에서 앱 서버 IP만 1521 포트 허용 (IP 화이트리스트) |
| **테이블 접근** | `ORACLE_WHITELIST_TABLES` 또는 `RAG_ACCESS_CONFIG`에 명시된 테이블만 허용 |
| **결과 행 수** | `ORACLE_MAX_ROWS=5000` 유지 (대용량 데이터 유출 방지) |
| **개인정보** | `MASK_COLUMNS`에 PII 컬럼 등록 필수 |

### PII(개인정보) 마스킹 정책

`db/pii_masker.py`가 두 레이어로 마스킹합니다:

| 레이어 | 적용 시점 | 방법 |
|--------|-----------|------|
| **Layer 1 (화면)** | 데이터 테이블 렌더링 시 | 이름: `홍**`, 주민번호: `900101-*******`, 전화: `010-****-5678` |
| **Layer 2 (LLM)** | AI에 데이터 전달 전 | PII 컬럼 완전 제거 또는 통계 요약만 전달 |

> PII 컬럼은 `RAG_ACCESS_CONFIG.MASK_COLUMNS`에 쉼표로 등록합니다.  
> 예: `MASK_COLUMNS = 'OMT02NAME,OMT02IDNOA,환자명,주민번호'`

### 감사 로그

모든 SQL 실행 이력이 `logs/query_audit.log`에 기록됩니다 (90일 보관):

```
2026-05-13 10:23:45 | oracle | rag_readonly | SELECT COUNT(*) FROM JAIN_WM.OMTIDN02 | rows=1 | 23ms
```

---

## 10. 초기 설정 체크리스트

```
[ 기본 연결 ]
☐ Oracle DB IP/Port/Service Name 확인
☐ .env 에 ORACLE_ENABLED=true 설정
☐ .env 에 ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE_NAME 설정
☐ .env 에 ORACLE_USER, ORACLE_PASSWORD 설정
☐ .env 에 ORACLE_SCHEMA 설정 (예: JAIN_WM)

[ Oracle 계정 설정 (DBA 작업) ]
☐ rag_readonly 계정 생성 및 CREATE SESSION 권한 부여
☐ 대시보드 VIEW 전체에 SELECT 권한 부여
☐ 자연어 분석 대상 테이블에 SELECT 권한 부여
☐ RAG_ACCESS_CONFIG 테이블에 SELECT 권한 부여

[ 구버전 Oracle (10g/11g) ]
☐ Oracle Instant Client 11.2 (64bit) 다운로드 및 설치
☐ .env 에 ORACLE_THICK_MODE=true 설정
☐ .env 에 ORACLE_CLIENT_LIB_DIR=설치경로 설정

[ 대시보드 VIEW ]
☐ docs/create_views.sql 실행 (DBA 계정)
☐ 관리자 대시보드 → 운영현황 탭에서 대시보드 정상 로드 확인

[ 자연어 분석 모드 ]
☐ RAG_ACCESS_CONFIG 테이블 DDL 실행 (§7 참고)
☐ 허용 테이블 INSERT + TABLE_DESC, COLUMN_DESCS 등록
☐ MASK_COLUMNS에 PII 컬럼 등록
☐ python -m db.schema_oracle_loader 실행 (스키마 벡터DB 구축)
☐ 챗봇에서 테스트 질문으로 동작 확인

[ 보안 확인 ]
☐ .gitignore에 .env 포함 확인
☐ rag_readonly 계정 DML 권한 없음 확인 (INSERT/UPDATE/DELETE)
☐ Oracle 서버 방화벽 IP 화이트리스트 적용 확인
```

---

## 11. 트러블슈팅

### DPY-3010: Thin Mode 지원 안 됨

```
ORA-12541 또는 DPY-3010: connections to this database server version are not supported
→ Oracle 버전이 12.1 미만 (10g/11g)
→ 해결: ORACLE_THICK_MODE=true + Instant Client 설치 (§5 Thick Mode 참고)
```

### ORA-01017: 로그인 거부

```
ORA-01017: invalid username/password; logon denied
→ ORACLE_USER 또는 ORACLE_PASSWORD 확인
→ 계정이 잠겼을 경우: DBA가 ALTER USER rag_readonly ACCOUNT UNLOCK; 실행
```

### ORA-12541: TNS 리스너 없음

```
ORA-12541: TNS:no listener
→ ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE_NAME 확인
→ Oracle 서버 방화벽에서 1521 포트 허용 확인
→ lsnrctl status 명령으로 리스너 상태 확인
```

### ORA-00942: 테이블 또는 뷰가 없음

```
ORA-00942: table or view does not exist
→ 테이블명 또는 스키마명 오타 확인
→ rag_readonly 계정에 해당 테이블 SELECT 권한 부여 확인
→ RAG_ACCESS_CONFIG에서 SCHEMA_NAME 올바른지 확인 (예: JAIN_WM vs JAIN_OCS)
```

### ORA-01008: Not all variables bound

```
ORA-01008: not all variables bound
→ SQL 문자열에 :변수명이 있는데 params에 해당 키가 없는 경우
→ db/schema_oracle_loader.py 사용 시: f-string으로 직접 삽입하도록 수정된 버전 사용 (v1.1)
```

### RAG_ACCESS_CONFIG 변경이 즉시 반영 안 됨

```
→ TTL 캐시 5분 대기 후 확인
→ 즉시 반영: 관리자 대시보드 → 환경설정 탭 → "캐시 초기화" 버튼
→ 또는 앱 재시작
```

### 스키마 벡터DB 구축 실패

```
python -m db.schema_oracle_loader 실행 시 오류
→ ORACLE_ENABLED=true 확인
→ Oracle 연결 상태 확인 (test_connection())
→ vector_store/schema_db/ 디렉토리 존재 확인
→ --show-docs 플래그로 구축 전 미리보기 확인
```

### 대시보드에서 Oracle 데이터가 안 보임

```
→ ORACLE_ENABLED=true 설정 확인
→ 관리자 대시보드 → 운영현황 탭 → 서비스 포트 상태 확인
→ 앱 로그 확인: logs/db.oracle_client_YYYYMMDD.log
→ Circuit Breaker 차단 상태: 30초 대기 후 자동 복구 시도
→ 관리자 탭에서 Oracle 연결 테스트 실행
```

---

*`db/oracle_client.py` v1.0 / `db/oracle_access_config.py` v1.5 기준*  
*이전 버전 cx_Oracle 사용자: `pip uninstall cx_Oracle` 후 `pip install oracledb>=2.0.0`*
