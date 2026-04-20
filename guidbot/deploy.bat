@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion
title 좋은문화병원 — 운영 배포

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   🚀  좋은문화병원 AI 가이드봇 — 운영 배포  ║
echo  ╚══════════════════════════════════════════════╝
echo.

REM ── 경로 설정 ────────────────────────────────────────────────
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 1 : 실행 중인 앱 종료
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo  [1/3] 실행 중인 앱 종료 중...
taskkill /IM python.exe /F > nul 2>&1
ping -n 3 127.0.0.1 > nul
echo  완료

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 2 : GitHub 최신 소스 반영
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [2/3] GitHub 최신 소스 받는 중...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  ❌ git pull 실패!
    echo.
    echo  [원인 1] 네트워크 연결 확인
    echo  [원인 2] 로컬 파일 충돌 — 아래 명령으로 해결:
    echo           git checkout -- .
    echo           git pull
    echo.
    pause
    exit /b 1
)
echo  완료

REM ── requirements.txt 변경 여부 확인 ─────────────────────────
git diff HEAD~1 HEAD --name-only 2>nul | findstr "requirements.txt" > nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo  ⚠️  requirements.txt 변경 감지 — 패키지 업데이트 중...
    if exist "venv\Scripts\activate.bat" (
        call venv\Scripts\activate.bat
    ) else if exist ".venv\Scripts\activate.bat" (
        call .venv\Scripts\activate.bat
    )
    pip install -r requirements.txt --quiet
    echo  패키지 업데이트 완료
)

REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REM  STEP 3 : 앱 재시작
REM ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo  [3/3] 앱 재시작 중...
echo.
call start.bat
