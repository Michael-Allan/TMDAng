
PIP=./env/bin/pip3.4
PYTEST=./env/bin/py.test

env:
	virtualenv --python=python3.4 env
	$(PIP) install -e .

test: env
	if [ ! -f $(PYTEST) ]; then \
		$(PIP) install pytest ;\
		$(PIP) install pytest-runfailed ;\
	fi
	cd tests && ../$(PYTEST) -v

testf: env
	cd tests && ../$(PYTEST) --failed -v

testf-clean: env clean-testf
	cd tests && ../$(PYTEST) --failed -v

clean-testf:
	rm -rf tests/.pytest

clean: clean-testf
	rm -rf env build dist

build:
	python setup.py bdist_wheel

