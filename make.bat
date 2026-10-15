@echo off
setlocal
set TARGET=%1
if "%TARGET%"=="" set TARGET=help

if "%TARGET%"=="help" (
    echo FluentPulse AI — Makefile Commands
    echo   make install           Install/sync project dependencies with uv
    echo   make run               Start the web application server ^(default: http://127.0.0.1:8000^)
    echo   make dev               Start the web server with auto-reload enabled
    echo   make generate          Generate/display today's 25 daily questions ^(all units^)
    echo   make generate-unit     Generate/display 25 daily questions for Unit 1
    echo   make generate-general  Generate/display 25 daily questions for general topics
    echo   make test              Run end-to-end tests
    echo   make clean             Remove Python cache files
    goto :eof
)
if "%TARGET%"=="install" (
    uv sync --active
    goto :eof
)
if "%TARGET%"=="sync" (
    uv sync --active
    goto :eof
)
if "%TARGET%"=="run" (
    uv run --active python main.py
    goto :eof
)
if "%TARGET%"=="dev" (
    uv run --active uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload
    goto :eof
)
if "%TARGET%"=="generate" (
    uv run --active python main.py --generate-only
    goto :eof
)
if "%TARGET%"=="generate-unit" (
    uv run --active python main.py --generate-only --unit 1
    goto :eof
)
if "%TARGET%"=="generate-general" (
    uv run --active python main.py --generate-only --topic general
    goto :eof
)
if "%TARGET%"=="test" (
    uv run --active python -m tests.test_app
    goto :eof
)
if "%TARGET%"=="clean" (
    uv run --active python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
    goto :eof
)
echo Unknown target: %TARGET%
exit /b 2
