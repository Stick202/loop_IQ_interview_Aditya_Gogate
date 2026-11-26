# Thin wrapper around the Python runner. Without make: python -m pipeline <command>
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
BOOT := python
else
PY := .venv/bin/python
BOOT := python3
endif

.PHONY: setup run sample extract load build report docs test
setup:
	$(BOOT) -m venv .venv
	$(PY) -m pip install -r requirements.txt
run sample extract load build report docs:
	$(PY) -m pipeline $@
test:
	$(PY) -m pytest -q
