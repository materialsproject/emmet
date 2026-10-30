"""Shape-level introspection of type annotations.

`classify` looks at a single annotation and reports what *kind* of type it is
(sequence, mapping, union, model, ...) and what its immediate components are,
without recursing. Consumers decide what to do with each kind and recurse
themselves via `TypeShape.child`, which keeps track of the namespace needed to
resolve forward references.

This is the one place where emmet knows how to take apart the annotations
used across its models (`Optional`, `NotRequired`, `TypeVar`s, `TypedDict`s,
pydantic models with `type_overrides`, MSONable type adapters, ...). It is
shared by:

- `emmet.core.arrow.arrowize`, which folds a type into a pyarrow schema
- `emmet.core.types.id_paths.find_identifier_paths`, which collects the
  location of identifier fields in a document

This module must not import pyarrow, as it is used where pyarrow is not
installed.
"""

from __future__ import annotations

import sys
import typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import UnionType
from typing import Annotated, Any, ForwardRef, TypeVar, Union

from monty.json import MSONable
from pydantic import BaseModel


class Kind(Enum):
    """The kind of a type, see `classify`."""

    ANY = auto()
    """`typing.Any`"""
    SEQUENCE = auto()
    """Homogeneous container: `list[X]`, `set[X]`, `tuple[X, ...]`, ...
    `args = (X,)`, or `()` if unparametrized."""
    TUPLE = auto()
    """Fixed length tuple `tuple[X, Y, ...]`. `args` are the positional types."""
    MAPPING = auto()
    """`dict[K, V]`, `Mapping[K, V]`. `args = (K, V)`, or `()` if unparametrized."""
    LITERAL = auto()
    """`Literal[...]`. `args` are the literal values."""
    UNION = auto()
    """`X | Y`, `Optional[X]`. `args` are the members, *without* `None`."""
    ANNOTATED = auto()
    """`Annotated[X, ...]`. `args = (X,)`, `metadata` holds the annotations."""
    ENUM = auto()
    """An `Enum` subclass."""
    MODEL = auto()
    """A pydantic model. See `TypeShape.fields`."""
    TYPEDDICT = auto()
    """A `TypedDict`. See `TypeShape.fields`."""
    MSONABLE = auto()
    """An `MSONable` class. `args = (X,)` where `X` is the annotation of its
    type adapter, or `()` if it has none."""
    CLASS = auto()
    """Any other class, e.g. `int`, `str`, `Path`. `origin` is the class."""
    OTHER = auto()
    """Anything not recognized."""


@dataclass(frozen=True)
class TypeShape:
    """The shape of one annotation, see `classify`.

    Attributes:
        kind: What kind of type this is.
        tp: The annotation as classified. Wrappers which carry no information
            on their own (`NotRequired`, `TypeVar`, forward references) have
            been resolved.
        args: The immediate component types, see `Kind`.
        metadata: `Annotated` metadata (only for `Kind.ANNOTATED`).
        origin: The class itself (for `ENUM`, `MODEL`, `TYPEDDICT`, `MSONABLE`
            and `CLASS`).
        namespace: Namespace in which forward references found in the
            components of this type are resolved.
    """

    kind: Kind
    tp: Any
    args: tuple[Any, ...] = ()
    metadata: tuple[Any, ...] = ()
    origin: Any = None
    namespace: Mapping[str, Any] = field(
        default_factory=dict, repr=False, compare=False
    )

    def child(self, tp: Any) -> TypeShape:
        """Classify a component of this type, e.g. one of `args`."""
        return classify(tp, self.namespace)

    def fields(
        self, *, include_excluded: bool = False, include_aliases: bool = False
    ) -> dict[str, Any]:
        """Annotations of the fields of a `MODEL` or `TYPEDDICT`.

        For models, `type_overrides` (see `emmet.core.utils.type_override`)
        replace the annotation of a field, and metadata which pydantic split off
        a field's annotation is re-attached with `Annotated`.

        Args:
            include_excluded: Include fields with `Field(exclude=True)`. These
                are left out of serialized models, but may be present in
                documents obtained from elsewhere, e.g. a database.
            include_aliases: Also list fields of models under their alias,
                with the same annotation. Documents may hold either name.
        """
        if self.kind is Kind.MODEL:
            return model_fields(
                self.origin,
                include_excluded=include_excluded,
                include_aliases=include_aliases,
            )
        if self.kind is Kind.TYPEDDICT:
            return typeddict_fields(self.origin)
        raise TypeError(f"{self.kind} has no fields")


def _module_namespace(cls: type) -> dict[str, Any]:
    module = sys.modules.get(getattr(cls, "__module__", None) or "")
    return dict(vars(module)) if module is not None else {}


def resolve_forward_ref(
    ref: ForwardRef | str, namespace: Mapping[str, Any] | None = None
) -> Any:
    """Evaluate a forward reference.

    The reference is evaluated in the module it was declared in, if it knows it,
    and otherwise in `namespace`. Names in `namespace` must therefore come from the
    module of the class which holds the annotation.

    Raises:
        NameError: if the reference can not be resolved.
    """
    if isinstance(ref, str):
        ref = ForwardRef(ref)

    globalns: dict[str, Any] = dict(namespace or {})
    module = getattr(ref, "__forward_module__", None)
    if module is not None and module in sys.modules:
        globalns = dict(vars(sys.modules[module]))

    try:
        return eval(ref.__forward_arg__, globalns, {})  # noqa: S307
    except NameError as exc:
        raise NameError(
            f"Could not resolve forward reference {ref.__forward_arg__!r}: {exc}"
        ) from exc


