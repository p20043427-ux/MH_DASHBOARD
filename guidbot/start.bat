@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title 좋은문화병원 AI 가이드봇 — 운영 시작

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  start.bat — 좋은문화병원 Guidbot 운영 실행 스크립트
REM
REM  [실행 구성]
REM  ┌─────────────────────────────────────────────────────┐
REM  │  Process 1: dashboard_app.py  (포트 8501)           │
REM  │     → 병동 대시보드 전용 (Oracle 조회만)            │
REM  │     → 가볍고 빠름 — 20명 동시 접속 가능            │
REM  │                                                     │
REM  │  Process 2: finance_app.py    (포트 8503)           │
REM  │     → 원무 대시보드 전용 (Oracle 조회만)            │
REM  │     → 가볍고 빠름 — 원무팀/통계과 전용             │
REM  │                                                     │
REM  │  Process 3: main.py           (포트 8502)           │
REM  │     → RAG 챗봇 + 규정 검색 (AI 모델 로드)          │
REM  │     → 무거움 — 동시 5명 이하 권장                  │
REM  │                                                     │
REM  │  Process 4: vector_db_admin.py (포트 8505)          │
REM  │     → 벡터 DB 관리자 전용 (관리자만 접근)          │
REM  │     → 문서 업로드 / 뷰어 / 삭제 / 백업 복원        │
REM  └─────────────────────────────────────────────────────┘
REM
REM  [접속 주소]
REM    병동 대시보드: http://localhost:8501  (또는 서버IP:8501)
REM    원무 대시보드: http://localhost:8503  (또는 서버IP:8503)
REM    챗봇:         http://localhost:8502  (또는 서버IP:8502)
REM    벡터DB 관리자: http://localhost:8505  (관리자 전용)
REM
REM  [종료]
REM    이 창을 닫거나 Ctrl+C → 모든 프로세스 종료됨
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║   🏥  좋은문화병원 AI 가이드봇 — 운영 시작          ║
echo  ║   i5-10500 / 16GB / Windows 최적화 구성             ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

REM ── 프로젝트 루트 디렉토리 확인 ───────────────────────────────
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
echo  📂 프로젝트 경로: %PROJECT_DIR%

REM ── 로그 디렉토리 생성 ─────────────────────────────────────────
if not exist "logs" mkdir logs
echo  📁 로그 디렉토리: %PROJECT_DIR%logs\

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 1: 가상환경 활성화
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [1/4] 가상환경 확인 중...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo  ✅ 가상환경 활성화: venv
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  ✅ 가상환경 활성화: .venv
) else (
    echo  ⚠️  가상환경 없음 — 시스템 Python 사용 (권장하지 않음)
)

REM ── Python 버전 확인 ────────────────────────────────────────────
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo  🐍 %PYVER%

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 2: 포트 충돌 확인 + 기존 프로세스 정리
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [2/4] 포트 충돌 확인 중 (8501, 8502, 8503, 8505)...

REM 8501 포트 사용 중인 프로세스 종료
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501 " 2^>nul') do (
    echo  ⚠️  포트 8501 사용 중인 PID %%a 종료
    taskkill /PID %%a /F >nul 2>&1
)

REM 8502 포트 사용 중인 프로세스 종료
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8502 " 2^>nul') do (
    echo  ⚠️  포트 8502 사용 중인 PID %%a 종료
    taskkill /PID %%a /F >nul 2>&1
)

REM 8503 포트 사용 중인 프로세스 종료
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8503 " 2^>nul') do (
    echo  ⚠️  포트 8503 사용 중인 PID %%a 종료
    taskkill /PID %%a /F >nul 2>&1
)

REM 8505 포트 사용 중인 프로세스 종료 (벡터 DB 관리자)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8505 " 2^>nul') do (
    echo  ⚠️  포트 8505 사용 중인 PID %%a 종료
    taskkill /PID %%a /F >nul 2>&1
)

ping -n 2 127.0.0.1 > nul
echo  ✅ 포트 정리 완료

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 3: AI 모델 워밍업 (캐시 확인)
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [3/4] AI 모델 캐시 확인 중...
echo  (최초 실행 시 모델 다운로드로 30~60초 소요)

python warmup.py
if %ERRORLEVEL% NEQ 0 (
    echo  ⚠️  워밍업 실패 — 첫 질문 응답이 느릴 수 있습니다.
) else (
    echo  ✅ 모델 캐시 확인 완료
)

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 4: 앱 동시 실행
REM  - 대시보드(8501) : 별도 창 백그라운드
REM  - 원무(8503)     : 별도 창 백그라운드
REM  - 벡터DB관리자(8505): 별도 창 백그라운드
REM  - RAG 챗봇(8502) : 이 창 포그라운드 (마지막 실행)
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [4/4] 앱 시작 중...
echo.

