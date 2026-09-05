PYTHON ?= python3

.PHONY: help install test test-unsafe test-fenced compare clean

help:
	@echo "Faultline"
	@echo
	@echo "make install       Install development dependencies"
	@echo "make test          Run framework regression tests"
	@echo "make test-unsafe   Reproduce duplicate side effect"
	@echo "make test-fenced   Verify stale-worker fencing"
	@echo "make compare       Run unsafe vs fenced experiment"
	@echo "make clean         Remove local generated state"

install:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest tests -q

test-unsafe:
	faultline test \
		--adapter celery \
		--fault pause \
		--implementation unsafe \
		--invariant at-most-one-effect

test-fenced:
	faultline test \
		--adapter celery \
		--fault pause \
		--implementation fenced \
		--invariant at-most-one-effect

compare:
	faultline compare \
		--adapter celery \
		--fault pause \
		--invariant at-most-one-effect

clean:
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
