from setuptools import find_namespace_packages, setup

setup(
    name="emmet-cli",
    use_scm_version={"root": "..", "relative_to": __file__},
    setup_requires=["setuptools_scm"],
    description="command line interface for MP contributors",
    author="The Materials Project",
    author_email="feedback@materialsproject.org",
    long_description=open("../README.md").read(),  # noqa: SIM115
    long_description_content_type="text/markdown",
    url="https://github.com/materialsproject/emmet",
    packages=find_namespace_packages(include=["emmet.*"]),
    install_requires=[
        "click",
        "colorama",
        "emmet-core",
        "pymatgen-io-validation>=0.1.0rc1",
        "psutil>=5.9.0",
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
            "blake3",
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
    entry_points="""
    [console_scripts]
    emmet=emmet.cli.entry_point:safe_entry_point
    """,
)
