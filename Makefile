.PHONY: help install sync run dev generate generate-unit generate-general test clean

HOST ?= 127.0.0.1
PORT ?= 8000
UNIT ?= 1
TOPIC ?= general

help:
	@echo "FluentPulse AI — Makefile Commands"
	@echo "  make install           Install/sync project dependencies with uv"
	@echo "  make run               Start the web application server (default: http://$(HOST):$(PORT))"
	@echo "  make dev               Start the web server with auto-reload enabled"
	@echo "  make generate          Generate/display today's 25 daily questions (all units)"
	@echo "  make generate-unit     Generate/display 25 daily questions for a specific unit (UNIT=1..6)"
	@echo "  make generate-general  Generate/display 25 daily questions for general topics (TOPIC=general or custom)"
	@echo "  make test              Run end-to-end tests"
	@echo "  make clean             Remove Python cache files"

install:
	uv sync --active

sync: install

run:
	uv run --active python main.py --host $(HOST) --port $(PORT)

dev:
	uv run --active uvicorn app.api:app --host $(HOST) --port $(PORT) --reload

generate:
	uv run --active python main.py --generate-only

generate-unit:
	uv run --active python main.py --generate-only --unit $(UNIT)

generate-general:
	uv run --active python main.py --generate-only --topic "$(TOPIC)"

test:
	uv run --active python -m tests.test_app

clean:
	uv run --active python -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"


