.PHONY: setup test lint fmt api web demo report build up docs clean

setup:            ## install python + web dependencies
	uv sync
	cd apps/web && npm install

test:             ## run python tests
	uv run pytest

lint:             ## ruff + typecheck the web app
	uv run ruff check .
	uv run ruff format --check .
	cd apps/web && npm run typecheck

fmt:              ## auto-format python
	uv run ruff check --fix .
	uv run ruff format .

api:              ## run the API with the built-in demo program on :8000
	uv run uvicorn pgmlens_api.main:app --reload --port 8000

web:              ## run the dashboard dev server on :5173 (proxies /api to :8000)
	cd apps/web && npm run dev

demo: build       ## build the dashboard and serve it with the demo program on http://localhost:8000
	uv run python -m pgmlens_api --web apps/web/dist

report:           ## print the analysis of the bundled demo dataset in the terminal
	uv run pgmlens analyze examples/demo-dataset.json

build:            ## production build of the dashboard
	cd apps/web && npm run build

up:               ## full stack via docker compose on :8080
	docker compose up --build

docs:             ## serve the documentation locally
	uv run --with mkdocs-material mkdocs serve

clean:
	rm -rf .venv .pytest_cache .ruff_cache apps/web/node_modules apps/web/dist
