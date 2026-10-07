
```{toctree}
:caption: Emmet Documentation
:hidden:
packages
settings
```

```{toctree}
:caption: Reference
:hidden:
reference_index
```

# Emmet

<h1 align="center">
  <img alt="emmet logo" src="https://raw.githubusercontent.com/materialsproject/emmet/main/docs/images/logo_w_text.svg" width="300px">
</h1>

[![Pytest Status](https://github.com/materialsproject/emmet/actions/workflows/testing.yml/badge.svg?branch=main)](https://github.com/materialsproject/emmet/actions?query=workflow%3Atesting+branch%3Amain)
[![Code Coverage](https://codecov.io/gh/materialsproject/emmet/branch/main/graph/badge.svg)](https://codecov.io/gh/materialsproject/emmet)

## What is Emmet?

Emmet is a toolkit of packages designed to build the Materials API. The Materials API is the specification of the Materials Project (MP) for defining and dissemenating "materials documents". The core document definitions live in `emmet-core`. The functions that transform raw calculation data into these documents live in `emmet-builders`, and the API server that serves them lives in `emmet-api`. Emmet has been developed by the Materials Project team at Lawrence Berkeley Labs.

Emmet is written in [Python](http://docs.python-guide.org/en/latest/) and supports Python 3.12+.

Emmet fully supports [Optimade API](https://optimade.org) and allows your MP infrastructure data to be exposed under the Optimade spec. It is also internally used to serve the MP [public Optimade endpoint](https://optimade.materialsproject.org).

## Installation from PyPI

Emmet is a toolkit with no published metapackage. Each component is published separately on the Python Package Index: [`emmet-core`](https://pypi.org/project/emmet-core/), [`emmet-builders`](https://pypi.org/project/emmet-builders/), and [`emmet-api`](https://pypi.org/project/emmet-api/). The preferred tool for installing packages from _PyPI_ is **pip**. This tool is provided with all modern versions of Python.

Open your terminal and install the packages you need, for example:

```shell
pip install --upgrade emmet-core emmet-builders
```

## Installation from source

You can install Emmet directly from a clone of the [Git repository](https://github.com/materialsproject/emmet). Each package lives in its own subdirectory and is installed individually.

```shell
git clone https://github.com/materialsproject/emmet
cd emmet
pip install -e emmet-core/
pip install -e emmet-builders/
```
