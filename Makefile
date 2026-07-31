.PHONY: check

.DEFAULT_GOAL := check

check:
	basedpyright
	python -m unittest discover -s tests
	ruff check src tests
	ruff format --check src tests
