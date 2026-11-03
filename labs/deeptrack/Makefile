.DEFAULT_GOAL := help
ARKHETYPO ?= $(HOME)/workspaces/damien/e-arkhetypo
LANGFUSE := $(ARKHETYPO)/stack/watch/langfuse/compose.yml

help:             ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

sync:             ## install the environment
	uv sync

stack:            ## Langfuse (house stack) + ontoref/ontoval, detached
	docker compose -f $(LANGFUSE) up -d
	docker compose up -d

down:             ## stop the lab's servers and Langfuse
	docker compose down
	docker compose -f $(LANGFUSE) down

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
	uv run pytest -q -p no:tach -m integration

check: lint types arch test ## the full local gate

tools:            ## each ontology server's tools and schemas
	uv run deeptrack tools

chat:             ## talk to the agents (needs Vertex creds: see .env.example)
	uv run --env-file .env deeptrack chat

.PHONY: help sync stack down lint types arch test integration check tools chat
