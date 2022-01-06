# -*- coding: utf-8 -*-
from setuptools import find_namespace_packages, setup
from setuptools_scm import get_version

version = get_version(root="..", relative_to=__file__, version_scheme="post-release")
version = version.split(".post")[0]

setup(
    name="emmet-api",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="Emmet API Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=[
        f"emmet-core~={version}",
        "fastapi",
        "maggma",
        "uvicorn",
        "gunicorn",
        "boto3",
    ],
    license="modified BSD",
    zip_safe=False,
)
