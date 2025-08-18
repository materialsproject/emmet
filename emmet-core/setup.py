import os

from setuptools import find_namespace_packages, setup

readme_path = os.path.join(os.path.dirname(__file__), "..", "README.md")
if os.path.exists(readme_path):
    with open(readme_path) as f:
        long_description = f.read()
else:
    long_description = "Core Emmet Library"


setup(
    name="emmet-core",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm>=8"],
    description="Core Emmet Library",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    package_data={
        "emmet.core.vasp.calc_types": ["*.yaml"],
        "emmet.core.qchem.calc_types": ["*.yaml"],
        "emmet.core.subtrates": ["*.json"],
    },
    include_package_data=True,
    install_requires=[
        "pymatgen>=2024.6.10",
        "monty>=2024.2.2",
        "pydantic>=2.0",
        "pydantic-settings>=2.0",
        "pymatgen-io-validation>=0.1.0",
        "pybtex~=0.24",
        "typing-extensions>=3.7",
    ],
    extras_require={
        "all": [
            "seekpath>=2.0.1",
            "robocrys>=0.2.11",
            "pymatgen-analysis-defects>=2024.7.18",
            "pymatgen-analysis-diffusion>=2024.7.15",
            "pymatgen-analysis-alloys>=0.0.6",
            "solvation-analysis>=0.4.1",
            "transport-analysis",
            "MDAnalysis>=2.7.0",
            "pyarrow",
        ],
        "ml": ["matcalc>=0.3.1"],
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
            "custodian",
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
    python_requires=">=3.10",
    license="modified BSD",
    zip_safe=False,
)
