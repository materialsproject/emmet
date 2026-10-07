# Packages

`emmet` is a toolkit of packages that are used in conjunction to create the Materials API (MAPI) from raw calculations on disk. The following packages make up this toolkit.

## emmet-core

This is the core package for the `emmet` ecosystem. `emmet.core` is where data models are defined. These data models are the most important part of `emmet` since they dictate what all the other packages have to use, serve, or compute.

## emmet-builders

The data served via MAPI has to be computed via data pipelines. `emmet.builders` provides the transformation step of those pipelines as a set of framework-agnostic functions: each `build_*` function takes a list of input documents (for example, `ValidationTaskDoc` or `BaseBuilderInput` models) and returns the corresponding `emmet.core` documents, such as `MaterialsDoc`, `ThermoDoc`, or `SummaryDoc`.

Data access, scheduling, and parallelization are deliberately left to the caller, so these functions can be embedded in whatever pipeline or workflow framework is in use. Where a builder needs a complete set of related inputs (for example, all tasks sharing a formula when grouping tasks into materials), this requirement is noted in the function's docstring.

Build defaults (allowed task types, structure matching tolerances, etc.) are controlled through `EmmetBuildSettings`; see [Settings Management](settings.md).

```{note}
Releases of `emmet-builders` prior to 0.87.0 were built on the [`maggma`](https://materialsproject.github.io/maggma/) `Builder`/`Store` framework. That implementation is preserved in the repository under `emmet-builders-legacy`; if you depend on it, pin `emmet-builders<0.87`.
```
