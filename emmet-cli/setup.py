import datetime

from setuptools import setup

setup(
    name="mp-contrib-cli",
    version=datetime.datetime.today().strftime("%Y.%m.%d"),
    description="command line interface for MP contributors",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=open("../README.md").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=["mp_contrib.cli"],
    install_requires=[
        "click",
        "colorama",
    ],
    license="modified BSD",
    zip_safe=False,
    entry_points="""
    [console_scripts]
    mp_contrib=mp_contrib.cli.entry_point:safe_entry_point
    """,
)
