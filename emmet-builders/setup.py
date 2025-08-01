import os
from setuptools import find_namespace_packages, setup

readme_path = os.path.join(os.path.dirname(__file__), "..", "README.md")
if os.path.exists(readme_path):
    with open(readme_path) as f:
        long_description = f.read()
else:
    long_description = "Emmet Builders Library"

setup(
    name="emmet-builders",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="Builders for the Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=long_description,  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    include_package_data=True,
    install_requires=[
        "emmet-core[all]",
        "maggma>=0.57.6",
        "matminer>=0.9.1",
        "solvation-analysis>=0.4.0",
        "MDAnalysis>=2.7.0",
    ],
    extras_require={
        "test": [
            "pre-commit",
            "pytest",
            "pytest-cov",
            "pycodestyle",
            "pydocstyle",
            "flake8",
            "mypy",
            "mypy-extensions",
            "types-setuptools",
            "types-requests",
            "wincertstore",
        ],
        "docs": [
            "mkdocs",
            "mkdocs-material<8.3",
            "mkdocs-material-extensions",
            "mkdocs-minify-plugin",
            "mkdocstrings",
            "mkdocs-awesome-pages-plugin",
            "mkdocs-markdownextradata-plugin",
            "mkdocstrings[python]",
            "livereload",
            "jinja2",
        ],
        "ml": ["emmet-core[ml]"],
        "openmm": ["transport-analysis>=0.1.0"],
    },
    python_requires=">=3.10",
    license="modified BSD",
    zip_safe=False,
)
