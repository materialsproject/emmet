from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("emmet-builders-legacy")
except PackageNotFoundError:  # pragma: no cover
    # package is not installed
    pass
