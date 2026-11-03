.DEFAULT_GOAL := help
-include .env
SERVER_PORT := $(or $(LABS_SERVER_PORT),28103)

help:             ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

sync:             ## install the environment
	uv sync

env:              ## write .env from .env.example with fresh random secrets (never overwrites)
	@test -f .env || while IFS= read -r line; do \
		case "$$line" in *@secret*) echo "$${line%@secret*}$$(openssl rand -hex 32)";; *) echo "$$line";; esac; \
	done < .env.example > .env

stack: env        ## restart the lab's stack: down whatever is up (volumes kept), then up and wait until healthy
	docker compose down --remove-orphans
	@### the web's node_modules volume is born root-owned; the dev server runs as the host user.
	docker compose run --rm --no-deps --user root --entrypoint chown labs-agui $(or $(LABS_UID),1000):$(or $(LABS_GID),1000) /app/node_modules
	docker compose up -d --wait

dev: env          ## the AG-UI server (Granian, reload) on 127.0.0.1:$(SERVER_PORT); `make down` stops it
	@echo $$$$ > .dev.pid; exec uv run granian --interface asgi --host 127.0.0.1 --port $(SERVER_PORT) \
		--reload --reload-paths src deeptrack.api.app:app

down: env         ## stop everything, up or not: the dev server and the stack (volumes kept)
	@test -f .dev.pid && kill $$(cat .dev.pid) 2>/dev/null; rm -f .dev.pid
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

integration:      ## scripted turns against the live stack (make stack first), no model
	uv run pytest -q -p no:tach -m "integration and not llm"

bench:            ## the ontology A/B (BENCH.md) on the real model; R=3 repeats, RESUME=reports/ab-….jsonl to continue
	uv run python tests/benchmark/deeptrack/ab.py --repeats $(or $(R),3) $(if $(RESUME),--resume $(RESUME),)

questions:        ## PREGUNTAS.md on the real model and the live stack — structural assertions
	uv run pytest -q -p no:tach -m llm -rA

check: lint types arch test ## the full local gate

tools:            ## each ontology server's tools and schemas
	uv run deeptrack tools

chat:             ## talk to the agents (needs Vertex creds: see .env.example)
	uv run deeptrack chat

.PHONY: help sync env stack dev down questions bench purge lint types arch test integration check tools chat