REM ─────────────────────────────────────────────────────────
REM  병동 대시보드 (포트 8501) — 별도 창 백그라운드 실행
REM  로그: logs\dashboard_YYYYMMDD.log
REM
REM  [성능 파라미터 설명]
REM  --server.runOnSave false     : 파일 변경 감지 비활성화 (CPU 절약)
REM  --server.headless true       : 브라우저 자동 실행 안 함
REM  --browser.gatherUsageStats   : 외부 통계 전송 비활성화
REM ─────────────────────────────────────────────────────────
set DASHBOARD_LOG=logs\dashboard_%date:~0,4%%date:~5,2%%date:~8,2%.log

start "병동 대시보드 (8501)" /min cmd /c ^
    "streamlit run dashboard_app.py ^
     --server.port 8501 ^
     --server.address 0.0.0.0 ^
     --server.headless true ^
     --server.runOnSave false ^
     --browser.gatherUsageStats false ^
     --server.enableXsrfProtection true ^
     >> %DASHBOARD_LOG% 2>&1"

REM 대시보드 기동 대기 (2초)
ping -n 3 127.0.0.1 > nul
echo  ✅ 병동 대시보드 시작: http://localhost:8501

REM ─────────────────────────────────────────────────────────
REM  원무 대시보드 (포트 8503) — 별도 창 백그라운드 실행
REM  로그: logs\finance_YYYYMMDD.log
REM ─────────────────────────────────────────────────────────
set FINANCE_LOG=logs\finance_%date:~0,4%%date:~5,2%%date:~8,2%.log

start "원무 대시보드 (8503)" /min cmd /c ^
    "streamlit run finance_app.py ^
     --server.port 8503 ^
     --server.address 0.0.0.0 ^
     --server.headless true ^
     --server.runOnSave false ^
     --browser.gatherUsageStats false ^
     --server.enableXsrfProtection true ^
     >> %FINANCE_LOG% 2>&1"

REM 원무 대시보드 기동 대기 (2초)
ping -n 3 127.0.0.1 > nul
echo  ✅ 원무 대시보드 시작: http://localhost:8503

REM ─────────────────────────────────────────────────────────
REM  벡터 DB 관리자 (포트 8505) — 별도 창 백그라운드 실행
REM  로그: logs\vecadmin_YYYYMMDD.log
REM
REM  [보안 주의]
REM  이 앱은 벡터 DB 삭제/재구축 등 강력한 기능을 가지고 있습니다.
REM  운영 환경에서는 내부 IP만 허용하도록 방화벽 설정 필요.
REM  --server.address 를 0.0.0.0 대신 127.0.0.1 로 변경하면
REM  로컬(이 PC)에서만 접근 가능합니다. (외부 접근 차단)
REM ─────────────────────────────────────────────────────────
set VECADMIN_LOG=logs\vecadmin_%date:~0,4%%date:~5,2%%date:~8,2%.log

start "벡터DB 관리자 (8505)" /min cmd /c ^
    "streamlit run vector_db_admin.py ^
     --server.port 8505 ^
     --server.address 127.0.0.1 ^
     --server.headless true ^
     --server.runOnSave false ^
     --browser.gatherUsageStats false ^
     --server.enableXsrfProtection true ^
     >> %VECADMIN_LOG% 2>&1"

REM 관리자 앱 기동 대기 (2초)
ping -n 3 127.0.0.1 > nul
echo  ✅ 벡터DB 관리자 시작: http://localhost:8505  (이 PC에서만 접근 가능)

REM ─────────────────────────────────────────────────────────
REM  RAG 챗봇 앱 (포트 8502) — 이 창에서 포그라운드 실행
REM  로그: logs\chatbot_YYYYMMDD.log (stdout 리다이렉션)
REM ─────────────────────────────────────────────────────────
set CHATBOT_LOG=logs\chatbot_%date:~0,4%%date:~5,2%%date:~8,2%.log

echo  ✅ AI 챗봇 시작: http://localhost:8502
echo.
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  🏥 병동 대시보드: http://localhost:8501
echo  💼 원무 대시보드: http://localhost:8503
echo  🤖 AI 규정 챗봇: http://localhost:8502
echo  🗄️  벡터DB 관리자: http://localhost:8505  (관리자 전용)
echo  📁 로그 위치:    %PROJECT_DIR%logs\
echo  ⏹️  종료: 이 창에서 Ctrl+C 또는 창 닫기
echo  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 포그라운드 실행 (이 창이 닫히면 백그라운드 창들도 함께 종료됨)
streamlit run main.py ^
    --server.port 8502 ^
    --server.address 0.0.0.0 ^
    --server.headless true ^
    --server.runOnSave false ^
    --browser.gatherUsageStats false ^
    --server.enableXsrfProtection true

REM ── 비정상 종료 시 안내 ────────────────────────────────────────
echo.
echo  ⚠️  앱이 종료되었습니다.
echo  오류가 발생한 경우 logs\ 폴더의 로그 파일을 확인하세요.
echo.
pause