"""End-to-end tests of the ``id_format`` query parameter on real resources."""

import json
import os

import pytest
from monty.io import zopen
from fastapi import FastAPI
from pydantic import BaseModel
from pymatgen.core import Structure
from starlette.testclient import TestClient

from emmet.api.core.settings import MAPISettings
from emmet.api.query_operator import IdFormatQuery
from emmet.api.resource.utils import CollectionWithKey
from emmet.api.routes.dois.resources import dois_resource
from emmet.api.routes.materials.alloys.resources import alloy_pairs_resource
from emmet.api.routes.materials.conversion_electrodes.resources import (
    conversion_electrodes_resource,
)
from emmet.api.routes.materials.insertion_electrodes.resources import (
    insertion_electrodes_resource,
)
from emmet.api.routes.materials.materials.resources import (
    blessed_tasks_resource,
    find_structure_resource,
    materials_resource,
)
from emmet.api.routes.materials.robocrys.resources import robo_search_resource
from emmet.api.routes.materials.similarity.resources import (
    similarity_feature_vector_resource,
)
from emmet.api.routes.materials.substrates.resources import substrates_resource
from emmet.api.routes.materials.summary.resources import summary_resource
from emmet.api.routes.materials.tasks.resources import entries_resource
from emmet.api.routes.materials.thermo.resources import thermo_resource
from emmet.core.electrode import ConversionElectrodeDoc, InsertionElectrodeDoc
from emmet.core.summary import SummaryDoc
from emmet.core.thermo import ThermoDoc
from emmet.core.vasp.material import MaterialsDoc


# Many endpoints implicitly restrict on license and deprecation state
_DEFAULT_CRITERIA = {"builder_meta": {"license": "BY-C"}, "deprecated": False}


def _entry(material_id="mp-aaacidek", task_id="aaadytct", run_type="GGA", **extra):
    """An entry, as stored in production: `entry_id` is a dumped `EntryID`."""
    return {
        "@module": "pymatgen.core.entries",
        "@class": "ComputedStructureEntry",
        "energy": -1.60028005,
        "composition": {"Mg": 1},
        "entry_id": {"identifier": material_id, "suffix": run_type, "separator": "-"},
        "correction": 0,
        "energy_adjustments": [],
        "parameters": {"potcar_spec": [], "run_type": run_type},
        "data": {
            "oxide_type": "None",
            "aspherical": True,
            "last_updated": "2024-11-21 21:25:11.212435+00:00",
            "task_id": task_id,
            "material_id": material_id,
            "license": "BY-C",
            "run_type": run_type,
        },
        **extra,
    }


def _entry_ids(entry: dict) -> tuple:
    return (
        entry["entry_id"]["identifier"],
        entry["data"]["task_id"],
        entry["data"]["material_id"],
    )


# What the entry above becomes
LEGACY_ENTRY_IDS = ("mp-1056702", "mp-1805667", "mp-1056702")
ALPHA_ENTRY_IDS = ("mp-aaacidek", "aaadytct", "mp-aaacidek")


def _assert_entry_untouched_but_for_ids(entry: dict, original: dict):
    assert entry["entry_id"]["suffix"] == original["entry_id"]["suffix"]
    assert entry["entry_id"]["separator"] == original["entry_id"]["separator"]
    assert entry["energy"] == original["energy"]
    assert entry["parameters"] == original["parameters"]
    assert entry["data"]["license"] == original["data"]["license"]


def _stored(model: type[BaseModel], **values) -> dict:
    """A document as stored in a collection of `model`.

    Refuses fields the model does not have, so that tests cannot rely on
    identifiers which are not actually stored.
    """
    known = set(model.model_fields) | {
        info.alias for info in model.model_fields.values() if info.alias
    }
    unknown = set(values) - known
    assert not unknown, f"{model.__name__} has no fields {sorted(unknown)}"
    return values


