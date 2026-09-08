# Canonical task runner. Every target is mirrored as a root pnpm script
# (pnpm dev / test / lint / migrate / eval) so the repo works on machines
# without GNU make.

.PHONY: dev down test test-api test-web lint lint-api lint-web format migrate eval install

install:
	pnpm install
	uv sync --directory apps/api

dev:
	docker compose up --build

down:
	docker compose down

test: test-api test-web

test-api:
	uv run --directory apps/api pytest -q

test-web:
	pnpm --filter web test

lint: lint-api lint-web

lint-api:
	uv run --directory apps/api ruff check .
	uv run --directory apps/api ruff format --check .
	uv run --directory apps/api mypy app

lint-web:
	pnpm --filter web lint
	pnpm exec prettier --check "apps/web/**/*.{ts,tsx,css}" "packages/**/*.ts"

format:
	uv run --directory apps/api ruff format .
	pnpm exec prettier --write "apps/web/**/*.{ts,tsx,css}" "packages/**/*.ts"

migrate:
	uv run --directory apps/api alembic upgrade head

eval:
	uv run --directory apps/api python -m eval.run_eval

eval-golden:
	uv run --directory apps/api python tests/eval/golden/build_golden.py
