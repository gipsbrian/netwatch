# Netwatch — common tasks.  Run `make` or `make help` to list them.
#
# Override settings on the command line, e.g.:
#   make run IFACE=en0
#   make run SUBNET=192.168.0.0/24 PORT=9000
#   make up  NETWATCH_IFACE=eth0

PYTHON  ?= python3
VENV    ?= .venv
PY      := $(VENV)/bin/python
PORT    ?= 8008
HOST    ?= 127.0.0.1
IFACE   ?=
SUBNET  ?=
IMAGE   ?= netwatch:latest
UNAME   := $(shell uname -s)

ARGS := --host $(HOST) --port $(PORT)
ifneq ($(strip $(IFACE)),)
  ARGS += --iface $(IFACE)
endif
ifneq ($(strip $(SUBNET)),)
  ARGS += --subnet $(SUBNET)
endif

.DEFAULT_GOAL := help
.PHONY: help install demo run run-lan open clean \
        docker-build up down logs restart status docker-demo docker-clean

## ---------- Native (macOS, Linux, Windows via WSL/Git Bash) ----------

help: ## Show this list
	@echo "Netwatch — make targets"
	@awk 'BEGIN {FS = ":.*## "} /^## -+/ {gsub(/^## -+ ?| ?-+$$/, ""); printf "\n\033[1m%s\033[0m\n", $$0} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "Variables: PORT=$(PORT) HOST=$(HOST) IFACE=$(or $(IFACE),auto) SUBNET=$(or $(SUBNET),auto)"

$(VENV)/.installed: requirements.txt
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PY) -m pip install -q --upgrade pip
	@$(PY) -m pip install -q -r requirements.txt
	@touch $@
	@echo "netwatch: dependencies installed in $(VENV)"

install: $(VENV)/.installed ## Create the virtualenv and install dependencies (runs automatically)

demo: install ## Run with simulated devices (no sudo needed)
	$(PY) server.py --demo $(ARGS)

run: install ## Scan your real network (asks for your password)
	sudo $(PY) server.py $(ARGS)

run-lan: install ## Like `run`, but reachable from other devices on your network
	sudo $(PY) server.py $(subst --host $(HOST),--host 0.0.0.0,$(ARGS))

open: ## Open the dashboard in your browser
	@if command -v open >/dev/null 2>&1; then open http://localhost:$(PORT); \
	 elif command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:$(PORT); \
	 else echo "Open http://localhost:$(PORT) in your browser"; fi

clean: ## Remove the virtualenv and caches
	rm -rf $(VENV) __pycache__

## ---------- Docker (Linux hosts: Raspberry Pi, home server, NAS) ----------

define DARWIN_WARNING
	@if [ "$(UNAME)" = "Darwin" ]; then \
	  echo "netwatch: note — on macOS, Docker can't see your Wi-Fi, so real scans find nothing."; \
	  echo "          Use 'make run' here, or 'make docker-demo' to try the image."; \
	fi
endef

docker-build: ## Build the Docker image
	docker build -t $(IMAGE) .

up: ## Start in the background with Docker Compose (Linux)
	$(DARWIN_WARNING)
	docker compose up -d --build
	@echo "netwatch: running — http://localhost:$(PORT)  (logs: make logs, stop: make down)"

down: ## Stop and remove the container
	docker compose down

logs: ## Follow the container's logs
	docker compose logs -f netwatch

restart: ## Restart the container
	docker compose restart netwatch

status: ## Show container status and health
	docker compose ps

docker-demo: docker-build ## Run the image with simulated devices (works on any OS)
	docker run --rm -it -p $(PORT):8008 -e NETWATCH_DEMO=1 --name netwatch-demo $(IMAGE)

docker-clean: ## Remove the container, image and cached vendor data
	docker compose down -v --rmi local
