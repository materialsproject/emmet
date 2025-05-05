import datetime

from setuptools import setup

setup(
    name="emmet-cli",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="command line interface for MP contributors",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=open("../README.md").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=["emmet.cli"],
    install_requires=[
        "click",
        "colorama",
        "emmet-core",
    ],
    license="modified BSD",
    zip_safe=False,
    entry_points="""
    [console_scripts]
    emmet=emmet.cli.entry_point:safe_entry_point
    """,
)
