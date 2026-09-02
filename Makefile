.PHONY: help install lint test format type security ci clean

help:
	@echo "tts-clip dev tasks:"
	@echo "  make install   - install dev tools via pacman/pip"
	@echo "  make lint      - ruff check + format check + shellcheck + qmllint + jq"
	@echo "  make test      - pytest"
	@echo "  make format    - ruff format"
	@echo "  make type      - mypy --strict"
	@echo "  make security  - bandit + gitleaks"
	@echo "  make ci        - run the same checks CI runs"
	@echo "  make clean     - remove caches"

install:
	sudo pacman -S --needed --noconfirm ruff mypy bandit shellcheck gitleaks jq yamllint qmllint python-pytest python-pytest-cov

lint:
	ruff check .
	ruff format --check .
	shellcheck -s bash install.sh
	qmllint -I /usr/share/omarchy/shell BarWidget.qml
	jq . manifest.json > /dev/null

test:
	pytest -v --cov=tts_clip --cov-report=term-missing tests/

format:
	ruff format .

type:
	mypy --strict tts_clip.py

security:
	bandit -c pyproject.toml -r .
	gitleaks detect --source . --no-banner

ci: lint type security test
	@echo "all checks passed"

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache tests/__pycache__ __pycache__
	find . -name __pycache__ -type d -exec rm -rf {} +
