import datetime

from setuptools import setup

setup(
    name="emmet-cli",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="command line interface for emmet",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=open("../README.md").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=["emmet.cli"],
    scripts=["emmet/cli/bash_scripts/launcher_finder"],
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
