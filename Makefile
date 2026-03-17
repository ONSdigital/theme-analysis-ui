# Makefile for Python (Poetry) template

.PHONY: fmt lint test run docs precommit-install

PY ?= python
PKG ?= theme_analysis_ui

fmt:
	poetry run black .
	poetry run ruff check . --fix

lint:
	poetry run ruff check .
	poetry run black --check .
	poetry run mypy src/$(PKG) tests
	poetry run bandit -q -r src/$(PKG)

test:
	poetry run pytest -q --maxfail=1 --disable-warnings \
	  --cov=src/$(PKG) --cov-report term-missing --cov-fail-under=80

run:
	FLASK_APP=$(PKG).app:create_app poetry run flask --debug run

docs:
	poetry run mkdocs serve -a 127.0.0.1:8000

precommit-install:
	poetry run pre-commit install
