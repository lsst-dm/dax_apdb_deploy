
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
	python -m venv $(VENV_LOCATION)
	@echo "\n === Execute '. $(VENV_LOCATION)/bin/activate' to activate environment ===\n"

ansible : $(VENV_LOCATION)
	. $(VENV_LOCATION)/bin/activate; pip install -r requirements.txt

collections : ansible
	. $(VENV_LOCATION)/bin/activate; ansible-galaxy collection install -r collections.yml

check:
	yamllint cassandra_cluster *.yml
