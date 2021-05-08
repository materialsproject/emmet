import datetime
from pathlib import Path
from setuptools import setup, find_namespace_packages
from setuptools_scm import get_version, DEFAULT_LOCAL_SCHEME

version = get_version(root="..", relative_to=__file__, version_scheme="post-release")
version = version.split(".post")[0]


setup(
    name="emmet-builders",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="Builders for the Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=[
        f"emmet-core~={version}",
        "pymatgen~=2021.3",
        "pydantic[email]~=1.8",
        "typing-extensions~=3.7",
        "maggma~=0.26.0",
    ],
    license="modified BSD",
    zip_safe=False,
)
