"""Stub imports to prevent breakages."""

import warnings

warnings.warn(
    "`emmet.core.mpid_ext` has been deprecated "
    "and will be removed after emmet-core==0.87.0."
)

from emmet.core.mpid import validate_identifier

__all__ = ["validate_identifier"]
