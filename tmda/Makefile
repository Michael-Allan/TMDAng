
PIP=./env/bin/pip3.4
PYTEST=./env/bin/py.test
PYTEST_ARGS=-v --timeout=60


env:
	virtualenv --python=python3.4 env
	$(PIP) install -e .

test: env
	if [ ! -f $(PYTEST) ]; then \
		$(PIP) install pytest ;\
		$(PIP) install pytest-runfailed ;\
		$(PIP) install pytest-timeout ;\
	fi
	cd tests && ../$(PYTEST) $(PYTEST_ARGS)

testf: env
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

testf-clean: env clean-testf
	cd tests && ../$(PYTEST) --failed $(PYTEST_ARGS)

clean-testf:
	rm -rf tests/.pytest

clean: clean-testf
	rm -rf env build dist
	find . -name __pycache__ | xargs rm -rf
	find . -name \*.pyc | xargs rm -f

wheel:
	python3 setup.py bdist_wheel

