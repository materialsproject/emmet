"""Tests for `emmet.core.types.introspection`.

Annotations are written with `from __future__ import annotations` on purpose:
`TypedDict`s then hold forward references, which must be resolved in the
module the `TypedDict` is declared in.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
    Any,
    ForwardRef,
    Literal,
    NotRequired,
    Optional,
    TypedDict,
    TypeVar,
    Union,
)

import _forward_refs  # sibling module, see its docstring
import pytest
from pydantic import BaseModel, Field

from emmet.core.types.introspection import (
    Kind,
    classify,
    model_fields,
    resolve_forward_ref,
    typeddict_fields,
)
from emmet.core.types.typing import IdentifierType
from emmet.core.utils import type_override


class Color(Enum):
    RED = "red"


class Leaf(BaseModel):
    value: int


class Tree(BaseModel):
    leaf: Leaf | None = None
    branches: list[Tree] = []
    hidden: str | None = Field(None, exclude=True)
    renamed: IdentifierType | None = Field(None, alias="other_name")
    plain: Annotated[int, Field(gt=0)] = 1


@type_override({"plain": str})
class Overridden(BaseModel):
    plain: int | None = None


class Inner(TypedDict):
    value: int


class Outer(TypedDict):
    inner: NotRequired[Inner | None]
    inners: NotRequired[list[Inner]]


Pair = TypeVar("Pair", int, Outer)


@pytest.mark.parametrize(
    "tp, kind, args",
    [
        (Any, Kind.ANY, ()),
        (int, Kind.CLASS, ()),
        (Path, Kind.CLASS, ()),
        (Color, Kind.ENUM, ()),
        (list[int], Kind.SEQUENCE, (int,)),
        (set[str], Kind.SEQUENCE, (str,)),
        (tuple[int, ...], Kind.SEQUENCE, (int,)),
        (tuple[int, str], Kind.TUPLE, (int, str)),
        (dict[str, int], Kind.MAPPING, (str, int)),
        (Literal["a", "b"], Kind.LITERAL, ("a", "b")),
        (int | None, Kind.UNION, (int,)),
        (Optional[int], Kind.UNION, (int,)),  # noqa: UP045
        (Union[int, str, None], Kind.UNION, (int, str)),  # noqa: UP007
        (NotRequired[list[int]], Kind.SEQUENCE, (int,)),
        (Leaf, Kind.MODEL, ()),
        (Inner, Kind.TYPEDDICT, ()),
    ],
)
def test_classify(tp, kind, args):
    shape = classify(tp)
    assert shape.kind is kind
    assert shape.args == args


def test_classify_annotated_keeps_metadata():
    marker = object()
    shape = classify(Annotated[int, marker])
    assert shape.kind is Kind.ANNOTATED
    assert shape.args == (int,)
    assert shape.metadata == (marker,)


def test_classify_typevar_resolves_to_second_constraint():
    assert classify(Pair).kind is Kind.TYPEDDICT
    assert classify(Pair).origin is Outer


def test_classify_does_not_confuse_str_with_a_sequence():
    assert classify(str).kind is Kind.CLASS
    assert classify(list[str]).args == (str,)


def test_resolve_forward_ref_prefers_the_module_of_the_reference():
    # The namespace is only used for references which do not know their module
    ref = ForwardRef("Leaf", module=__name__)
    assert resolve_forward_ref(ref, {"Leaf": "wrong"}) is Leaf
    assert resolve_forward_ref("Leaf", {"Leaf": Leaf}) is Leaf
    with pytest.raises(NameError, match="DoesNotExist"):
        resolve_forward_ref("DoesNotExist", {"Leaf": Leaf})


def test_arrowize_resolves_forward_references_nested_in_containers():
    # These used to fail: references nested in containers do not know their
    # module and were evaluated in the namespace of `emmet.core.arrow`
    pa = pytest.importorskip("pyarrow")
    from emmet.core.arrow import arrowize

    inner = pa.struct([pa.field("value", pa.int64())])
    assert arrowize(_forward_refs.InList) == pa.struct([pa.field("x", pa.list_(inner))])
    assert arrowize(_forward_refs.InOptional) == pa.struct([pa.field("x", inner)])
    assert arrowize(_forward_refs.InDict) == pa.struct(
        [pa.field("x", pa.map_(pa.string(), inner))]
    )


def test_arrowize_resolves_stringified_annotations():
    pa = pytest.importorskip("pyarrow")
    from emmet.core.arrow import arrowize

    inner = pa.struct([pa.field("value", pa.int64())])
    assert arrowize(Outer) == pa.struct(
        [pa.field("inner", inner), pa.field("inners", pa.list_(inner))]
    )


def test_typeddict_forward_references_are_resolved():
    assert typeddict_fields(Outer)["inner"] == NotRequired[Inner | None]

    shape = classify(Outer)
    inner = shape.child(shape.fields()["inner"])
    assert inner.kind is Kind.UNION
    assert shape.child(inner.args[0]).origin is Inner


def test_model_fields():
    fields = model_fields(Tree)
    assert "hidden" not in fields
    assert "hidden" in model_fields(Tree, include_excluded=True)

    assert "other_name" not in fields
    assert model_fields(Tree, include_aliases=True)["other_name"] == fields["renamed"]

    # type overrides replace the annotation
    assert model_fields(Overridden) == {"plain": str}


def test_model_fields_keep_the_metadata_pydantic_split_off():
    shape = classify(model_fields(Tree)["plain"])
    assert shape.kind is Kind.ANNOTATED
    assert shape.args == (int,)


def test_self_referencing_model_is_resolved():
    branches = classify(Tree).fields()["branches"]
    shape = classify(branches)
    assert shape.kind is Kind.SEQUENCE
    assert shape.child(shape.args[0]).origin is Tree


def test_fields_of_other_kinds_is_an_error():
    with pytest.raises(TypeError):
        classify(int).fields()
