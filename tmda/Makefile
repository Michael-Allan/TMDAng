
env:
	virtualenv env
	./env/bin/pip install -e .

test: env
	if [ ! -f ./env/bin/py.test ]; then ./env/bin/pip install pytest ; fi
	./env/bin/py.test 

clean:
	rm -rf env build dist

build:
	python setup.py bdist_wheel

