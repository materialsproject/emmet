# -*- coding: utf-8 -*-
import os
import datetime
from setuptools import setup

SETUP_PTH = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SETUP_PTH, 'requirements.txt')) as f:
    required = f.read().splitlines()

setup(
    name='emmet-cli',
    version=datetime.datetime.today().strftime('%Y.%m.%d'),
    description='command line interface for emmet',
    author='Patrick Huck',
    author_email='phuck@lbl.gov',
    url='https://github.com/materialsproject/emmet',
    packages=['emmet.cli'],
    install_requires=required,
    license='modified BSD',
    zip_safe=False,
    entry_points='''
    [console_scripts]
    emmet=emmet.scripts.emmet:cli
    ''',
)
