"""Locate the identifier fields of a document model.

Models annotate fields holding MP identifiers with `IdentifierType`,
`MaterialIdentifierType` or `TaskIdentifierType` (see
`emmet.core.types.typing`). `find_identifier_paths` walks a model and reports
where, at any depth, such fields are found, and how to display them.

A *path* is a tuple of segments describing how to reach identifiers from a
document (a plain `dict`, as obtained from a database or `model_dump()`):

- `str`: the value of this key of a dict. Lists met on the way are traversed
  transparently, i.e. the rest of the path applies to each of their elements.
- `int`: this position of a list or tuple.
- `VALUES`: every value of a dict, for `dict[str, <identifier>]`-like fields.
- `KEYS`: every key of a dict, for `dict[<identifier>, ...]`-like fields.
  Can only be the last segment, since keys cannot be navigated further.

`apply_to_path` carries out a path on a document.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from emmet.core.types.introspection import Kind, TypeShape, classify
from emmet.core.types.typing import IdDisplayFormat

if TYPE_CHECKING:
    from pydantic import BaseModel


class _Segment:
    """Marker for a path segment which is not a field name."""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return self.name

    def __reduce__(self):
        return self.name


VALUES = _Segment("VALUES")
"""Path segment: every value of a dict."""

KEYS = _Segment("KEYS")
"""Path segment: every key of a dict. Last segment only."""

IdPath = tuple[str | int | _Segment, ...]
IdFormatter = Callable[..., Any]
"""`formatter(value, legacy=<bool>)`, see `IdDisplayFormat`."""

_DOTTED_SEGMENTS = {"*": VALUES, "*key": KEYS}


def parse_id_path(path: str | IdPath) -> IdPath:
    """Convert a dotted path to a tuple path.

    `"adj_pairs.id_charge"`, `"phonon_IDs.*"` (dict values), `"calc_types.*key"`
    (dict keys). All-digit segments are list positions.
    """
    if not isinstance(path, str):
        return tuple(path)

    parts: list[str | int | _Segment] = []
    for seg in path.split("."):
        if seg in _DOTTED_SEGMENTS:
            parts.append(_DOTTED_SEGMENTS[seg])
        elif seg.isdigit():
            parts.append(int(seg))
        else:
            parts.append(seg)
    return tuple(parts)


def _marker_of(shape: TypeShape) -> IdDisplayFormat | None:
    """Find the identifier marker of a type which is directly an identifier."""
    match shape.kind:
        case Kind.ANNOTATED:
            for meta in shape.metadata:
                if isinstance(meta, IdDisplayFormat):
                    return meta
            return _marker_of(shape.child(shape.args[0]))
        case Kind.UNION:
            for arg in shape.args:
                if marker := _marker_of(shape.child(arg)):
                    return marker
    return None


def find_identifier_paths(model: type[BaseModel]) -> dict[IdPath, IdFormatter]:
    """Find every identifier-typed field of a pydantic model, at any depth.

    Optional / union types, lists, tuples, dicts (both keys and values), nested
    models, `TypedDict`s, constrained type variables and MSONable type adapters
    are searched. Fields excluded from serialization are searched too, and
    fields with an alias are reported under both names, as the documents of
    interest may come from a database.

    Models which contain themselves, directly or not, are searched once: a path
    cannot describe unbounded depth.

    Args:
        model: The pydantic model describing a document.

    Returns:
        Mapping of path (see the module docstring) -> formatter.
    """
    found: dict[IdPath, IdFormatter] = {}

    def walk(shape: TypeShape, path: IdPath, stack: tuple[Any, ...]) -> None:
        match shape.kind:
            case Kind.ANNOTATED:
                for meta in shape.metadata:
                    if isinstance(meta, IdDisplayFormat):
                        found.setdefault(path, meta.formatter)
                        return
                walk(shape.child(shape.args[0]), path, stack)
            case Kind.MSONABLE | Kind.SEQUENCE:
                for arg in shape.args[:1]:
                    walk(shape.child(arg), path, stack)
            case Kind.UNION:
                for arg in shape.args:
                    walk(shape.child(arg), path, stack)
            case Kind.TUPLE:
                for idx, arg in enumerate(shape.args):
                    walk(shape.child(arg), (*path, idx), stack)
            case Kind.MAPPING:
                if len(shape.args) == 2:
                    key, value = (shape.child(arg) for arg in shape.args)
                    if marker := _marker_of(key):
                        found.setdefault((*path, KEYS), marker.formatter)
                    walk(value, (*path, VALUES), stack)
            case Kind.MODEL | Kind.TYPEDDICT:
                if shape.origin in stack:
                    return
                fields = shape.fields(include_excluded=True, include_aliases=True)
                for name, annotation in fields.items():
                    walk(
                        shape.child(annotation),
                        (*path, name),
                        (*stack, shape.origin),
                    )

    walk(classify(model), (), ())
    return found


def apply_to_path(
    node: Any, path: IdPath, formatter: IdFormatter, *, legacy: bool
) -> None:
    """Reformat in place the identifiers found at `path` below `node`.

    Parts of the document which do not match the path (e.g. fields dropped by
    a projection, `None`s, unexpected shapes) are left untouched.
    """
    seg, rest = path[0], path[1:]

    if isinstance(node, list) and not isinstance(seg, int):
        for item in node:
            apply_to_path(item, path, formatter, legacy=legacy)
        return

    if isinstance(node, dict):
        if seg is KEYS:
            # Rebuild, so that the order of the keys is preserved
            items = [(_format(k, formatter, legacy), v) for k, v in node.items()]
            node.clear()
            node.update(items)
            return
        keys = list(node) if seg is VALUES else [seg] if seg in node else []
    elif (
        isinstance(node, list | tuple)
        and isinstance(seg, int)
        and -len(node) <= seg < len(node)
    ):
        keys = [seg]
    else:
        return

    for key in keys:
        if rest:
            apply_to_path(node[key], rest, formatter, legacy=legacy)
        else:
            try:
                node[key] = _format(node[key], formatter, legacy)
            except TypeError:  # tuples are immutable
                return


def _format(value: Any, formatter: IdFormatter, legacy: bool) -> Any:
    if isinstance(value, list):
        return [_format(v, formatter, legacy) for v in value]
    return formatter(value, legacy=legacy) if value else value
