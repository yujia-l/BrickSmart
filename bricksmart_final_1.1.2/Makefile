PYTHON ?= python
PYTEST ?= pytest
TEST_RUNS_ROOT ?= .test-runs

.PHONY: test build api regression regression-bird regression-airplane-reference regression-airplane-standard-kit clean-test-runs

test:
	$(PYTEST) -q

build:
	$(PYTHON) -m build

api:
	PYTHONPATH=backend uvicorn bricksmart.app:app --reload

regression:
	$(PYTEST) -q backend/tests/test_regression_baselines.py

regression-bird:
	BRICKSMART_RUNS_ROOT=$(TEST_RUNS_ROOT) PYTHONPATH=backend $(PYTHON) -m bricksmart.build_cli --contract contract://bird-standard-kit --inventory config/inventory/standard_kit.yaml --project-root . --run-id bird-live-check --clean-output

regression-airplane-reference:
	BRICKSMART_RUNS_ROOT=$(TEST_RUNS_ROOT) PYTHONPATH=backend $(PYTHON) -m bricksmart.build_cli --contract contract://airplane-reference --inventory config/inventory/unlimited.yaml --project-root . --run-id airplane-reference-unlimited-live-check --clean-output

regression-airplane-standard-kit:
	BRICKSMART_RUNS_ROOT=$(TEST_RUNS_ROOT) PYTHONPATH=backend $(PYTHON) -m bricksmart.build_cli --contract contract://airplane-standard-kit --inventory config/inventory/standard_kit.yaml --project-root . --run-id airplane-standard-kit-live-check --clean-output

clean-test-runs:
	rm -rf $(TEST_RUNS_ROOT)
