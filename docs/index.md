
```{toctree}
:caption: Emmet Documentation
:hidden:
packages
settings
CHANGELOG
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

Emmet is a toolkit of packages designed to build the Materials API. The Materials API is the specification of the Materials Project (MP) for defining and dissemenating "materials documents". The core document definitions live in `emmet-core`. The data pipelines that build these documents live in `emmet-builders`. A specialized multi-functional CLI to manage the orchestration of calculation ingestion, backup, and parsing is in `emmet-cli-legacy`. Emmet has been developed by the Materials Project team at Lawrence Berkeley Labs.

Emmet is written in [Python](http://docs.python-guide.org/en/latest/) and supports Python 3.6+.

Emmet fully supports [Optimade API](https://optimade.org) and allows your MP infrastructure data to be exposed under the Optimade spec. It is also internally used to serve the MP [public Optimade endpoint](https://optimade.materialsproject.org).

## Installation from PyPI

Emmet is a toolkit. Due to a refactoring, `emmet` is in alpha status with no published metapackage. Only `emmet-core` is published on the [Python Package Index](https://pypi.org/project/emmet-core/). The preferred tool for installing
packages from _PyPi_ is **pip**. This tool is provided with all modern
versions of Python.

Open your terminal and run the following command.

```shell
pip install --upgrade emmet-core
```

## Installation from source

You can install Maggma directly from a clone of the [Git repository](https://github.com/materialsproject/maggma). This can be done either by cloning the repo and installing from the local clone, or simply installing directly via **git**.

```shell tab="Local Clone"
git clone https://github.com/materialsproject/emmet
cd emmet
pip install -e emmet-core/
```
