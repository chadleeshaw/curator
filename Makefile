.PHONY: help lint format lint-python lint-js lint-css format-python format-js format-css test install run clean

PYTHON_FILES := $(shell find . -name '*.py' -not -path './.venv/*' -not -path './node_modules/*' -not -path './.node_modules/*')
JS_FILES := static/js/*.js
CSS_FILES := static/css/*.css

help:
	@echo "Curator - Build Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make run              Start the application"
	@echo "  make format           Format all code (Python, JS, CSS)"
	@echo "  make lint             Run all linters"
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
	@echo "  make test             Run all tests"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove cache, build, and temp files"

# Installation
install:
	@echo "📦 Installing dependencies..."
	pip install -r requirements.txt > /dev/null 2>&1
	npm install > /dev/null 2>&1
	@echo "✓ Dependencies installed"

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
	@echo "🧪 Running tests..."
	@.venv/bin/python tests/test_clients.py && \
		.venv/bin/python tests/test_config.py && \
		.venv/bin/python tests/test_database.py && \
		.venv/bin/python tests/test_factory.py && \
		.venv/bin/python tests/test_processor_download.py && \
		.venv/bin/python tests/test_processor_importer.py && \
		.venv/bin/python tests/test_processor_organizer.py && \
		.venv/bin/python tests/test_processor_scheduler.py && \
		.venv/bin/python tests/test_provider_metadata.py && \
		.venv/bin/python tests/test_provider_search.py
	@echo "✅ All tests completed!"

# Cleanup
clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info 2>/dev/null || true
	@echo "✓ Cleanup complete"
