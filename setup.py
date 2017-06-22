#!/usr/bin/env python

import os

from setuptools import setup, find_packages

module_dir = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    setup(
        name='emmet',
        version='0.1',
        description='Emmet is a builder framework for the Materials Project',
        long_description=open(os.path.join(module_dir, 'README.md')).read(),
        url='https://github.com/materialsproject/emmet',
        author='MP team',
        author_email='matproj-develop@googlegroups.com',
        license='modified BSD',
        packages=find_packages(),
        package_data={},
        zip_safe=False,
        # TODO: finalize requirements
        install_requires=[
            'FireWorks>=1.4.0', 'pymatgen>=4.7.1', 'pymatgen-db>=0.5.1',
            'maggma', 'monty>=0.9.5', 'six',
        ],
        classifiers=["Programming Language :: Python :: 3",
                     "Programming Language :: Python :: 3.6",
                     'Development Status :: 2 - Pre-Alpha',
                     'Intended Audience :: Science/Research',
                     'Intended Audience :: System Administrators',
                     'Intended Audience :: Information Technology',
                     'Operating System :: OS Independent',
                     'Topic :: Other/Nonlisted Topic',
                     'Topic :: Scientific/Engineering'],
        test_suite='nose.collector',
        tests_require=['nose']
    )
