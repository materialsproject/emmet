#!/usr/bin/env python

from setuptools import setup, find_packages
from pathlib import Path

module_dir = Path(__file__).resolve().parent


with open(module_dir / "README.md") as f:
    long_desc = f.read()


setup(
    name="emmet",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="Emmet is the builder framework for the Materials Project",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    license="modified BSD",
    install_requires=["emmet-core", "emmet-cli", "emmet-builders"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",
        "Operating System :: OS Independent",
        "Topic :: Other/Nonlisted Topic",
        "Topic :: Scientific/Engineering",
    ],
    python_requires=">=3.6",
)
