.PHONY: help install dev test test-cov lint fmt type-check docs-build docs-serve run collect judge merge verify dry-run dialogue dialogue-live inspect-run select export-gen-e2 export-html split-judging check-judging judge-models verify-quality pilot-items models

PYTHON ?= .venv/bin/python

help: ## Show this help
	@echo "Standard evaluation path (README, Quick Start):"
	@echo "  make select -> make verify MODELS=selection"
	@echo "  -> make collect MODELS=selection"
	@echo "  -> @judge-coordinator in Copilot Chat -> make merge -> make export-html"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	pip install -e .

dev: ## Install all dependencies (including dev)
	pip install -e ".[dev,docs]"
	$(PYTHON) -m pre_commit install
	$(PYTHON) -m pre_commit install --hook-type commit-msg

test: ## Run all tests (Python)
	$(PYTHON) -m pytest --tb=short

test-cov: ## Run tests with a coverage report (requires pytest-cov, see [dev] extras)
	$(PYTHON) -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80 --tb=short

lint: ## Run all linters
	$(PYTHON) -m ruff check .

fmt: ## Auto-format all code
	$(PYTHON) -m ruff format .

type-check: ## Run type checkers
	$(PYTHON) -m mypy src/

docs-build: ## Build documentation and validate links strictly
	$(PYTHON) -m mkdocs build --strict

docs-serve: ## Preview documentation with live reload
	$(PYTHON) -m mkdocs serve

run: ## Phase 1 — collect responses + deterministic eval + security (alias of collect; MODELS=<preset|list> SECURITY=<full|skip> optional)
	$(PYTHON) -m src.main collect $(if $(MODELS),--models "$(MODELS)") $(if $(SECURITY),--security $(SECURITY))
	@echo ""
	@echo "Next step — Phase 2 (required, no extra API cost): in Copilot chat, invoke:"
	@echo "  @judge-coordinator   (runs the 3 blind judges in parallel automatically)"
	@echo "Then Phase 3: make merge"

collect: ## Phase 1 — PAID, calls OpenRouter — collect responses + deterministic eval + security (MODELS=<preset|list> SECURITY=<full|skip> optional, else .env)
	$(PYTHON) -m src.main collect $(if $(MODELS),--models "$(MODELS)") $(if $(SECURITY),--security $(SECURITY))

verify: ## Real but free preflight — API key + TARGET_MODELS against the live OpenRouter catalog (GET /key + GET /models, $0, before a paid run; MODELS=/SECURITY= optional)
	$(PYTHON) -m src.main verify $(if $(MODELS),--models "$(MODELS)") $(if $(SECURITY),--security $(SECURITY))

dry-run: ## Fully offline simulation of the whole pipeline and its HTML report — NO OpenRouter call, NO judge agent (MODELS=/SECURITY= optional)
	$(PYTHON) -m src.main dry-run $(if $(MODELS),--models "$(MODELS)") $(if $(SECURITY),--security $(SECURITY))
	@preview=$$(ls -t data/dry_run/benchmark_preview_*.csv | head -1); \
		$(PYTHON) scripts/export_dashboard_html.py --results "$$preview" \
		--output "$$(dirname "$$preview")/$$(basename "$$preview" .csv | sed 's/^benchmark_preview_/dashboard_preview_/').html"

dialogue: ## Separate, fully offline two-turn quality screen (MODELS= optional)
	$(PYTHON) -m src.dialogue_cli $(if $(MODELS),--models "$(MODELS)")

dialogue-live: ## PAID — separate two-turn quality screen via OpenRouter (MODELS= optional)
	$(PYTHON) -m src.dialogue_cli --live $(if $(MODELS),--models "$(MODELS)")

inspect-run: ## Verify the latest run manifest and artifact checksums
	$(PYTHON) -m src.main inspect-run

select: ## Preview dynamic OpenRouter model selection without starting a benchmark
	$(PYTHON) -m src.main select \
		$(if $(PAID_ONLY),--paid-only) $(if $(FREE_ONLY),--free-only) \
		$(if $(MAX_INPUT_PRICE),--max-input-price $(MAX_INPUT_PRICE)) \
		$(if $(MAX_OUTPUT_PRICE),--max-output-price $(MAX_OUTPUT_PRICE)) \
		$(if $(MIN_CONTEXT),--min-context $(MIN_CONTEXT)) $(if $(LIMIT),--limit $(LIMIT))

judge: ## Phase 2 — open a Copilot judge agent (pick one of the 3 providers)
	@echo "Option A — coordinator (recommended): runs all 3 judges automatically"
	@echo "  @judge-coordinator"
	@echo ""
	@echo "Option B — independent judges (run all 3 in parallel):"
	@echo "  @judge-anthropic  (Claude Sonnet 5)  |  @judge-openai  (GPT-6 Sol)  |  @judge-google  (Gemini 3.8 Flash)"
	@echo ""
	@echo "Pending judging file:"
	@ls data/intermediate/judging_*.json 2>/dev/null | tail -1 || echo "  (none — run make collect first)"

merge: ## Phase 3 — merge Copilot scores + export final results
	$(PYTHON) -m src.main merge

export-html: ## Build the static HTML report (RESULTS=/OUTPUT=/PROFILE= optional, else latest run + enterprise_qa)
	$(PYTHON) scripts/export_dashboard_html.py \
		$(if $(RESULTS),--results "$(RESULTS)") \
		$(if $(OUTPUT),--output "$(OUTPUT)") \
		$(if $(PROFILE),--profile "$(PROFILE)")

split-judging: ## Split the latest (or JUDGING=) blind judging batch into parts the coordinator can forward whole
	$(PYTHON) scripts/split_judging_batch.py $(if $(JUDGING),--judging "$(JUDGING)") $(if $(REPLACE),--replace)

judge-models: ## Preflight: check each judge agent's model is enabled on your Copilot plan; SET="anthropic=Claude Opus 5.5 (copilot)" switches one
	$(PYTHON) scripts/judge_models.py $(if $(SET),--set "$(SET)")

check-judging: ## Validate the latest (or TS=) batch's score files and judge models; QUARANTINE=1 moves invalid ones aside
	$(PYTHON) scripts/check_judging.py $(if $(TS),--timestamp "$(TS)") $(if $(QUARANTINE),--quarantine) $(if $(SKIP_MODEL_AUDIT),--skip-model-audit) $(if $(STRICT),--strict)

verify-quality: ## Recheck one k=1 objective failure twice through OpenRouter (pass ARGS="...")
	$(PYTHON) scripts/verify_quality_reproducibility.py $(ARGS)

pilot-items: ## PAID — try the candidate quality items on real models before they join the suite (MODELS=, ITEMS=id,id optional; without LIVE=1 only lists them)
	$(PYTHON) scripts/pilot_quality_items.py $(if $(LIVE),--live) $(if $(MODELS),--models "$(MODELS)") $(if $(ITEMS),--items "$(ITEMS)")

models: ## List the coherent model-set presets available for MODELS=<name>
	$(PYTHON) -m src.main models

export-gen-e2: ## Export latest benchmark to gen-e2-eval compatible YAML (set PROFILE=<name> to override)
	$(PYTHON) scripts/export_gen_e2_registry.py \
		--results $(shell ls -t results/benchmark_*.json 2>/dev/null | head -1) \
		--output evaluation/candidates/openrouter-security-pricing.yaml \
		--profile $(if $(PROFILE),$(PROFILE),enterprise_qa)
