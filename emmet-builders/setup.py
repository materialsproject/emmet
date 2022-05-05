from setuptools import find_namespace_packages, setup
from _version import __version__ as fallback_version

if "+" in fallback_version:
    fallback_version = fallback_version.split("+")[0]


setup(
    name="emmet-builders",
    use_scm_version={
        "root": "..",
        "relative_to": __file__,
        "write_to": "emmet-builders/_version.py",
        "write_to_template": '__version__ = "{version}"',
        "fallback_version": fallback_version,
    },
    setup_requires=["setuptools_scm"],
    description="Builders for the Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=["emmet-core", "maggma>=0.46.1"],
    python_requires=">=3.8",
    license="modified BSD",
    zip_safe=False,
)