def model_fields(
    model: type[BaseModel],
    *,
    include_excluded: bool = False,
    include_aliases: bool = False,
) -> dict[str, Any]:
    """Field annotations of a pydantic model, see `TypeShape.fields`."""
    overrides = getattr(model, "type_overrides", {})
    out: dict[str, Any] = {}
    for name, info in model.model_fields.items():
        if info.exclude and not include_excluded:
            continue
        if name in overrides:
            out[name] = overrides[name]
        elif info.metadata:
            # pydantic splits the metadata of a field's top level `Annotated`
            # off its annotation, put it back
            out[name] = Annotated[(info.annotation, *info.metadata)]  # type: ignore[assignment]
        else:
            out[name] = info.annotation

        if include_aliases and isinstance(info.alias, str) and info.alias != name:
            out[info.alias] = out[name]
    return out


def typeddict_fields(typed_dict: type) -> dict[str, Any]:
    """Field annotations of a `TypedDict`, with forward references resolved."""
    try:
        return typing.get_type_hints(typed_dict, include_extras=True)
    except (NameError, TypeError):
        # e.g. names only imported when type checking
        return dict(typed_dict.__annotations__)


def _is_typeddict(tp: Any) -> bool:
    # Duck-typed so TypedDicts from third-party code still built with
    # typing_extensions (which uses its own metaclass on python < 3.13) also match
    return typing.is_typeddict(tp) or (
        isinstance(tp, type)
        and issubclass(tp, dict)
        and hasattr(tp, "__required_keys__")
        and hasattr(tp, "__optional_keys__")
    )


_TYPE_WRAPPERS = tuple(
    wrapper
    for name in ("NotRequired", "Required", "ReadOnly")
    if (wrapper := getattr(typing, name, None)) is not None
)


def classify(tp: Any, namespace: Mapping[str, Any] | None = None) -> TypeShape:
    """Say what kind of type an annotation is, and what it is made of.

    Args:
        tp: The annotation.
        namespace: Namespace to resolve forward references in, if `tp` or its
            components contain any. Use `TypeShape.child` to classify the
            components of a type, which takes care of this.

    Returns:
        The shape of `tp`. `NotRequired`, `Required`, `ReadOnly`, forward
        references, and `TypeVar`s are resolved to what they wrap: for the
        latter that is its second constraint, which for the type variables in
        `emmet.core.types.pymatgen_types` is the `TypedDict` describing the
        serialized form of the object.
    """
    ns: Mapping[str, Any] = namespace or {}

    if isinstance(tp, str | ForwardRef):
        return classify(resolve_forward_ref(tp, ns), ns)

    if tp is typing.Any:
        return TypeShape(Kind.ANY, tp, namespace=ns)

    origin = typing.get_origin(tp)
    args = typing.get_args(tp)

    if origin in _TYPE_WRAPPERS:
        return classify(args[0], ns)

    if origin is Annotated:
        return TypeShape(
            Kind.ANNOTATED, tp, args=(args[0],), metadata=tuple(args[1:]), namespace=ns
        )

    if origin is Union or origin is UnionType:
        members = tuple(arg for arg in args if arg is not type(None))
        return TypeShape(Kind.UNION, tp, args=members, namespace=ns)

    if origin is typing.Literal:
        return TypeShape(Kind.LITERAL, tp, args=args, namespace=ns)

    if isinstance(origin, type):
        if issubclass(origin, Mapping):
            return TypeShape(Kind.MAPPING, tp, args=args, namespace=ns)
        if issubclass(origin, tuple) and not (len(args) == 2 and args[1] is Ellipsis):
            return TypeShape(Kind.TUPLE, tp, args=args, namespace=ns)
        if issubclass(origin, tuple):
            return TypeShape(Kind.SEQUENCE, tp, args=args[:1], namespace=ns)
        if issubclass(origin, Iterable) and not issubclass(origin, str | bytes):
            return TypeShape(Kind.SEQUENCE, tp, args=args, namespace=ns)

    if isinstance(tp, TypeVar):
        if len(tp.__constraints__) > 1:
            return classify(tp.__constraints__[1], ns)
        if tp.__constraints__:
            return classify(tp.__constraints__[0], ns)
        if tp.__bound__ is not None:
            return classify(tp.__bound__, ns)
        return TypeShape(Kind.ANY, tp, namespace=ns)

    if isinstance(tp, type):
        own_ns = _module_namespace(tp)
        if issubclass(tp, Enum):
            return TypeShape(Kind.ENUM, tp, origin=tp, namespace=ns)
        if issubclass(tp, BaseModel):
            return TypeShape(Kind.MODEL, tp, origin=tp, namespace=own_ns)
        if _is_typeddict(tp):
            return TypeShape(Kind.TYPEDDICT, tp, origin=tp, namespace=own_ns)
        if issubclass(tp, MSONable):
            adapter = getattr(tp, "__type_adapter__", None)
            adapter_args = (adapter.model_fields["root"].annotation,) if adapter else ()
            return TypeShape(
                Kind.MSONABLE, tp, args=adapter_args, origin=tp, namespace=own_ns
            )
        return TypeShape(Kind.CLASS, tp, origin=tp, namespace=ns)

    return TypeShape(Kind.OTHER, tp, namespace=ns)
