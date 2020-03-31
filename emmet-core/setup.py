# -*- coding: utf-8 -*-
import os
import datetime
from setuptools import setup, find_namespace_packages

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name='emmet-core',
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description='Core Emmet Library',
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url='https://github.com/materialsproject/emmet',
    packages=find_namespace_packages(include=['emmet.*']),
    install_requires=required,
    license='modified BSD',
    zip_safe=False,
)
