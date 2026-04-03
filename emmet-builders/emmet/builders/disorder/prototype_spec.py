"""Prototype structure specification and primitive cell builders.

Vendored from phaseedge.science.prototype_spec with imports adjusted.
"""

import dataclasses
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

import numpy as np
from ase.atoms import Atoms
from ase.spacegroup import crystal


class PrototypeStructure(str, Enum):
    ROCKSALT = "rocksalt"
    GARNET = "garnet"
    SPINEL = "spinel"
    DOUBLE_PEROVSKITE = "doubleperovskite"
    PYROCHLORE = "pyrochlore"
    ILMENITE = "ilmenite"


_SEGMENT_RE = re.compile(
    r"^(?P<prefix>[A-Z])(?P<index>\d+)(?P<element>[A-Z][a-z]{0,2})$"
)


def _annotate_atoms_with_metadata(
    atoms: Atoms,
    metadata_by_symbol: dict[str, dict[str, Any]],
) -> None:
    """Attach per-site metadata arrays to an ASE Atoms object based on its symbols."""
    symbols = atoms.get_chemical_symbols()

    keys: set[str] = set()
    for meta in metadata_by_symbol.values():
        keys.update(meta.keys())

    for key in sorted(keys):
        vals: list[Any] = []
        for sym in symbols:
            meta = metadata_by_symbol.get(sym)
            vals.append(meta.get(key) if meta is not None else None)
        atoms.set_array(key, np.array(vals, dtype=object))


def parse_prototype(
    prototype: str,
    *,
    allowed_prefixes: Iterable[str] = ("J", "Q"),
) -> tuple[PrototypeStructure, dict[str, str]]:
    """Parse prototypes like 'doubleperovskite_J0Sr_Q0O' into
    ``(PrototypeStructure.DOUBLE_PEROVSKITE, {'J0': 'Sr', 'Q0': 'O'})``.
    """
    if not prototype:
        raise ValueError("Invalid prototype: empty string.")

    tokens = prototype.split("_")
    structure_token = tokens[0]

    structure_map: dict[str, PrototypeStructure] = {e.value: e for e in PrototypeStructure}
    try:
        structure = structure_map[structure_token]
    except KeyError as exc:
        valid = ", ".join(sorted(structure_map))
        raise ValueError(
            f"Unknown prototype structure '{structure_token}'. Valid values: {valid}."
        ) from exc

    prefixes = set(allowed_prefixes)
    spec: dict[str, str] = {}
    seen_keys: set[str] = set()

    for seg in tokens[1:]:
        m = _SEGMENT_RE.match(seg)
        if not m:
            raise ValueError(
                f"Bad segment '{seg}'. Expected <PREFIX><INDEX><ELEMENT>, e.g. J0Sr or Q12O."
            )

        prefix = m.group("prefix")
        if prefix not in prefixes:
            allowed_str = ", ".join(sorted(prefixes))
            raise ValueError(
                f"Disallowed prefix '{prefix}' in segment '{seg}'. Allowed: {allowed_str}."
            )

        index = m.group("index")
        element = m.group("element")
        key = f"{prefix}{index}"

        if key in seen_keys:
            raise ValueError(f"Duplicate key '{key}' encountered.")

        spec[key] = element
        seen_keys.add(key)

    return structure, spec


def _require_exact_keys(spec: dict[str, str], required: set[str]) -> None:
    """Ensure spec has exactly the required keys."""
    present = set(spec.keys())
    missing = required - present
    extra = present - required

    if missing:
        raise ValueError(f"Missing required tag(s): {sorted(missing)}")
    if extra:
        raise ValueError(
            f"Unexpected tag(s): {sorted(extra)}; expected exactly {sorted(required)}"
        )


def _pop_float(local_params: dict[str, float], key: str) -> float:
    """Pop a required numeric param from local_params."""
    try:
        raw_val = local_params.pop(key)
    except KeyError as exc:
        raise ValueError(f"Missing required numeric param '{key}'.") from exc

    try:
        val = float(raw_val)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Param '{key}' must be castable to float, got {raw_val!r}."
        ) from exc

    return val


