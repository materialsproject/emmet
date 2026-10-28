"""Which identifiers does each endpoint convert on `id_format`?

The identifier fields of an endpoint are discovered from its response model.
This snapshot makes any change in what is converted visible in review: adding
or retyping a field of a model changes the snapshot of every endpoint serving it.

To accept a change, regenerate the snapshot with
`UPDATE_ID_FORMAT_SNAPSHOT=1 pytest emmet-api/tests/mapi/test_id_format_snapshot.py`
"""

import importlib
import inspect
import json
import os
import pkgutil
from pathlib import Path

import pytest

import emmet.api.routes as routes
from emmet.api.query_operator import IdFormatQuery
from emmet.api.resource.utils import CollectionWithKey
from emmet.core.types.id_paths import KEYS, VALUES

SNAPSHOT = Path(__file__).parent / "id_format_paths.json"

# Not registered in `material_resources.py`, and fails to be built
NOT_SERVED = {
    "emmet.api.routes.materials.charge_density.resources:charge_density_resource"
}


def _dotted(path) -> str:
    return ".".join(
        "*" if seg is VALUES else "*key" if seg is KEYS else str(seg) for seg in path
    )


def _resource_factories():
    for module_info in pkgutil.walk_packages(routes.__path__, "emmet.api.routes."):
        if not module_info.name.endswith(".resources"):
            continue
        module = importlib.import_module(module_info.name)
        for name, func in inspect.getmembers(module, inspect.isfunction):
            key = f"{module_info.name}:{name}"
            if (
                func.__module__ == module_info.name
                and name.endswith("_resource")
                and key not in NOT_SERVED
            ):
                yield key.removeprefix("emmet.api.routes."), func


def _current(store) -> dict:
    out = {}
    for key, factory in _resource_factories():
        resource = factory(store)
        id_ops = [
            op
            for op in getattr(resource, "query_operators", [])
            if isinstance(op, IdFormatQuery)
        ]
        assert len(id_ops) <= 1, f"{key} has several IdFormatQuery operators"
        out[key] = {
            "sub_path": resource.sub_path,
            "id_format": (
                sorted(
                    f"{_dotted(path)} -> {formatter.__name__}"
                    for path, formatter in id_ops[0].id_paths.items()
                )
                if id_ops
                else None
            ),
        }
    return dict(sorted(out.items()))


@pytest.mark.asyncio
async def test_id_format_paths_snapshot(mock_database):
    current = _current(CollectionWithKey(mock_database["anything"]))

    if os.environ.get("UPDATE_ID_FORMAT_SNAPSHOT"):
        SNAPSHOT.write_text(json.dumps(current, indent=1) + "\n")

    assert current == json.loads(SNAPSHOT.read_text())


@pytest.mark.asyncio
async def test_endpoints_without_id_format_are_known(mock_database):
    """An endpoint serving identifiers should accept `id_format`."""
    current = _current(CollectionWithKey(mock_database["anything"]))
    without = sorted(k for k, v in current.items() if v["id_format"] is None)

    # None of these are about materials (user settings, ...), or are not
    # registered in `material_resources.py` (charge density), or are molecule
    # endpoints which have not been looked at (vibrations).
    assert without == [
        "_consumer.resources:settings_resource",
        "_general_store.resources:general_store_resource",
        "_messages.resources:messages_resource",
        "materials.charge_density.resources:charge_density_url_resource",
        "materials.mpcomplete.resources:mpcomplete_resource",
        "molecules.vibrations.resources:vibration_resource",
    ]


@pytest.mark.asyncio
async def test_endpoints_serving_no_materials_identifiers_accept_id_format(
    mock_database,
):
    """Accepted for consistency, but nothing is converted: no MP identifiers
    are returned, or they have no legacy form (molecules)."""
    current = _current(CollectionWithKey(mock_database["anything"]))
    accepted_but_inert = sorted(k for k, v in current.items() if v["id_format"] == [])
    assert accepted_but_inert == [
        "legacy.jcesr.resources:jcesr_resource",
        "materials.materials.resources:formula_autocomplete_resource",
        "materials.synthesis.resources:synth_resource",
        "molecules.summary.resources:summary_resource",
    ]
