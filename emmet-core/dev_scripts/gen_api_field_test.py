"""Generate test for consistency of document models used in API."""

from mp_api.client import MPRester
import json
from importlib_resources import files
from pathlib import Path

test_file = Path(
    files("emmet.core") / ".." / ".." / "tests" / "test_model_fields.py"
).resolve()

document_models = {rester.document_model for rester in MPRester()._all_resters}

model_fields = {}

py_str = '"""Ensure that document models used in API do not change fields."""'
py_str += """
import pytest
from importlib import import_module


"""
for doc_model in sorted(document_models, key=lambda x: f"{x.__module__}.{x.__name__}"):
    model_fields[f"{doc_model.__module__}.{doc_model.__name__}"] = list(
        doc_model.model_fields
    )

py_str += f"ref_model_fields = {json.dumps(model_fields,indent=2)}\n"
py_str += """
@pytest.mark.parametrize('import_str,ref_fields',ref_model_fields.items())
def test_model_field_drift(import_str, ref_fields):
    module, class_name = import_str.rsplit(".",1)
    model_class = getattr(import_module(module),class_name)
    assert set(model_class.model_fields) == set(ref_fields)
"""

test_file.write_text(py_str)
