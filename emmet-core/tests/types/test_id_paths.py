"""Tests for `emmet.core.types.id_paths`."""

from __future__ import annotations

from typing import NotRequired, TypedDict, TypeVar

import pytest
from pydantic import BaseModel, Field

from emmet.core.types.id_paths import (
    KEYS,
    VALUES,
    apply_to_path,
    find_identifier_paths,
    parse_id_path,
)
from emmet.core.types.pymatgen_types.computed_entries_adapter import EntryIDType
from emmet.core.types.typing import (
    IdentifierType,
    MaterialIdentifierType,
    TaskIdentifierType,
    format_compound_identifier,
    format_identifier,
    format_task_id,
)
from emmet.core.utils import type_override


class Leaf(BaseModel):
    material_id: IdentifierType | None = None
    amount: float = 0.0


class Node(BaseModel):
    task_id: TaskIdentifierType
    children: list[Node] | None = None


class Member(TypedDict):
    id_: NotRequired[MaterialIdentifierType | None]


class Pair(TypedDict):
    members: NotRequired[list[Member] | None]
    id_a: NotRequired[MaterialIdentifierType | None]


PairVar = TypeVar("PairVar", int, Pair)


@type_override({"narrowed": MaterialIdentifierType})
class Doc(BaseModel):
    material_id: MaterialIdentifierType
    task_ids: list[TaskIdentifierType] = []
    maybe: IdentifierType | int | None = None
    narrowed: MaterialIdentifierType | int | None = None
    leaves: list[Leaf] | None = None
    by_method: dict[str, list[TaskIdentifierType]] | None = None
    by_name: dict[str, Leaf] = {}
    calc_types: dict[TaskIdentifierType, str] | None = None
    pair: tuple[IdentifierType, float, int] | None = None
    node: Node | None = None
    typed: PairVar | None = None
    entry_id: EntryIDType | None = None
    hidden: IdentifierType | None = Field(None, exclude=True)
    aliased: IdentifierType | None = Field(None, alias="other_name")
    not_an_id: str = "mp-149"
    number: int = 0


def _names(paths):
    return {path: formatter.__name__ for path, formatter in paths.items()}


def test_find_identifier_paths():
    assert _names(find_identifier_paths(Doc)) == {
        ("material_id",): "format_identifier",
        ("task_ids",): "format_task_id",
        ("maybe",): "format_identifier",
        ("narrowed",): "format_identifier",
        ("leaves", "material_id"): "format_identifier",
        ("by_method", VALUES): "format_task_id",
        ("by_name", VALUES, "material_id"): "format_identifier",
        ("calc_types", KEYS): "format_task_id",
        ("pair", 0): "format_identifier",
        ("node", "task_id"): "format_task_id",
        # Node.children is Node again: a path cannot describe unbounded depth
        ("typed", "members", "id_"): "format_identifier",
        ("typed", "id_a"): "format_identifier",
        ("entry_id",): "format_entry_id",
        # not serialized by the model, but possibly stored somewhere else
        ("hidden",): "format_identifier",
        # stored under either of its names
        ("aliased",): "format_identifier",
        ("other_name",): "format_identifier",
    }


def test_find_identifier_paths_finds_nothing_in_a_model_without_identifiers():
    class NoIds(BaseModel):
        a: str
        b: list[int]
        c: dict[str, str]

    assert find_identifier_paths(NoIds) == {}


def test_find_identifier_paths_is_not_misled_by_str_fields_holding_ids():
    assert ("not_an_id",) not in find_identifier_paths(Doc)


def test_find_identifier_paths_of_served_models():
    # regression guard for the nested identifiers `id_format` is expected to reach
    from emmet.core.summary import SummaryDoc
    from emmet.core.vasp.material import MaterialsDoc

    summary = _names(find_identifier_paths(SummaryDoc))
    assert summary[("material_id",)] == "format_identifier"
    assert summary[("task_ids",)] == "format_task_id"
    assert summary[("decomposes_to", "material_id")] == "format_identifier"
    assert summary[("phonon_IDs", VALUES)] == "format_task_id"

    materials = _names(find_identifier_paths(MaterialsDoc))
    for field in ("calc_types", "task_types", "run_types"):
        assert materials[(field, KEYS)] == "format_task_id"
    for alias in ("GGA", "R2SCAN", "r2SCAN", "HSE", "HSE06"):
        assert materials[("entries", alias, "entry_id")] == "format_entry_id"
        assert materials[("entries", alias, "data", "task_id")] == "format_task_id"


# ---------------------------------------------------------------------------
# parse_id_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dotted, expected",
    [
        ("material_id", ("material_id",)),
        ("adj_pairs.id_charge", ("adj_pairs", "id_charge")),
        ("phonon_IDs.*", ("phonon_IDs", VALUES)),
        ("calc_types.*key", ("calc_types", KEYS)),
        ("dos.0", ("dos", 0)),
        (("a", KEYS), ("a", KEYS)),
    ],
)
def test_parse_id_path(dotted, expected):
    assert parse_id_path(dotted) == expected


