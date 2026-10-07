# ruff: noqa: E501

"""Sphinx configuration file."""

import os
import sys

sys.path.insert(0, os.path.abspath("../../"))
project = "emmet"
copyright = "2025, The Materials Project"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx_autodoc_typehints",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

exclude_patterns = ["emmet-builders-legacy", "emmet-cli-legacy", "test*.py"]

source_suffix = {".rst": "restructuredtext", ".md": "restructuredtext"}

language = "en"

# autodoc options
# use type hints
autodoc_typehints = "description"
autosummary_imported_members = False
autodoc_preserve_defaults = True
autoclass_content = "class"
autodoc_member_order = "bysource"

# don't overwrite summary but generate them if they don't exist
autosummary_generate = True
autosummary_generate_overwrite = True

# Should erdantic work in the future with our pydantic models, uncomment these:
# autodoc_pydantic_model_show_json = False
# autodoc_pydantic_model_erdantic_figure = True
# graphviz_output_format = "svg"

# HTML styling
html_theme = "sphinx_rtd_theme"
html_show_sphinx = False
html_show_sourcelink = False
html_title = "emmet"


def _skip_member(app, what, name, obj, skip, options):
    """Hide members that should not get their own API reference page.

    - ``TYPE_CHECKING``: imported from ``typing`` in many modules; it is not
      part of the emmet API.
    - The objects re-exported lazily by ``emmet.core.io.pymatgen``: these are
      pymatgen objects documented by pymatgen itself. Resolving them would also
      require every optional pymatgen add-on to be installed in the docs build.
    """
    if name == "TYPE_CHECKING":
        return True

    from emmet.core.io import pymatgen as pmg_io

    # Skip only if this member *is* the pymatgen re-export (or could not be
    # resolved), so emmet objects that happen to share a name are unaffected.
    if name in pmg_io._class_map:
        try:
            reexport = getattr(pmg_io, name)
        except Exception:
            return True
        if obj is None or obj is reexport:
            return True
    return None


def setup(app):
    app.connect("autodoc-skip-member", _skip_member)
