
VENV_LOCATION = _venv

.PHONY: check setup ansible collections

help:
	@echo
	@echo "Available targets:"
	@echo "  setup    - Create virtual environment"
	@echo "  check    - Check file syntax for YAML files"
	@echo

setup: _venv ansible collections

$(VENV_LOCATION) :
	@python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,9) else "*** ERROR: Python 3.9+ is required.")'
	python3 -m venv $(VENV_LOCATION)
	@echo "\n === Execute '. setup.sh' to activate environment ===\n"

ansible : $(VENV_LOCATION)
	. $(VENV_LOCATION)/bin/activate; python3 -m pip install -r requirements.txt

collections : ansible
	. $(VENV_LOCATION)/bin/activate; ansible-galaxy collection install -r collections.yml

check:
	yamllint cassandra_cluster *.yml
