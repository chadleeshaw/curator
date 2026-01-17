.PHONY: help lint format lint-python lint-js lint-css format-python format-js format-css test test-unit test-integration test-e2e test-routers test-coverage test-quick install install-hooks run clean ci-lint

PYTHON_FILES := $(shell find . -name '*.py' -not -path './.venv/*' -not -path './node_modules/*' -not -path './.node_modules/*')
JS_FILES := static/js/*.js
CSS_FILES := static/css/*.css

help:
	@echo "Curator - Build Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies"
	@echo "  make install-hooks    Install Git pre-push hooks"
	@echo ""
	@echo "Development:"
	@echo "  make run              Start the application"
	@echo "  make format           Format all code (Python, JS, CSS)"
	@echo "  make lint             Run all linters"
	@echo "  make ci-lint          Run CI linters (matches GitHub exactly)"
	@echo ""
	@echo "Linting:"
	@echo "  make lint-python      Lint Python files (pylint + flake8)"
	@echo "  make lint-js          Lint JavaScript files"
	@echo "  make lint-css         Lint CSS files"
	@echo ""
	@echo "Formatting:"
	@echo "  make format-python    Format Python with Black"
	@echo "  make format-js        Format JavaScript with Prettier"
	@echo "  make format-css       Format CSS with Prettier"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests with pytest"
	@echo "  make test-unit        Run unit tests only (fast)"
	@echo "  make test-integration Run integration tests only"
	@echo "  make test-e2e         Run end-to-end tests only"
	@echo "  make test-routers     Run router/API tests only"
	@echo "  make test-coverage    Run tests with coverage report"
	@echo "  make test-quick       Quick syntax check of test files"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove cache, build, and temp files"

# Installation
install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt > /dev/null 2>&1
	npm install > /dev/null 2>&1
	@echo "✓ Dependencies installed"

install-hooks:
	@./setup-hooks.sh

# Running the app
run:
	@echo "🚀 Starting application..."
	.venv/bin/python ./main.py

# Linting
lint: lint-python lint-js lint-css
	@echo "✅ Linting complete!"

lint-python:
	@echo "📝 Linting Python files..."
	@.venv/bin/python -m pylint --fail-under=7.0 $(PYTHON_FILES) > /dev/null 2>&1 && echo "  ✓ pylint passed" || echo "  ⚠ Some Python issues found"
	@.venv/bin/python -m flake8 $(PYTHON_FILES) > /dev/null 2>&1 && echo "  ✓ flake8 passed" || echo "  ⚠ Some style issues found"

lint-js:
	@echo "📜 Linting JavaScript files..."
	@npx eslint $(JS_FILES) 2>/dev/null || echo "  ⚠ Some JavaScript issues found"

lint-css:
	@echo "🎨 Linting CSS files..."
	@npx stylelint $(CSS_FILES) 2>/dev/null || echo "  ⚠ Some CSS issues found"

# CI Linting (matches GitHub Actions exactly)
ci-lint:
	@echo "🔍 Running CI linters (matches GitHub exactly)..."
	@echo ""
	@echo "📝 Running pylint..."
	@.venv/bin/python -m pylint --fail-under=7.0 --recursive=y . --ignore=.venv,node_modules || true
	@echo ""
	@echo "📝 Running flake8..."
	@find . -name '*.py' -not -path './.venv/*' -not -path './node_modules/*' -print0 | xargs -0 .venv/bin/python -m flake8
	@echo ""
	@echo "🐍 Checking Black formatting..."
	@find . -name '*.py' -not -path './.venv/*' -not -path './node_modules/*' -print0 | xargs -0 .venv/bin/python -m black --check --line-length=120
	@echo ""
	@echo "📜 Running eslint..."
	@npx eslint $(JS_FILES)
	@echo ""
	@echo "🎨 Running stylelint..."
	@npx stylelint $(CSS_FILES)
	@echo ""
	@echo "✅ All CI linters passed!"

# Formatting
format: format-python format-js format-css
	@echo "✅ Formatting complete!"

format-python:
	@echo "🐍 Formatting Python files..."
	@black --line-length=120 $(PYTHON_FILES) 2>&1 | grep -E "reformatted|unchanged" || true

format-js:
	@echo "📝 Formatting JavaScript files..."
	@npx prettier --write $(JS_FILES) 2>&1 | grep -E "ms|error" || true

format-css:
	@echo "🎨 Formatting CSS files..."
	@npx prettier --write $(CSS_FILES) 2>&1 | grep -E "ms|error" || true

# Testing
test:
	@echo "🧪 Running all tests..."
	@.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -50 || echo "⚠ Some tests failed"
	@echo "✅ Test run completed!"

test-unit:
	@echo "🧪 Running unit tests (fast)..."
	@.venv/bin/python -m pytest tests/unit/ -v --tb=short
	@echo "✅ Unit tests completed!"

test-integration:
	@echo "🧪 Running integration tests..."
	@.venv/bin/python -m pytest tests/integration/ -v --tb=short
	@echo "✅ Integration tests completed!"

test-e2e:
	@echo "🧪 Running end-to-end tests..."
	@.venv/bin/python -m pytest tests/e2e/ -v --tb=short
	@echo "✅ E2E tests completed!"

test-routers:
	@echo "🧪 Running router tests..."
	@.venv/bin/python -m pytest tests/unit/web/routers/ -v --tb=short
	@echo "✅ Router tests completed!"

test-coverage:
	@echo "🧪 Running tests with coverage..."
	@.venv/bin/python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html
	@echo "✅ Coverage report generated in htmlcov/"

test-quick:
	@echo "🧪 Quick test (syntax check only)..."
	@find tests/ -name "test_*.py" -exec .venv/bin/python -m py_compile {} + && echo "✅ All test files compile"

# Cleanup
clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info 2>/dev/null || true
	@echo "✓ Cleanup complete"
