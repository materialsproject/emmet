# -*- coding: utf-8 -*-
from setuptools import find_namespace_packages, setup

with open("../_version.py") as file:
    for line in file.readlines():
        lsplit = line.split("=")
        if lsplit[0].strip() == "__version__":
            fallback_version = lsplit[1].strip().replace('"', "").split("+")[0]

setup(
    name="emmet-api",
    use_scm_version={
        "root": "..",
        "relative_to": __file__,
        "write_to": "_version.py",
        "write_to_template": '__version__ = "{version}"',
        "fallback_version": fallback_version,
    },
    setup_requires=["setuptools_scm"],
    description="Emmet API Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=[
        f"emmet-core~={fallback_version}",
        "fastapi",
        "maggma",
        "uvicorn",
        "gunicorn",
        "boto3",
    ],
    license="modified BSD",
    zip_safe=False,
)
