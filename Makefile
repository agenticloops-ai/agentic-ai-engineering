.PHONY: help check fix verify sync-all clean
.DEFAULT_GOAL := help

# Module and lesson directories (pattern: NN-*)
MODULES := $(wildcard [0-9][0-9]-*)
LESSONS := $(wildcard [0-9][0-9]-*/[0-9][0-9]-*)

help: ## Show commands
	@echo "make check    - lint, format, type check"
	@echo "make fix      - auto-fix lint/format issues"
	@echo "make verify   - verify all scripts import correctly"
	@echo "make sync-all - install deps for all lessons"
	@echo "make clean    - remove cache files"

check: ## Lint, format check, and type check
	@uv run ruff check $(MODULES)
	@uv run ruff format --check $(MODULES)
	@uv run mypy $(MODULES) --ignore-missing-imports || true

fix: ## Auto-fix lint and format issues
	@uv run ruff check --fix $(MODULES)
	@uv run ruff format $(MODULES)

verify: ## Verify all scripts compile and imports work
	@echo "Verifying scripts..."
	@failed=0; \
	for lesson in $(LESSONS); do \
		if [ -f "$$lesson/pyproject.toml" ]; then \
			for script in $$lesson/*.py; do \
				if [ -f "$$script" ]; then \
					script_name=$$(basename $$script); \
					module_name=$${script_name%.py}; \
					if ! cd $$lesson && uv run python -c "import $$module_name" > /dev/null 2>&1; then \
						echo "  ✗ $$script"; \
						failed=1; \
					fi; \
					cd - > /dev/null; \
				fi \
			done \
		fi \
	done; \
	if [ $$failed -eq 1 ]; then \
		exit 1; \
	else \
		echo "✓ All scripts OK"; \
	fi

sync-all: ## Install dependencies for all lessons
	@for lesson in $(LESSONS); do \
		if [ -f "$$lesson/pyproject.toml" ]; then \
			echo "Syncing $$lesson..."; \
			cd $$lesson && uv sync --quiet && cd - > /dev/null; \
		fi \
	done

clean: ## Remove cache files
	@find . -type d \( -name "__pycache__" -o -name "*.egg-info" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" \) -exec rm -rf {} + 2>/dev/null || true
	@find . -type f \( -name ".coverage" -o -name "*.pyc" \) -delete 2>/dev/null || true
	@echo "✓ Clean"
