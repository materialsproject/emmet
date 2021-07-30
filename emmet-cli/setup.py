# -*- coding: utf-8 -*-
import datetime

from setuptools import setup

setup(
    name="emmet-cli",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="command line interface for emmet",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=["emmet.cli"],
    install_requires=[
        "log4mongo",
        "click",
        "colorama",
        "mongogrant",
        "atomate",
        "mgzip",
        "slurmpy",
        "github3.py",
        "hpsspy",
        "multiprocessing-logging",
        "dotty-dict",
        "emmet-core",
    ],
    license="modified BSD",
    zip_safe=False,
    entry_points="""
    [console_scripts]
    emmet=emmet.cli.entry_point:safe_entry_point
    """,
)
