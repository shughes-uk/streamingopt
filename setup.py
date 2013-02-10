from distutils.core import setup
import py2exe , matplotlib

setup(windows=[{'script':'main.py'}],
	data_files=matplotlib.get_py2exe_datafiles(),
	zipfile=None,
	options={'py2xe':{
				 'bundle_files' : 1,
				 'compressed' : True

				 }
			}

	)