import os

from setuptools import find_namespace_packages, setup

readme_path = os.path.join(os.path.dirname(__file__), "..", "README.md")
if os.path.exists(readme_path):
    with open(readme_path) as f:
        long_description = f.read()
else:
    long_description = "Archival Emmet Library"


setup(
    name="emmet-archive",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="Archival Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=[
        "emmet-core",
        "h5py",
        "zarr",
        "pyarrow",
        "pandas",
        "pymatgen>=2025.3.10",
        "pymatgen-io-validation>=0.1.0rc2",
    ],
    extras_require={
        "ase": [
            "ase>=3.23.0",
        ],
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
    },
    python_requires=">=3.9",
    license="modified BSD",
    zip_safe=False,
)
