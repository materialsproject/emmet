# Packages

`emmet` is a toolkit of packages that are used in conjunction to create the Materials API (MAPI) from raw calculations on disk. The following package make up this toolkit.

## emmet-core

This is the core package for the `emmet` ecosystem. `emmet.core` is where data models are defined. These data models are the most important part of `emmet` since they dictate what all the other packages have to use, serve, or compute.

There is an additional `emmet.stubs` module that provides `pydantic` compatible stubs for various datatypes commonly used in `emmet`. Many of these are from `pymatgen`. These stubs are 100% functional in-place, meaning they can be used as they would be from pymatgen. The stubs provide additional metadata for the models in `emmet` to use for validation and better documentation.


## emmet-cli

Many of the operations in `emmet` are complex. These range from backing up calculations, to parsing, to setting of build chains, to starting workflows. Since these processes are pretty standard, the `emmet` ecosystem provides a CLI implemented in `emmet.cli`. This makes managing MAPI much easier.


## emmet-builders

The data served via MAPI has to computed via data pipelines. `emmet.builders` defines these operations using the [`maggma`](https://materialsproject.github.io/maggma/) framework to enable well constructed data access, multi- and distributed processing, reporting, and automatic incremental computation.
