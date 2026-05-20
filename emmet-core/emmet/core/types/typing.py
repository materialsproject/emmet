"""Define custom type annotations for emmet-core.

Note that only type annotations which are used across
the code base should be put here.

Types which only have one purpose / exist only within
one module, can and should remain in that module.
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Union, overload
from typing_extensions import TypedDict

import orjson
from pydantic import BeforeValidator, Field, PlainSerializer, WrapSerializer

from emmet.core.mpid import MPID, AlphaID
from emmet.core.utils import convert_datetime, utcnow

if TYPE_CHECKING:
    from typing import Literal

    from typing_extensions import TypeAlias

FSPathType: TypeAlias = Annotated[
    Union[str | Path | os.DirEntry[str] | os.PathLike[str]],
    PlainSerializer(lambda x: str(x), return_type=str),
]
"""Type of a generic path-like object"""


DateTimeType: TypeAlias = Annotated[
    datetime,
    Field(default_factory=utcnow),
    BeforeValidator(convert_datetime),
]
"""Datetime serde."""

NullableDateTimeType: TypeAlias = Annotated[
    datetime | None,
    Field(default_factory=utcnow),
    BeforeValidator(convert_datetime),
]
"""Nullable datetime serde.

See: https://docs.pydantic.dev/latest/concepts/fields/#the-annotated-pattern
for why this separate class is necesary instead of `DateTimeType | None`
"""


def _fault_tolerant_id_serde(
    val: Any,
    legacy: bool = False,
    serialize: bool = False,
    **kwargs,
) -> Any:
    """Needed for the API and safe de-/serialization behavior."""
    try:
        alpha_id = AlphaID(val, **kwargs)
        if serialize:
            return str(alpha_id)
        return alpha_id.formatted if legacy else alpha_id
    except Exception:
        return val


_id_base_metadata = (BeforeValidator(_fault_tolerant_id_serde),)


ID_PADLEN: int = 8
ID_PREFIX: str = "mp"


def format_identifier(
    idx: Any,
    legacy: bool,
    prefix: str | None = ID_PREFIX,
    padlen: int = ID_PADLEN,
) -> str:
    """Render an MP identifier as either the legacy `mp-<int>` form or the padded AlphaID form.

    This is the canonical display-formatting helper for MP identifiers. Use it
    anywhere you need to switch a `material_id`, plain prefix-number id, or
    AlphaID-form id between the two human-readable representations.

    Args:
        idx: An MPID, AlphaID, or string that parses as either. May be passed
            in any form (legacy `mp-149`, unpadded alpha `mp-ft`, padded alpha
            `mp-aaaaaaft`, bare int `149`, etc.); the function normalizes.
        legacy: If True, returns the legacy form (e.g. "mp-149") for identifiers
            below the AlphaID cutoff. Above the cutoff there is no legacy form,
            so the alpha form is returned instead.
            If False, returns the AlphaID form padded to `padlen` characters
            (e.g. "mp-aaaaaaft" for value 149 with the default padlen=8).
        prefix: The id prefix to apply on the alpha-form output. Defaults to
            "mp"; pass None to omit the prefix entirely.
        padlen: The minimum identifier length on the alpha-form output (the
            identifier is left-padded with the alphabet's first letter to reach
            this length). Defaults to 8.

    Returns:
        The formatted string. If `idx` is None or empty, it is returned
        unchanged. If `idx` cannot be parsed as an AlphaID, it is coerced to
        a string and returned unchanged (defensive: never raises from a
        display helper).

    Examples:
        >>> format_identifier("mp-149", legacy=True)
        'mp-149'
        >>> format_identifier("mp-149", legacy=False)
        'mp-aaaaaaft'
        >>> format_identifier("mp-aaaaaaft", legacy=True)
        'mp-149'
    """
    # Guard against None and the empty string. The ``str``-instance check
    # avoids triggering ``MPID.__eq__`` (which raises ValueError on
    # ``MPID(...) == ""``) when ``idx`` is an MPID/AlphaID subclass instance
    # rather than a plain string.
    if idx is None:
        return idx
    if isinstance(idx, str) and not idx:
        return idx
    try:
        alpha = AlphaID(idx)
    except (ValueError, TypeError):
        return str(idx)
    if legacy:
        return alpha.string
    # Re-instantiate with the requested display pad length, preserving the
    # separator from the parsed instance (defaulting to "-" if absent).
    return str(
        AlphaID(
            int(alpha),
            padlen=padlen,
            prefix=prefix,
            separator=alpha._separator or "-",
        )
    )


# Separators used by composite MP identifiers
# ("mp-2658_Al" for battery ids, "mp-67-XANES-O-K" for XAS spectrum ids).
# The first segment is the canonical MPID/AlphaID; any trailing segments
# are preserved verbatim during reformatting.
_COMPOSITE_ID_SEPARATORS: tuple[str, ...] = ("_", "-")


def _split_composite_identifier(
    value: str,
    separators: tuple[str, ...] = _COMPOSITE_ID_SEPARATORS,
) -> tuple[str, str]:
    """Split a composite MP identifier into ``(base_id, suffix)``.

    The base_id is the longest leading substring that parses as a valid MP
    identifier via ``AlphaID``; the suffix is everything from the splitting
    separator onward (separator included). If no valid split exists, returns
    ``(value, "")`` so callers can pass the value through unchanged.

    Examples:
        >>> _split_composite_identifier("mp-149")
        ('mp-149', '')
        >>> _split_composite_identifier("mp-2658_Al")
        ('mp-2658', '_Al')
    """
    from emmet.core.mpid import validate_identifier

    if not isinstance(value, str) or not value:
        return value, ""

    # If the whole thing parses, no split is needed.
    try:
        validate_identifier(value)
        return value, ""
    except ValueError:
        pass

    # Walk separators from the end of the string; the longest leading prefix
    # that validates is the base id.
    for i in range(len(value) - 1, 0, -1):
        if value[i] in separators:
            candidate = value[:i]
            try:
                validate_identifier(candidate)
                return candidate, value[i:]
            except ValueError:
                continue

    return value, ""


def format_compound_identifier(
    idx: Any,
    legacy: bool,
    prefix: str | None = ID_PREFIX,
    padlen: int = ID_PADLEN,
) -> str:
    """Render a composite MP identifier in the requested format, preserving the suffix.

    Composite identifiers include battery ids
    (`mp-2658_Al`) and XAS spectrum ids (`mp-67-XANES-O-K`). The leading
    MP identifier portion is reformatted via `format_identifier`; the
    trailing suffix (working ion, task index, XAS components, etc.) is
    preserved verbatim. Plain (non-composite) MP identifiers pass through
    to `format_identifier`.

    This is the fault-tolerant, suffix-agnostic counterpart of
    `validate_compound_identifier`, which performs strict, typed validation
    against a known suffix tuple. Use *this* function when you need to
    reformat an id for display and don't know (or don't care to verify) the
    specific suffix shape.

    Args:
        idx: The composite identifier string.
        legacy: If True, the leading id is rendered in legacy form;
            otherwise in padded AlphaID form. See `format_identifier`.
        prefix: Forwarded to `format_identifier` for the alpha-form path.
        padlen: Forwarded to `format_identifier` for the alpha-form path.

    Returns:
        The formatted string. Returns the input unchanged if `idx` is None,
        empty, or cannot be parsed.

    Examples:
        >>> format_compound_identifier("mp-2658_Al", legacy=False)
        'mp-aaaaadyg_Al'
    """
    # See ``format_identifier`` for the rationale behind this two-step guard.
    if idx is None:
        return idx
    if isinstance(idx, str) and not idx:
        return idx
    base, suffix = _split_composite_identifier(str(idx))
    if not suffix:
        return format_identifier(base, legacy, prefix=prefix, padlen=padlen)
    return f"{format_identifier(base, legacy, prefix=prefix, padlen=padlen)}{suffix}"


def format_task_id(
    task_id: Any,
    legacy: bool,
    prefix: str = ID_PREFIX,
    padlen: int = ID_PADLEN,
) -> str:
    """Render a calculation task id in either legacy or new alpha form.

    Task ids have a different shape convention than other MP identifiers:

    - Legacy form: ``mp-<int>`` (prefixed, same shape as a plain mpid, e.g.
      ``mp-149``).
    - New alpha form: bare padded alpha string with **no** prefix and no
      suffix (e.g. ``aaaaaaft``).

    This is unlike `material_id` (prefix preserved in both modes) and
    `battery_id` (composite with a working-ion suffix). The general-purpose
    :func:`format_identifier` / :func:`format_compound_identifier` helpers
    do not capture this prefix-dropping rule, so task ids are rendered
    through this dedicated helper instead.

    Args:
        task_id: A task id in either form, or any value coercible to an
            :class:`AlphaID`. May be a bare int, a prefixed string, or an
            :class:`AlphaID` object.
        legacy: If True, returns the legacy form (e.g. ``mp-149``). If False,
            returns the bare padded alpha form (e.g. ``aaaaaaft``) with no
            prefix.
        prefix: The id prefix used in the legacy form. Defaults to ``"mp"``.
        padlen: The minimum identifier length on the alpha-form output.
            Defaults to 8.

    Returns:
        The formatted string. If ``task_id`` is None or empty, it is returned
        unchanged. If ``task_id`` cannot be parsed as an :class:`AlphaID`, it
        is coerced to a string and returned unchanged (defensive: this helper
        never raises from a display path).

    Examples:
        >>> format_task_id("mp-149", legacy=True)
        'mp-149'
        >>> format_task_id("mp-149", legacy=False)
        'aaaaaaft'
        >>> format_task_id("aaaaaaft", legacy=True)
        'mp-149'
    """
    # See ``format_identifier`` for the rationale behind this two-step guard.
    if task_id is None:
        return task_id
    if isinstance(task_id, str) and not task_id:
        return task_id
    try:
        value = int(AlphaID(task_id))
    except (ValueError, TypeError):
        return str(task_id)
    if legacy:
        return f"{prefix}-{value}"
    # Alpha display: bare padded identifier with no prefix.
    return str(AlphaID(value, padlen=padlen, prefix=None))


def _make_id_type(render_order, **kwargs) -> Any:
    _order: Any
    match render_order:
        case 0:
            _order = Union[AlphaID, MPID]
        case 1:
            _order = Union[MPID, AlphaID]
        case _:
            raise NotImplementedError(
                f"No implementation for render_order: {render_order}"
            )

    return Annotated[
        _order,
        BeforeValidator(partial(_fault_tolerant_id_serde, **kwargs)),
        PlainSerializer(partial(_fault_tolerant_id_serde, serialize=True, **kwargs)),
    ]


IdentifierType = _make_id_type(0, padlen=ID_PADLEN)
MaterialIdentifierType = _make_id_type(
    1, legacy=True, prefix=ID_PREFIX, padlen=ID_PADLEN
)
"""MPID / AlphaID serde."""


class CompoundIDType(TypedDict):
    """Define layout of compound identifiers for static type analysis."""

    identifier: AlphaID
    suffix: tuple[Enum]
    separator: str


@overload
def validate_compound_identifier(
    idx: str,
    suffixes: tuple[Enum],
    separator: str = "_",
    use_prefix: bool = False,
    as_components: Literal[False] = False,
) -> str: ...


@overload
def validate_compound_identifier(
    idx: str,
    suffixes: tuple[Enum],
    separator: str = "_",
    use_prefix: bool = False,
    as_components: Literal[True] = True,
) -> CompoundIDType: ...


def validate_compound_identifier(
    idx: str,
    suffixes: tuple[Enum],
    separator: str = "_",
    use_prefix: bool = False,
    as_components: bool = False,
) -> str | CompoundIDType:
    """Serde for compound identifier types.

    Examples:
    - Thermo: mp-149_GGA
    - Insertion electrodes: mp-75_Li
    - XAS: mp-67-XANES-O-K

    Args:
    idx (str) : The compound identifier
    suffixes (tuple of Enum) : Suffixes used in the identifier.
        Must be enums, ex.: ThermoType, RunType, pymatgen.core.periodic_table.Element
    separator (str) : Separator between distinct ID components.
    use_prefix (bool) : Whether to strip the prefix from the base ID component:
        use_prefix = True  --> mp-aaaaaaft-GGA
        use_prefix = False -->    aaaaaaft-GGA
    as_components (bool) : Whether to serialize to a str (True),
        or return as a dict of validated components.
    """

    for _split_method in ("split", "rsplit"):
        try:
            id_components = getattr(idx, _split_method)(separator, len(suffixes))
            base_id = AlphaID(
                int(AlphaID(id_components[0])),
                prefix=ID_PREFIX if use_prefix else None,
                padlen=ID_PADLEN,
            )
            validated_suffixes = [
                suffix(id_components[1 + idx]) for idx, suffix in enumerate(suffixes)  # type: ignore[operator]
            ]
            break
        except Exception:
            continue
    else:
        raise ValueError("Could not identify components of compound ID.")

    if as_components:
        return CompoundIDType(
            identifier=base_id,
            suffix=tuple(validated_suffixes),
            separator=separator,
        )

    return separator.join([str(base_id), *[sfx.value for sfx in validated_suffixes]])


def _ser_json_like(d, default_serializer, info):
    """Serialize a generic JSON-like object to a str for arrow, and a dict otherwise."""
    default_serialized_object = default_serializer(d, info)

    format = info.context.get("format") if info.context else None
    if format == "arrow" and default_serialized_object is not None:
        return orjson.dumps(default_serialized_object).decode()

    return default_serialized_object


def _deser_json_like(d):
    """Deserialize a generic JSON-like object from a str or object."""
    if hasattr(d, "as_dict"):
        d = d.as_dict()
    return orjson.loads(d) if isinstance(d, str | bytes) else d


JsonDictType = Annotated[
    dict[str, Any] | None,
    BeforeValidator(_deser_json_like),
    WrapSerializer(_ser_json_like),
]
"""Annotation for free-form JSON-like dict (INCAR-like, ddec6, etc.)"""

JsonListType = Annotated[
    list[Any] | None,
    BeforeValidator(_deser_json_like),
    WrapSerializer(_ser_json_like),
]
"""Annotation for free-form JSON-like list (some custodian metadata)"""


def _dict_items_zipper(
    dict_like: dict[str, Any] | list[tuple[str, Any]] | None,
) -> dict[str, Any] | None:
    """Zip output of dict(...).items() back into a dict."""
    if isinstance(dict_like, list):
        return {k: v for k, v in dict_like}
    return dict_like
