# -*- coding: utf-8 -*-
from setuptools import find_namespace_packages, setup
from _version import __version__ as fallback_version

if "+" in fallback_version:
    fallback_version = fallback_version.split("+")[0]


setup(
    name="emmet-core",
    use_scm_version={
        "root": "..",
        "relative_to": __file__,
        "write_to": "emmet-core/_version.py",
        "write_to_template": '__version__ = "{version}"',
        "fallback_version": fallback_version,
    },
    setup_requires=["setuptools_scm~=6.0"],
    description="Core Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    package_data={
        "emmet.core.vasp.calc_types": ["*.yaml"],
        "emmet.core.subtrates": ["*.json"],
    },
    include_package_data=True,
    install_requires=[
        "pymatgen>=2021.3,<2023.0",
        "monty>=2021.3,<2023.0",
        "pydantic==1.8.2",
        "pybtex~=0.24",
        "typing-extensions>=3.7,<5.0",
        "robocrys>=0.2.7",
        "matminer>=0.7.3",
    ],
    python_requires=">=3.8",
    license="modified BSD",
    zip_safe=False,
)
