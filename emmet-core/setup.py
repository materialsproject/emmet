# -*- coding: utf-8 -*-
import os
import datetime
from setuptools import setup

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name='emmet-core',
    version=datetime.datetime.today().strftime('%Y.%m.%d'),
    description='core emmet library',
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url='https://github.com/materialsproject/emmet',
    packages=['emmet.core'],
    install_requires=required,
    license='modified BSD',
    zip_safe=False,
)
