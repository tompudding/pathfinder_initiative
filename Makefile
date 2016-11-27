vmaccess.so: vmaccess.pyx
	python setup.py build_ext --inplace
