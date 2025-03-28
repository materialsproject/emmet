# Packages

`emmet` is a toolkit of packages that are used in conjunction to create the Materials API (MAPI) from raw calculations on disk. The following package make up this toolkit.

## emmet-core

This is the core package for the `emmet` ecosystem. `emmet.core` is where data models are defined. These data models are the most important part of `emmet` since they dictate what all the other packages have to use, serve, or compute.

## emmet-cli-legacy

Many of the operations in `emmet` are complex. These range from backing up calculations, to parsing, to setting of build chains, to starting workflows. Since these processes are pretty standard, the `emmet` ecosystem provides a CLI implemented in `emmet.cli.legacy`. This makes managing MAPI much easier.


## emmet-builders

The data served via MAPI has to computed via data pipelines. `emmet.builders` defines these operations using the [`maggma`](https://materialsproject.github.io/maggma/) framework to enable well constructed data access, multi- and distributed processing, reporting, and automatic incremental computation.
