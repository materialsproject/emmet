import datetime
from pathlib import Path
from setuptools import setup, find_namespace_packages

with open(Path(__file__).parent / "requirements.txt") as f:
    required = f.read().splitlines()

setup(
    name="emmet-builders",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="Builders for the Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=required,
    license="modified BSD",
    zip_safe=False,
)