# ---------------------------------------------------------------------------
# apply_to_path
# ---------------------------------------------------------------------------


def test_apply_to_keys_preserves_order_and_values():
    doc = {"types": {"mp-aaaaaaan": 1, "not an id": 2, "mp-aaaaaaft": 3}}
    apply_to_path(doc, ("types", KEYS), format_task_id, legacy=True)
    assert list(doc["types"].items()) == [("mp-13", 1), ("not an id", 2), ("mp-149", 3)]


def test_apply_to_values_and_through_lists():
    doc = {
        "a": {"x": ["mp-aaaaaaft", "mp-aaaaaaan"], "y": []},
        "b": [{"c": {"d": "mp-aaaaaaft"}}, {"c": None}, {}],
    }
    apply_to_path(doc, ("a", VALUES), format_identifier, legacy=True)
    apply_to_path(doc, ("b", "c", "d"), format_identifier, legacy=True)
    assert doc == {
        "a": {"x": ["mp-149", "mp-13"], "y": []},
        "b": [{"c": {"d": "mp-149"}}, {"c": None}, {}],
    }


def test_apply_to_composite_identifiers():
    doc = {"entries": {"GGA": {"entry_id": "mp-aaaaaaft-GGA"}, "SCAN": {}}}
    apply_to_path(
        doc, ("entries", VALUES, "entry_id"), format_compound_identifier, legacy=True
    )
    assert doc["entries"]["GGA"]["entry_id"] == "mp-149-GGA"


def test_apply_to_a_position():
    doc = {"dos": ["mp-aaaaaaft", {"not": "an id"}, 1]}
    apply_to_path(doc, ("dos", 0), format_task_id, legacy=True)
    assert doc["dos"] == ["mp-149", {"not": "an id"}, 1]


@pytest.mark.parametrize(
    "doc",
    [
        {},
        {"a": None},
        {"a": "mp-aaaaaaft"},
        {"a": []},
        {"a": [None, "junk", 1]},
        {"a": {"not an id": None}},
        {"a": ("mp-aaaaaaft",)},  # immutable
    ],
)
def test_apply_tolerates_unexpected_shapes(doc):
    before = repr(doc)
    apply_to_path(doc, ("a", "b"), format_identifier, legacy=True)
    apply_to_path(doc, ("a", KEYS), format_identifier, legacy=True)
    apply_to_path(doc, ("a", 5), format_identifier, legacy=True)
    assert repr(doc) == before


# ---------------------------------------------------------------------------
# format_entry_id: entry ids are stored as {identifier, suffix, separator}
# ---------------------------------------------------------------------------


def test_format_entry_id_dict_form():
    from emmet.core.types.pymatgen_types.computed_entries_adapter import (
        format_entry_id,
    )

    stored = {"identifier": "mp-aaacidek", "suffix": "r2SCAN", "separator": "-"}
    before = dict(stored)

    legacy = format_entry_id(stored, legacy=True)
    assert legacy == {"identifier": "mp-1056702", "suffix": "r2SCAN", "separator": "-"}
    assert format_entry_id(legacy, legacy=False) == stored
    assert stored == before  # not mutated
    assert legacy is not stored


@pytest.mark.parametrize(
    "value, legacy, expected",
    [
        ("mp-aaacidek-GGA", True, "mp-1056702-GGA"),
        ("mp-1056702-GGA", False, "mp-aaacidek-GGA"),
        (None, True, None),
        ("", True, ""),
        ({}, True, {}),
        (
            {"identifier": None, "suffix": "GGA"},
            True,
            {"identifier": None, "suffix": "GGA"},
        ),
        (5, True, 5),
    ],
)
def test_format_entry_id_other_shapes(value, legacy, expected):
    from emmet.core.types.pymatgen_types.computed_entries_adapter import (
        format_entry_id,
    )

    assert format_entry_id(value, legacy=legacy) == expected


def test_entry_ids_are_found_through_every_entry_container():
    from emmet.core.electrode import InsertionElectrodeDoc
    from emmet.core.thermo import ThermoDoc
    from emmet.core.vasp.material import MaterialsDoc

    for model, prefix in [
        (MaterialsDoc, ("entries", "GGA")),
        (ThermoDoc, ("entries", VALUES)),
        (InsertionElectrodeDoc, ("electrode_object", "working_ion_entry")),
    ]:
        paths = _names(find_identifier_paths(model))
        assert paths[(*prefix, "entry_id")] == "format_entry_id"
        assert paths[(*prefix, "data", "task_id")] == "format_task_id"
        assert paths[(*prefix, "data", "material_id")] == "format_identifier"
