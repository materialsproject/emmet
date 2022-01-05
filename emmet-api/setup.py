# -*- coding: utf-8 -*-
from setuptools import find_namespace_packages, setup

setup(
    name="emmet-api",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm~=6.0"],
    description="Emmet API Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    package_data={},
    include_package_data=True,
    install_requires=["fastapi", "maggma", "uvicorn", "gunicorn", "boto3"],
    license="modified BSD",
    zip_safe=False,
)