def _build_primitive_cell(
    structure: PrototypeStructure,
    spec: dict[str, str],
    params: dict[str, float],
) -> tuple[Atoms, set[str]]:
    """Build the primitive ASE cell and determine active sublattices.

    Returns:
        (primitive_cell, active_sublattices)
    """
    local_params: dict[str, float] = dict(params)

    if structure is PrototypeStructure.ROCKSALT:
        _require_exact_keys(spec, {"Q0"})
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        primitive_cell = crystal(
            symbols=["Es", anion],
            basis=[(0, 0, 0), (0, 0, 1 / 2)],
            spacegroup=225,
            cellpar=[a, a, a, 90, 90, 90],
            primitive_cell=False,
        )
        active_sublattices = {"Es"}

        symbol_metadata: dict[str, dict[str, str]] = {
            "Es": {"sublattice": "A", "wyckoff": "4a", "role": "active_cation"},
            anion: {"sublattice": "X", "wyckoff": "4b", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

    elif structure is PrototypeStructure.GARNET:
        _require_exact_keys(spec, {"J0", "Q0"})
        inactive_cation = spec["J0"]
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        primitive_cell = crystal(
            symbols=["Es", "Fm", inactive_cation, anion],
            basis=[
                (0, 1 / 2, 0),
                (3 / 4, 1 / 8, 0),
                (1 / 4, 3 / 8, 1 / 2),
                (0.350086, 0.472582, 0.055588),
            ],
            spacegroup=230,
            cellpar=[a, a, a, 90, 90, 90],
            primitive_cell=True,
        )
        active_sublattices = {"Es", "Fm"}

        symbol_metadata = {
            "Es": {"sublattice": "B", "wyckoff": "16a", "role": "active_cation"},
            "Fm": {"sublattice": "C", "wyckoff": "24d", "role": "active_cation"},
            inactive_cation: {"sublattice": "A", "wyckoff": "24c", "role": "inactive_cation"},
            anion: {"sublattice": "X", "wyckoff": "96h", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

    elif structure is PrototypeStructure.SPINEL:
        _require_exact_keys(spec, {"Q0"})
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        u = float(local_params.pop("u", 0.36))

        primitive_cell = crystal(
            symbols=["Es", "Fm", anion],
            basis=[
                (1 / 4, 3 / 4, 3 / 4),
                (5 / 8, 3 / 8, 3 / 8),
                (1 / 2 + u, u, u),
            ],
            spacegroup=227,
            cellpar=[a, a, a, 90, 90, 90],
            primitive_cell=True,
        )
        active_sublattices = {"Es", "Fm"}

        symbol_metadata = {
            "Es": {"sublattice": "A", "wyckoff": "8a", "role": "active_cation"},
            "Fm": {"sublattice": "B", "wyckoff": "16d", "role": "active_cation"},
            anion: {"sublattice": "X", "wyckoff": "32e", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

    elif structure is PrototypeStructure.DOUBLE_PEROVSKITE:
        _require_exact_keys(spec, {"J0", "Q0"})
        inactive_cation = spec["J0"]
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        u = float(local_params.pop("u", 0.26))

        primitive_cell = crystal(
            symbols=["Es", "Fm", inactive_cation, anion],
            basis=[
                (0, 0, 0),
                (0, 0, 1 / 2),
                (1 / 4, 3 / 4, 3 / 4),
                (u, 0, 0),
            ],
            spacegroup=225,
            cellpar=[a, a, a, 90, 90, 90],
            primitive_cell=True,
        )
        active_sublattices = {"Es", "Fm"}

        symbol_metadata = {
            "Es": {"sublattice": "B_prime", "wyckoff": "4a", "role": "active_cation"},
            "Fm": {"sublattice": "B_double_prime", "wyckoff": "4b", "role": "active_cation"},
            inactive_cation: {"sublattice": "A", "wyckoff": "8c", "role": "inactive_cation"},
            anion: {"sublattice": "X", "wyckoff": "24e", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

    elif structure is PrototypeStructure.PYROCHLORE:
        _require_exact_keys(spec, {"Q0"})
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        x = _pop_float(local_params, "x")
        if not (0 < x < 1):
            raise ValueError(f"Param 'x' must be in (0, 1), got {x}.")

        primitive_cell = crystal(
            symbols=["Es", "Fm", "Md", "No"],
            basis=[
                (3 / 8, 7 / 8, 1 / 8),
                (7 / 8, 7 / 8, 1 / 8),
                (1 / 4, 3 / 4, 1 / 4),
                (1 / 4, x, 1 / 4),
            ],
            spacegroup=227,
            cellpar=[a, a, a, 90, 90, 90],
            primitive_cell=False,
        )
        active_sublattices = {"Es", "Fm"}

        symbol_metadata = {
            "Es": {"sublattice": "A", "wyckoff": "16d", "role": "active_cation"},
            "Fm": {"sublattice": "B", "wyckoff": "16c", "role": "active_cation"},
            "Md": {"sublattice": "X", "wyckoff": "8b", "role": "anion"},
            "No": {"sublattice": "X", "wyckoff": "48f", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

        # Collapse Md/No back to the actual anion species
        symbols = primitive_cell.get_chemical_symbols()
        new_symbols: list[str] = []
        for s in symbols:
            if s in ("Md", "No"):
                new_symbols.append(anion)
            else:
                new_symbols.append(s)
        primitive_cell.set_chemical_symbols(new_symbols)

    elif structure is PrototypeStructure.ILMENITE:
        _require_exact_keys(spec, {"Q0"})
        anion = spec["Q0"]

        a = _pop_float(local_params, "a")
        if a <= 0:
            raise ValueError(f"Param 'a' must be > 0, got {a}.")

        c = _pop_float(local_params, "c")
        if c <= 0:
            raise ValueError(f"Param 'c' must be > 0, got {c}.")

        primitive_cell = crystal(
            symbols=["Es", "Fm", anion],
            basis=[
                (1 / 3, 2 / 3, 0.311558),
                (2 / 3, 1 / 3, 0.188669),
                (0.315034, 0.294888, 0.246799),
            ],
            spacegroup=148,
            cellpar=[a, a, c, 90, 90, 120],
            primitive_cell=True,
        )
        active_sublattices = {"Es", "Fm"}

        symbol_metadata = {
            "Es": {"sublattice": "A", "wyckoff": "6c", "role": "active_cation"},
            "Fm": {"sublattice": "B", "wyckoff": "6c", "role": "active_cation"},
            anion: {"sublattice": "X", "wyckoff": "18f", "role": "anion"},
        }
        _annotate_atoms_with_metadata(primitive_cell, symbol_metadata)

    else:
        raise ValueError(f"Unknown prototype structure: {structure}")

    if local_params:
        raise ValueError(
            f"Unexpected extra params for prototype {structure.value}: {sorted(local_params.keys())}"
        )

    return primitive_cell, active_sublattices


@dataclass(frozen=True, slots=True)
class PrototypeSpec:
    """Immutable description of a prototype structure.

    Fields:
        prototype: e.g. "spinel_Q0O" or "doubleperovskite_J0Sr_Q0O"
        params:    dict of geometry parameters, e.g. {"a": 8.2, "u": 0.36}
    """

    _: dataclasses.KW_ONLY
    prototype: str
    params: dict[str, float]

    def __post_init__(self) -> None:
        # Validation is delegated to _build_primitive_cell.
        structure, spec = parse_prototype(self.prototype)
        _build_primitive_cell(structure, spec, self.params)

    @property
    def primitive_cell(self) -> Atoms:
        """Build and return the primitive cell (ASE Atoms)."""
        structure, spec = parse_prototype(self.prototype)
        primitive_cell, _ = _build_primitive_cell(structure, spec, self.params)
        return primitive_cell

    @property
    def active_sublattices(self) -> set[str]:
        """Return which placeholder species are active cation sublattices."""
        structure, spec = parse_prototype(self.prototype)
        _, active = _build_primitive_cell(structure, spec, self.params)
        return active

    @property
    def active_sublattice_counts(self) -> dict[str, int]:
        """Count sites for each active sublattice in the primitive cell."""
        chem_syms: list[str] = list(self.primitive_cell.get_chemical_symbols())
        return {sub: chem_syms.count(sub) for sub in self.active_sublattices}