def _client(resource) -> TestClient:
    app = FastAPI()
    app.include_router(resource.router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_summary_nested_ids_follow_id_format(mock_database):
    collection = mock_database["summary"]
    await collection.insert_one(
        {
            **_DEFAULT_CRITERIA,
            **_stored(
                SummaryDoc,
                material_id="mp-aaaaaaft",
                formula_pretty="Si",
                task_ids=["mp-aaaaaaft", "mp-aaaaaaan"],
                decomposes_to=[
                    {"material_id": "mp-aaaaaaan", "formula": "Si", "amount": 1.0}
                ],
                origins=[{"name": "structure", "task_id": "mp-aaaaaaft"}],
            ),
        }
    )
    client = _client(summary_resource(CollectionWithKey(collection)))
    params = {"_fields": "material_id,task_ids,decomposes_to,origins"}

    legacy = client.get("/summary/", params={**params, "id_format": "legacy"})
    assert legacy.status_code == 200
    doc = legacy.json()["data"][0]
    assert doc["material_id"] == "mp-149"
    assert doc["task_ids"] == ["mp-149", "mp-13"]
    assert doc["decomposes_to"][0]["material_id"] == "mp-13"
    assert doc["decomposes_to"][0]["amount"] == 1.0
    assert doc["origins"][0]["task_id"] == "mp-149"

    alpha = client.get("/summary/", params={**params, "id_format": "alpha"})
    doc = alpha.json()["data"][0]
    assert doc["material_id"] == "mp-aaaaaaft"
    assert doc["decomposes_to"][0]["material_id"] == "mp-aaaaaaan"
    assert doc["origins"][0]["task_id"] == "aaaaaaft"

    # Without the parameter, documents come back as stored
    default = client.get("/summary/", params=params).json()["data"][0]
    assert default["decomposes_to"][0]["material_id"] == "mp-aaaaaaan"


@pytest.mark.asyncio
async def test_thermo_decomposition_products(mock_database):
    collection = mock_database["thermo"]
    await collection.insert_one(
        {
            **_DEFAULT_CRITERIA,
            **_stored(
                ThermoDoc,
                material_id="mp-aaaaaaft",
                decomposes_to=[{"material_id": "mp-aaaaaaan", "amount": 1.0}],
                decomposition_enthalpy_decomposes_to=[
                    {"material_id": "mp-aaaaaaan", "amount": 1.0}
                ],
            ),
        }
    )
    client = _client(thermo_resource(CollectionWithKey(collection, "thermo_id")))
    res = client.get(
        "/thermo/",
        params={
            "_fields": "material_id,decomposes_to,decomposition_enthalpy_decomposes_to",
            "id_format": "legacy",
        },
    )
    doc = res.json()["data"][0]
    assert doc["material_id"] == "mp-149"
    assert doc["decomposes_to"][0]["material_id"] == "mp-13"
    assert doc["decomposition_enthalpy_decomposes_to"][0]["material_id"] == "mp-13"


def _electrode_object(klass: str, **containers) -> dict:
    return {"@module": "pymatgen.apps.battery", "@class": klass, **containers}


def _all_entries(electrode_object: dict):
    """Every entry held anywhere in an electrode object."""
    for key in (
        "working_ion_entry",
        "stable_entries",
        "unstable_entries",
        "entries_charge",
        "entries_discharge",
        "entry_charge",
        "entry_discharge",
    ):
        value = electrode_object.get(key)
        if isinstance(value, dict):
            yield value
        elif isinstance(value, list):
            yield from value
    for pair in electrode_object.get("voltage_pairs", []):
        yield from _all_entries(pair)


@pytest.mark.asyncio
async def test_insertion_electrode_ids(mock_database):
    collection = mock_database["insertion_electrodes"]
    await collection.insert_one(
        _stored(
            InsertionElectrodeDoc,
            material_ids=["mp-aaaaaaft", "mp-aaaaaaan"],
            id_charge="mp-aaaaaaft",
            adj_pairs=[{"id_charge": "mp-aaaaaaft", "id_discharge": "mp-aaaaaaan"}],
            electrode_object=_electrode_object(
                "InsertionElectrode",
                working_ion_entry=_entry(),
                stable_entries=[_entry(), _entry()],
                unstable_entries=[_entry()],
                voltage_pairs=[
                    {
                        "voltage": 1.0,
                        "working_ion_entry": _entry(),
                        "entry_charge": _entry(),
                        "entry_discharge": _entry(),
                    }
                ],
            ),
        )
    )
    client = _client(
        insertion_electrodes_resource(CollectionWithKey(collection, "battery_id"))
    )
    params = {"_fields": "material_ids,id_charge,adj_pairs,electrode_object"}

    legacy = client.get(
        "/insertion_electrodes/", params={**params, "id_format": "legacy"}
    )
    assert legacy.status_code == 200, legacy.text
    doc = legacy.json()["data"][0]
    assert doc["material_ids"] == ["mp-149", "mp-13"]
    assert doc["id_charge"] == "mp-149"
    assert doc["adj_pairs"] == [{"id_charge": "mp-149", "id_discharge": "mp-13"}]

    # every entry, however deeply nested
    entries = list(_all_entries(doc["electrode_object"]))
    assert len(entries) == 1 + 2 + 1 + 3
    for entry in entries:
        assert _entry_ids(entry) == LEGACY_ENTRY_IDS
        _assert_entry_untouched_but_for_ids(entry, _entry())

    alpha = client.get(
        "/insertion_electrodes/", params={**params, "id_format": "alpha"}
    )
    for entry in _all_entries(alpha.json()["data"][0]["electrode_object"]):
        assert _entry_ids(entry) == ALPHA_ENTRY_IDS


@pytest.mark.asyncio
async def test_conversion_electrode_ids(mock_database):
    collection = mock_database["conversion_electrodes"]
    await collection.insert_one(
        _stored(
            ConversionElectrodeDoc,
            material_ids=["mp-aaaaaaft", "mp-aaaaaaan"],
            electrode_object=_electrode_object(
                "ConversionElectrode",
                working_ion_entry=_entry(),
                voltage_pairs=[
                    {
                        "voltage": 1.0,
                        "working_ion_entry": _entry(),
                        "entries_charge": [_entry(), _entry()],
                        "entries_discharge": [_entry()],
                        "rxn": {"reactants": {"Li": 1.0}, "products": {"Li2O": 1.0}},
                    }
                ],
            ),
        )
    )
    client = _client(
        conversion_electrodes_resource(CollectionWithKey(collection, "battery_id"))
    )
    res = client.get(
        "/conversion_electrodes/",
        params={"_fields": "material_ids,electrode_object", "id_format": "legacy"},
    )
    assert res.status_code == 200, res.text
    doc = res.json()["data"][0]
    assert doc["material_ids"] == ["mp-149", "mp-13"]

    entries = list(_all_entries(doc["electrode_object"]))
    assert len(entries) == 1 + 1 + 2 + 1
    for entry in entries:
        assert _entry_ids(entry) == LEGACY_ENTRY_IDS
    # formulas of the reaction are not identifiers
    rxn = doc["electrode_object"]["voltage_pairs"][0]["rxn"]
    assert rxn == {"reactants": {"Li": 1.0}, "products": {"Li2O": 1.0}}


@pytest.mark.asyncio
async def test_thermo_entries(mock_database):
    collection = mock_database["thermo"]
    await collection.insert_one(
        {
            **_DEFAULT_CRITERIA,
            **_stored(
                ThermoDoc,
                material_id="mp-aaacidek",
                entries={"r2SCAN": _entry(run_type="r2SCAN")},
            ),
        }
    )
    client = _client(thermo_resource(CollectionWithKey(collection, "thermo_id")))
    res = client.get(
        "/thermo/", params={"_fields": "material_id,entries", "id_format": "legacy"}
    )
    assert res.status_code == 200, res.text
    doc = res.json()["data"][0]
    entry = doc["entries"]["r2SCAN"]
    assert _entry_ids(entry) == LEGACY_ENTRY_IDS
    assert entry["entry_id"]["suffix"] == "r2SCAN"


def _materials_doc() -> dict:
    return {
        **_DEFAULT_CRITERIA,
        **_stored(
            MaterialsDoc,
            material_id="mp-aaaaaaft",
            task_ids=["mp-aaaaaaft", "mp-aaaaaaan"],
            calc_types={
                "mp-aaaaaaft": "GGA Structure Optimization",
                "mp-aaaaaaan": "GGA Static",
            },
            task_types={"mp-aaaaaaft": "Structure Optimization"},
            run_types={"mp-aaaaaaft": "GGA"},
            entries={
                "GGA": _entry(),
                # stored under the alias of the field
                "r2SCAN": _entry("mp-aaacjdvk", "aaadxciu", "r2SCAN"),
            },
        ),
    }


@pytest.mark.asyncio
async def test_materials_dict_keys_and_entries(mock_database):
    collection = mock_database["materials"]
    await collection.insert_one(_materials_doc())
    client = _client(materials_resource(CollectionWithKey(collection)))
    params = {"_fields": "material_id,task_ids,calc_types,task_types,run_types,entries"}

    legacy = client.get("/core/", params={**params, "id_format": "legacy"})
    assert legacy.status_code == 200, legacy.text
    doc = legacy.json()["data"][0]
    assert doc["task_ids"] == ["mp-149", "mp-13"]
    # identifiers used as keys
    assert doc["calc_types"] == {
        "mp-149": "GGA Structure Optimization",
        "mp-13": "GGA Static",
    }
    assert doc["task_types"] == {"mp-149": "Structure Optimization"}
    assert doc["run_types"] == {"mp-149": "GGA"}
    # identifiers nested in entries
    assert _entry_ids(doc["entries"]["GGA"]) == LEGACY_ENTRY_IDS
    _assert_entry_untouched_but_for_ids(doc["entries"]["GGA"], _entry())
    assert doc["entries"]["r2SCAN"]["entry_id"]["suffix"] == "r2SCAN"

    alpha = client.get("/core/", params={**params, "id_format": "alpha"})
    doc = alpha.json()["data"][0]
    assert list(doc["calc_types"]) == ["aaaaaaft", "aaaaaaan"]
    assert _entry_ids(doc["entries"]["GGA"]) == ALPHA_ENTRY_IDS


@pytest.mark.asyncio
async def test_blessed_tasks_entries(mock_database):
    collection = mock_database["materials"]
    await collection.insert_one(_materials_doc())
    client = _client(blessed_tasks_resource(CollectionWithKey(collection)))
    res = client.get(
        "/core/blessed_tasks/", params={"run_type": "GGA", "id_format": "legacy"}
    )
    assert res.status_code == 200, res.text
    doc = res.json()["data"][0]
    assert doc["material_id"] == "mp-149"
    assert _entry_ids(doc["entries"]["GGA"]) == LEGACY_ENTRY_IDS


@pytest.mark.asyncio
async def test_find_structure_honours_id_format(mock_database):
    structure = Structure.from_file(
        os.path.join(MAPISettings().TEST_FILES, "Si_mp_149.cif"), primitive=True
    )
    collection = mock_database["materials"]
    await collection.insert_one(
        {
            "material_id": "mp-aaaaaaft",
            "structure": structure.as_dict(),
            "composition_reduced": dict(structure.composition.to_reduced_dict),
        }
    )
    client = _client(find_structure_resource(CollectionWithKey(collection)))

    legacy = client.post(
        "/core/find_structure/",
        params={"id_format": "legacy"},
        json=structure.as_dict(),
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["data"][0]["material_id"] == "mp-149"

    alpha = client.post(
        "/core/find_structure/", params={"id_format": "alpha"}, json=structure.as_dict()
    )
    assert alpha.json()["data"][0]["material_id"] == "mp-aaaaaaft"

    default = client.post("/core/find_structure/", json=structure.as_dict())
    assert default.json()["data"][0]["material_id"] == "mp-aaaaaaft"


# Endpoints which did not accept `id_format` before, and now do.
_NEWLY_SUPPORTED = [
    dois_resource,
    alloy_pairs_resource,
    blessed_tasks_resource,
    find_structure_resource,
    robo_search_resource,
    similarity_feature_vector_resource,
    substrates_resource,
    entries_resource,
]


@pytest.mark.parametrize("factory", _NEWLY_SUPPORTED, ids=lambda f: f.__name__)
def test_endpoints_accept_id_format(factory, mock_database):
    resource = factory(CollectionWithKey(mock_database["anything"]))
    id_ops = [op for op in resource.query_operators if isinstance(op, IdFormatQuery)]
    assert len(id_ops) == 1
    assert id_ops[0].id_paths, "no identifier fields were found for this endpoint"
    app = FastAPI()
    app.include_router(resource.router)
    assert "id_format" in str(app.openapi()["paths"])


@pytest.mark.asyncio
async def test_substrates_ids(mock_database):
    collection = mock_database["substrates"]
    await collection.insert_one({"film_id": "mp-aaaaaaft", "sub_id": "mp-aaaaaaan"})
    client = _client(substrates_resource(CollectionWithKey(collection, "film_id")))
    res = client.get("/substrates/", params={"id_format": "legacy"})
    assert res.json()["data"][0] == {"film_id": "mp-149", "sub_id": "mp-13"}


def _task_docs() -> list[dict]:
    """Real task documents, stored the way production does: bare alpha task ids."""
    with zopen(
        os.path.join(MAPISettings().TEST_FILES, "tasks_Li_Fe_V.json.gz"), "rt"
    ) as file:
        tasks = json.load(file)[:2]
    for task, task_id in zip(tasks, ("aaaaaaft", "aaaaaaan")):
        task["task_id"] = task_id
    return tasks


@pytest.mark.asyncio
async def test_task_entries_ids(mock_database):
    collection = mock_database["tasks"]
    await collection.insert_many(_task_docs())
    # a task without the output needed to build an entry
    await collection.insert_one({"task_id": "aaaaaaao", "output": {}})
    client = _client(entries_resource(CollectionWithKey(collection, "task_id")))
    ids = "task_ids=mp-149,mp-13,mp-14"

    def get(**params):
        res = client.get(f"/tasks/entries/?{ids}", params=params)
        assert res.status_code == 200, res.text
        return {d["task_id"]: d for d in res.json()["data"]}

    legacy = get(id_format="legacy")
    for task_id in ("mp-149", "mp-13"):
        # the entry is generated from the task, its id must agree with the task
        assert legacy[task_id]["entry"]["@class"] == "ComputedStructureEntry"
        assert legacy[task_id]["entry"]["entry_id"] == task_id

    alpha = get(id_format="alpha")
    for task_id in ("aaaaaaft", "aaaaaaan"):
        assert alpha[task_id]["entry"]["entry_id"] == task_id

    stored = get()
    assert set(stored) == {"aaaaaaft", "aaaaaaan", "aaaaaaao"}
    assert stored["aaaaaaft"]["entry"]["entry_id"] == "aaaaaaft"

    # no entry could be generated: the message is left alone
    message = stored["aaaaaaao"]["entry"]
    assert isinstance(message, str)
    assert get(id_format="legacy")["mp-14"]["entry"] == message
    assert get(id_format="alpha")["aaaaaaao"]["entry"] == message


@pytest.mark.asyncio
async def test_alloy_pair_ids(mock_database):
    collection = mock_database["alloys"]
    pair_id = {"id_a": "mp-aaacqdyw", "id_b": "mp-aaaabjgp", "separator": "_"}
    await collection.insert_one({"pair_id": pair_id})
    client = _client(alloy_pairs_resource(CollectionWithKey(collection, "pair_id")))

    legacy = client.get("/alloys/", params={"id_format": "legacy"})
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["data"][0]["pair_id"] == {
        "id_a": "mp-1197842",
        "id_b": "mp-23831",
        "separator": "_",
    }

    stored = client.get("/alloys/").json()["data"][0]["pair_id"]
    assert stored == pair_id


@pytest.mark.asyncio
async def test_jcesr_accepts_id_format_and_returns_documents_untouched(mock_database):
    # Molecule ids have no legacy form, nothing is converted
    from emmet.api.routes.legacy.jcesr.resources import jcesr_resource

    collection = mock_database["jcesr"]
    await collection.insert_one({"task_id": "mol-1", "formula_alphabetical": "H2O"})
    client = _client(jcesr_resource(CollectionWithKey(collection, "task_id")))

    stored = client.get("/jcesr/")
    assert stored.status_code == 200, stored.text
    for fmt in ("legacy", "alpha"):
        res = client.get("/jcesr/", params={"id_format": fmt})
        assert res.status_code == 200, res.text
        assert res.json()["data"] == stored.json()["data"]
