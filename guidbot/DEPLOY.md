# 좋은문화병원 AI 가이드봇 — 설치·배포·운영 매뉴얼

> 작성일: 2026-04-20  
> 적용 버전: Guidbot v9.x  
> 담당: 개발 PC 192.1.1.234 → 운영 PC 192.1.1.231

---

## 목차

1. [시스템 구성 개요](#1-시스템-구성-개요)
2. [사전 준비사항](#2-사전-준비사항-운영-pc-192111231)
3. [최초 설치 절차](#3-최초-설치-절차-운영-pc-192111231)
4. [개발→운영 소스 반영](#4-개발-pc--운영-pc-소스-반영-절차)
5. [일상 운영 절차](#5-일상-운영-절차)
6. [트러블슈팅](#6-트러블슈팅)
7. [담당 역할 정리](#7-담당-역할-정리)

---

## 1. 시스템 구성 개요

```
┌─────────────────────────────┐        ┌─────────────────────────────┐
│   개발 PC  192.1.1.234      │        │   운영 PC  192.1.1.231      │
│                             │        │                             │
│  · 소스코드 개발·수정       │        │  · 실제 서비스 운영         │
│  · GitHub Desktop으로 Push  │        │  · git pull로 최신본 반영   │
│  · .env (개발용)            │        │  · .env (운영용, 별도 관리) │
└────────────┬────────────────┘        └──────────────┬──────────────┘
             │                                        │
             └──────────── GitHub 저장소 ─────────────┘
                           (코드 허브)
```

### 구동 앱 3개

| 앱 | 포트 | 진입점 파일 | 내부 접속 | 외부 접속 |
|---|---|---|---|---|
| 병동 대시보드 | 8501 | `dashboard_app.py` | http://localhost:8501 | http://192.1.1.231:8501 |
| AI 규정 챗봇 | 8502 | `main.py` | http://localhost:8502 | http://192.1.1.231:8502 |
| 원무 대시보드 | 8503 | `finance_app.py` | http://localhost:8503 | http://192.1.1.231:8503 |

### 디렉토리 구조 (운영 PC 기준)

```
C:\MH\guidbot\
├── .env                    ← API키·비밀번호 (Git 제외! 운영PC 단독 보관)
├── .env.example            ← 설정 항목 예시 (Git 포함)
├── start.bat               ← 서비스 시작 스크립트
├── deploy.bat              ← 원클릭 배포 스크립트 (설치 후 생성)
├── warmup.py               ← AI 모델 사전 로드
├── requirements.txt        ← Python 패키지 목록
├── dashboard_app.py        ← 병동 대시보드 (포트 8501)
├── main.py                 ← AI 챗봇 (포트 8502)
├── finance_app.py          ← 원무 대시보드 (포트 8503)
├── config/
│   └── settings.py         ← 중앙 설정 (경로·DB·모델 파라미터)
├── ui/                     ← 대시보드 화면 모듈
├── core/                   ← RAG 파이프라인 (임베딩·벡터검색·LLM)
├── db/                     ← Oracle/DB 클라이언트
├── utils/                  ← 로깅·모니터링 유틸
├── venv/                   ← Python 가상환경 (Git 제외)
├── data_cache/             ← HuggingFace 모델 캐시 (Git 제외)
├── data_rag_working/       ← PDF 원문 작업 폴더 (Git 제외)
├── vector_store/           ← FAISS 벡터 DB (Git 제외)
└── logs/                   ← 일별 로그 파일 (Git 제외)
```

---

## 2. 사전 준비사항 (운영 PC 192.1.1.231)

### 2-1. 필수 설치 소프트웨어

#### Python 3.11 (권장)

```
https://www.python.org/downloads/
  → Windows installer (64-bit) 다운로드
  → 설치 화면에서 "Add Python to PATH" 반드시 체크
```

설치 확인:
```cmd
python --version
```
`Python 3.11.x` 출력이면 정상.

#### Git for Windows

```
https://git-scm.com/download/win
  → 기본 옵션으로 설치
```

설치 확인:
```cmd
git --version
```
`git version 2.x.x` 출력이면 정상.

#### Oracle Instant Client (Oracle DB 사용 시만)

```
Oracle Instant Client Basic 21c (64-bit) 다운로드 후 압축 해제
→ 예: C:\oracle\instantclient_21_11\
→ [내 PC] → [속성] → [고급 시스템 설정] → [환경변수]
   → 시스템 변수 Path에 C:\oracle\instantclient_21_11\ 추가
→ PC 재시작
```

### 2-2. 방화벽 포트 개방

관리자 권한 CMD에서 실행:

```cmd
netsh advfirewall firewall add rule name="GuidBot-8501" protocol=TCP dir=in localport=8501 action=allow
netsh advfirewall firewall add rule name="GuidBot-8502" protocol=TCP dir=in localport=8502 action=allow
netsh advfirewall firewall add rule name="GuidBot-8503" protocol=TCP dir=in localport=8503 action=allow
```

확인:
```cmd
netsh advfirewall firewall show rule name="GuidBot-8501"
```

---

## 3. 최초 설치 절차 (운영 PC 192.1.1.231)

### STEP 1 — GitHub에서 소스 클론

```cmd
cd C:\
git clone https://github.com/[계정명]/[저장소명].git MH
cd C:\MH\guidbot
```

> GitHub 저장소 주소: 개발 PC의 GitHub Desktop → Repository → Copy Remote URL

### STEP 2 — 가상환경 생성

```cmd
cd C:\MH\guidbot
python -m venv venv
```

### STEP 3 — Python 패키지 설치

```cmd
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

> 최초 설치 시 약 10~20분 소요 (PyTorch 포함 약 4GB 다운로드)

GPU 없는 일반 PC는 그대로 진행. GPU 사용 시 추가:
```cmd
pip uninstall faiss-cpu -y
pip install faiss-gpu
```

### STEP 4 — 환경변수 파일 (.env) 설정

```cmd
copy .env.example .env
notepad .env
```

`.env`에서 **반드시** 수정할 항목:

```ini
# ① Google Gemini API 키 (필수 — 없으면 앱 시작 불가)
#    발급: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY=AIzaSy...실제키...
GOOGLE_API_KEY_2=AIzaSy...예비키1...    # 할당량 초과 시 자동 전환
GOOGLE_API_KEY_3=AIzaSy...예비키2...

# ② 관리자 비밀번호 (기본값 'moonhwa' 반드시 변경!)
ADMIN_PASSWORD=강력한패스워드12자이상!

# ③ Oracle 연결 (사용 시)
DB_ENABLED=true
DB_TYPE=oracle
DB_HOST=192.1.1.xxx      # Oracle 서버 IP
DB_PORT=1521
DB_NAME=ORCL             # SID 또는 서비스명
DB_USER=rag_readonly     # SELECT 전용 계정 권장
DB_PASSWORD=DB패스워드
```

> `.env` 파일은 `.gitignore`에 등록되어 있어 Git에 올라가지 않습니다.
> 운영 PC에서만 단독 보관하세요.

### STEP 5 — AI 모델 사전 캐시

```cmd
venv\Scripts\activate
python warmup.py
```

> 최초 실행 시 임베딩 모델 약 500MB 다운로드 (인터넷 필요, 1~3분 소요)
> 이후 재실행부터는 3~5초로 단축됩니다.

### STEP 6 — 경로 설정 확인

`config/settings.py` 파일을 열어 기준 경로를 확인합니다:

```python
# 43번째 줄 — 운영 PC 경로와 다르면 수정
_BASE_DIR = Path(r"C:\MH\guidbot")
```

> 운영 PC 설치 경로가 `C:\MH\guidbot`이면 수정 불필요.
> 다른 경로(예: `D:\guidbot`)에 설치했다면 해당 경로로 수정.

### STEP 7 — 실행 테스트

```cmd
cd C:\MH\guidbot
start.bat
```

브라우저에서 접속 확인:
- http://localhost:8501 → 병동 대시보드
- http://localhost:8502 → AI 챗봇
- http://localhost:8503 → 원무 대시보드

다른 PC에서 접속 확인:
- http://192.1.1.231:8501 ~ 8503

---

## 4. 개발 PC → 운영 PC 소스 반영 절차

### 4-1. 개발자 작업 흐름 (192.1.1.234)

```
코드 수정 완료
  → GitHub Desktop 열기
  → 변경 파일 확인 (Changes 탭)
  → Summary 입력 (커밋 메시지)
  → [Commit to main] 클릭
  → [Push origin] 클릭
  → 운영 담당자에게 배포 요청
```

### 4-2. 운영 PC 수동 반영 절차 (192.1.1.231)

```cmd
cd C:\MH\guidbot

REM ① 앱 중지
taskkill /IM python.exe /F

REM ② 최신 소스 받기
git pull

REM ③ 패키지 추가된 경우에만 (requirements.txt 변경 시)
venv\Scripts\activate
pip install -r requirements.txt

REM ④ 앱 재시작
start.bat
```

### 4-3. 원클릭 배포 스크립트 생성 (최초 1회)

`C:\MH\guidbot\deploy.bat` 파일을 아래 내용으로 생성:

```bat
@echo off
chcp 65001 > nul
setlocal
title 좋은문화병원 — 운영 배포

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   🚀 운영 배포 시작                          ║
echo  ╚══════════════════════════════════════════════╝
echo.

echo [1/3] 실행 중인 앱 종료...
taskkill /IM python.exe /F > nul 2>&1
ping -n 3 127.0.0.1 > nul
echo  완료

echo [2/3] GitHub 최신 소스 반영...
cd /d C:\MH\guidbot
git pull
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ❌ git pull 실패 — 네트워크 또는 충돌 확인 필요
    echo  해결: git checkout -- . 실행 후 재시도
    pause
    exit /b 1
)
echo  완료

echo [3/3] 앱 재시작...
echo.
call start.bat
```

이후 배포 시: **`deploy.bat` 더블클릭** 만으로 전체 반영 완료.

---

## 5. 일상 운영 절차

### 서비스 시작

```cmd
cd C:\MH\guidbot
start.bat
```

또는 바탕화면 `start.bat` 바로가기 더블클릭.

### 서비스 종료

`start.bat`을 실행한 CMD 창에서 **Ctrl+C** 또는 창 닫기.  
강제 종료 시:
```cmd
taskkill /IM python.exe /F
```

### Windows 부팅 시 자동 실행 설정 (선택)

1. `Win + R` → `shell:startup` 엔터 → 시작 프로그램 폴더 열림
2. `C:\MH\guidbot\start.bat`의 **바로가기**를 폴더 안에 복사
3. 이후 PC 재부팅 시 자동으로 앱 실행됨

### 로그 확인

```
C:\MH\guidbot\logs\
  ├── dashboard_20260420.log    ← 병동 대시보드 로그
  ├── chatbot_20260420.log      ← AI 챗봇 로그
  └── finance_20260420.log      ← 원무 대시보드 로그
```

오류 발생 시 해당 날짜 로그 파일을 메모장으로 열어 확인.  
관리자 대시보드 접속 → 로그 뷰어 탭에서도 확인 가능.

### 정기 점검 항목 (월 1회 권장)

```
□ logs/ 폴더 30일 이상 된 파일 삭제
□ pip list --outdated 로 패키지 업데이트 여부 확인
□ .env의 API 키 만료 여부 확인
□ Oracle 연결 상태 확인 (대시보드 접속 테스트)
□ vector_store_backup/ 오래된 백업 정리
```

---

## 6. 트러블슈팅

| 증상 | 원인 | 해결 방법 |
|---|---|---|
| `ModuleNotFoundError` | 패키지 미설치 | `venv\Scripts\activate` 후 `pip install -r requirements.txt` |
| 포트 이미 사용 중 오류 | 이전 프로세스 잔존 | `taskkill /IM python.exe /F` 후 재시작 |
| Oracle 연결 실패 | Instant Client 미설치 또는 방화벽 | Client 설치 확인, DB 서버 방화벽 1521 포트 개방 |
| AI 응답 없음 / API 오류 | Gemini API 키 만료 또는 할당량 초과 | `.env`의 `GOOGLE_API_KEY` 재발급·수정 |
| `'xxx' key error` | 구버전 코드와 신버전 충돌 | `git pull` 후 `pip install -r requirements.txt` 재실행 |
| `git pull` 충돌 | 운영 PC에서 파일 직접 수정됨 | `git checkout -- .` 실행 후 `git pull` 재시도 |
| 브라우저에서 접속 불가 | 방화벽 미개방 | 섹션 2-2 방화벽 규칙 추가 확인 |
| 앱 느림 / 메모리 부족 | 모델 캐시 미적재 | `python warmup.py` 실행 후 재시작 |
| 챗봇만 응답 없음 | RAG 인덱스 없음 | 관리자 패널 → 문서 인덱스 재구축 실행 |

### git pull 충돌 발생 시 전체 초기화

> 운영 PC에서 파일을 실수로 수정했을 때:

```cmd
cd C:\MH\guidbot
git fetch origin
git reset --hard origin/main
git pull
```

⚠️ 로컬 수정사항이 모두 삭제됩니다. `.env`는 영향 없습니다.

---

## 7. 담당 역할 정리

| 구분 | PC | 작업 내용 |
|---|---|---|
| 개발·코드 관리 | 192.1.1.234 | 소스 수정 → GitHub Desktop으로 Push |
| 서비스 운영 | 192.1.1.231 | `deploy.bat` 실행으로 최신본 반영 |
| `.env` 보안 | 운영 PC 단독 | API키·DB패스워드 — Git에 절대 올리지 않음 |
| Oracle 연결 | 운영 PC | DB_HOST·DB_PASSWORD 설정 운영팀 관리 |

### 한 줄 요약

```
개발 PC: 코드 수정 → [Push]
운영 PC: deploy.bat 더블클릭
```

---

## 부록 A — 환경변수 전체 목록

| 변수명 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `GOOGLE_API_KEY` | ✅ | — | Gemini API 기본 키 |
| `GOOGLE_API_KEY_2` ~ `4` | 권장 | — | 할당량 초과 시 자동 전환 예비 키 |
| `CHAT_MODEL` | — | `models/gemini-2.5-flash` | LLM 모델 선택 |
| `ADMIN_PASSWORD` | ✅ | `moonhwa` | 관리자 패널 비밀번호 (운영 시 변경 필수) |
| `DB_ENABLED` | — | `false` | Oracle/DB 연결 활성화 |
| `DB_TYPE` | DB 시 ✅ | — | `oracle` / `mysql` / `mssql` / `postgresql` |
| `DB_HOST` | DB 시 ✅ | — | DB 서버 IP 또는 호스트명 |
| `DB_PORT` | — | `1521` | DB 포트 (Oracle 기본 1521) |
| `DB_NAME` | DB 시 ✅ | — | DB 이름 (Oracle: SID 또는 서비스명) |
| `DB_USER` | DB 시 ✅ | — | DB 계정 (SELECT 전용 권장) |
| `DB_PASSWORD` | DB 시 ✅ | — | DB 비밀번호 |
| `MONITORING_ENABLED` | — | `true` | 성능 모니터링 수집 ON/OFF |
| `APP_TITLE` | — | `좋은문화병원 AI` | 브라우저 탭 제목 |

---

## 부록 B — 접속 URL 전체 목록

| 서비스 | 내부 (운영 PC 직접) | 병원 내부망 |
|---|---|---|
| 병동 대시보드 | http://localhost:8501 | http://192.1.1.231:8501 |
| AI 규정 챗봇 | http://localhost:8502 | http://192.1.1.231:8502 |
| 원무 대시보드 | http://localhost:8503 | http://192.1.1.231:8503 |
