.PHONY: check

.DEFAULT_GOAL := check

check:
	basedpyright
	ruff check src
	ruff format --check src
