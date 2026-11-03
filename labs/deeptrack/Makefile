.DEFAULT_GOAL := help

help:             ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

sync:             ## install the environment
	uv sync

env:              ## create .env from .env.example if missing
	@test -f .env || cp .env.example .env

stack: env        ## the lab's stack (labs-*), detached, waiting until healthy
	docker compose up -d --wait

down:             ## stop the lab's stack, keep its volumes
	docker compose down

purge:            ## stop the lab's stack and delete its volumes
	docker compose down -v

lint:             ## ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

types:            ## ty static type check
	uv run ty check

arch:             ## tach import contracts
	uv run tach check

test:             ## unit suite, no services needed
	uv run pytest -q -p no:tach

integration:      ## scripted turns against the live stack (make stack first)
	uv run --env-file .env pytest -q -p no:tach -m integration

check: lint types arch test ## the full local gate

tools:            ## each ontology server's tools and schemas
	uv run deeptrack tools

chat:             ## talk to the agents (needs Vertex creds: see .env.example)
	uv run --env-file .env deeptrack chat

.PHONY: help sync env stack down purge lint types arch test integration check tools chat
