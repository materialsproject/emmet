"""Define utility functions used across the emmet namespace packages."""

from __future__ import annotations

import copy
import datetime
import hashlib
import inspect
import logging
from enum import Enum
from importlib import import_module
from itertools import groupby
from math import gcd
from typing import TYPE_CHECKING, get_args

import numpy as np
from monty.json import MontyDecoder, MSONable
from pydantic import BaseModel, RootModel
from pydantic._internal._utils import lenient_issubclass
from pymatgen.analysis.elasticity.strain import Deformation
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher
from pymatgen.analysis.structure_matcher import (
    AbstractComparator,
    ElementComparator,
    StructureMatcher,
)
from pymatgen.core.structure import Molecule, Structure
from pymatgen.transformations.standard_transformations import (
    DeformStructureTransformation,
)
from pymatgen.util.graph_hashing import weisfeiler_lehman_graph_hash
from typing_extensions import TypedDict

from emmet.core import ARROW_COMPATIBLE
from emmet.core.mpid import MPculeID
from emmet.core.settings import EmmetSettings

try:
    import blake3
except ImportError:
    blake3 = None  # type: ignore

try:
    import bson
except ImportError:
    bson = None  # type: ignore


if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import Any

    from emmet.core.types.typing import FSPathType

logger = logging.getLogger(__name__)

SETTINGS = EmmetSettings()


def type_override(overrides: dict[str, Any]):
    """
    Pydantic model decorator for declaring a field should be serialized
    as a type that does not match the type hint for the field. Examples:
    narrow a union type to a single value or hint at a the return type
    of a field_serializer used during model dumping.
    """

    def wrapped(cls):
        cls.type_overrides = {**getattr(cls, "type_overrides", {}), **overrides}
        return cls

    return wrapped


def set_msonable_type_adapter(cls):
    """
    Decorator for MSONables defined in emmet with arrow compatible
    type hints. Shortcut for generating type adapters rather than
    writing a dedicated stub file.
    """
    TypedClsDict = TypedDict(
        f"Typed{cls.__name__}Dict",
        {
            "@module": str,
            "@class": str,
            "@version": str,
            **{
                key: field.annotation
                for key, field in inspect.signature(cls).parameters.items()
            },
        },
    )

    class ClsTypeAdapter(RootModel):
        root: TypedClsDict

    setattr(cls, "__type_adapter__", ClsTypeAdapter)

    return cls


def arrow_incompatible(cls):
    """
    Simple decorator to mark a Pydantic model as being incompatible with
    serialization using pyarrow. This should only be applied as a temporary
    measure, all document models should aim for full type introspection.
    """
    cls.arrow_incompatible = True
    return cls


def get_sg(struc, symprec=SETTINGS.SYMPREC) -> int:
    """helper function to get spacegroup with a loose tolerance"""
    try:
        return struc.get_space_group_info(symprec=symprec)[1]
    except Exception:
        return -1


def get_num_formula_units(composition: dict[Any, int | float]) -> int:
    """Get the number of formula units in a dict-like composition.

    This implementation differs slightly from how some pymatgen/atomate2
    internals work. In those, certain formulas, e.g., N, will assume
    a smallest formula unit of N2. Thus even if a specified composition is
    `{"N": 1}`, the reduced composition will be `{"N": 2}`, and the number of
    formula units 1/2.

    This always just returns the greatest common divisor of a composition.
    """
    num_form_u = 1
    if all(abs(int(val) - val) < 1e-6 for val in composition.values()):
        num_form_u = gcd(*[int(sc) for sc in composition.values()])
    return num_form_u


def group_structures(
    structures: list[Structure],
    ltol: float = SETTINGS.LTOL,
    stol: float = SETTINGS.STOL,
    angle_tol: float = SETTINGS.ANGLE_TOL,
    symprec: float = SETTINGS.SYMPREC,
    comparator: AbstractComparator = ElementComparator(),
) -> Iterator[list[Structure]]:
    """
    Groups structures according to space group and structure matching

    Args:
        structures ([Structure]): list of structures to group
        ltol (float): StructureMatcher tuning parameter for matching tasks to materials
        stol (float): StructureMatcher tuning parameter for matching tasks to materials
        angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        symprec (float): symmetry tolerance for space group finding
    """

    sm = StructureMatcher(
        ltol=ltol,
        stol=stol,
        angle_tol=angle_tol,
        primitive_cell=True,
        scale=True,
        attempt_supercell=False,
        allow_subset=False,
        comparator=comparator,
    )

    def _get_sg(struc):
        return get_sg(struc, symprec=symprec)

    # First group by spacegroup number then by structure matching
    for _, pregroup in groupby(sorted(structures, key=_get_sg), key=_get_sg):
        for group in sm.group_structures(list(pregroup)):
            yield group


def undeform_structure(structure: Structure, transformations: dict) -> Structure:
    """
    Get an undeformed structure by applying transformations in a reverse order.

    Args:
        structure: deformed structure
        transformation: transformation that deforms the structure

    Returns:
        undeformed structure
    """

    for transformation in reversed(transformations.get("history", [])):
        if transformation["@class"] == "DeformStructureTransformation":
            deform = Deformation(transformation["deformation"])
            dst = DeformStructureTransformation(deform.inv)
            structure = dst.apply_transformation(structure)
        else:
            raise RuntimeError(
                "Expect transformation to be `DeformStructureTransformation`; "
                f"got {transformation['@class']}"
            )

    return structure


def generate_robocrys_condensed_struct_and_description(
    structure: Structure,
    mineral_matcher=None,
    symprecs: list[float] = [0.01, 0.1, 1.0e-3],
) -> tuple[dict[str, Any], Any]:
    """
    Get robocrystallographer description of a structure.

    Input
    ------
    structure : pymatgen .Structure
    mineral_matcher : optional robocrys MineralMatcher object
        Slightly reduces load time by storing mineral data
        in memory, rather than reloading for each structure.
    symprecs : list[float]
        A list of symprec values to try for symmetry identification.
        The first value is the default used by robocrys, then
        the default used by emmet (looser), then a tighter symprec.

    Output
    -------
    A robocrys condensed structure and description.
    """
    try:
        from robocrys import StructureCondenser, StructureDescriber
    except ImportError:
        raise ImportError(
            "robocrys needs to be installed to generate Robocrystallographer descriptions"
        )

    for isymprec, symprec in enumerate(symprecs):
        # occasionally, symmetry detection fails - give a few chances to modify symprec
        try:
            condenser = StructureCondenser(
                mineral_matcher=mineral_matcher, symprec=symprec
            )
            condensed_structure = condenser.condense_structure(structure)
            break
        except ValueError as exc:
            if isymprec == len(symprecs) - 1:
                raise exc

    for desc_fmt in ["unicode", "html", "raw"]:
        try:
            describer = StructureDescriber(
                describe_symmetry_labels=False, fmt=desc_fmt, return_parts=False
            )
            description = describer.describe(condensed_structure)
            break
        except ValueError as exc:
            # pymatgen won't convert a "subscript period" character to unicode
            # in these cases, the description is still generated but unicode
            # parsing failed - use html instead
            if "subscript period" not in str(exc):
                raise exc

    return condensed_structure, description


def group_molecules(molecules: list[Molecule]):
    """
    Groups molecules according to composition, charge, and equality

    Note: this function is (currently) only used in the MoleculesAssociationBuilder.
        At that stage, we want to link calculations that are performed on
        identical structures. Collapsing similar structures on the basis of e.g.
        graph isomorphism happens at a later stage.

    Args:
        molecules (list[Molecule])
    """

    def _mol_form(mol_solv):
        return mol_solv.composition.alphabetical_formula

    # Extremely tight tolerance is desirable
    # We want to match only calculations that are EXACTLY the same
    # Molecules with slight differences in bonding (which might be caused by, for instance,
    # different solvent environments)
    # This tolerance was chosen based on trying to distinguish CO optimized in
    # two different solvents
    mm = MoleculeMatcher(tolerance=0.000001)

    # First, group by formula
    # Hopefully this step is unnecessary - builders should already be doing this
    for mol_key, pregroup in groupby(sorted(molecules, key=_mol_form), key=_mol_form):
        groups: list[dict[str, Any]] = list()
        for mol in pregroup:
            mol_copy = copy.deepcopy(mol)

            # Single atoms could always have identical structure
            # So grouping by geometry isn't enough
            # Need to also group by charge
            if len(mol_copy) > 1:
                mol_copy.set_charge_and_spin(0)
            matched = False

            # Group by structure
            for group in groups:
                if (
                    (mm.fit(mol_copy, group["mol"]) or mol_copy == group["mol"])
                    and mol_copy.charge == group["mol"].charge
                    and mol_copy.spin_multiplicity == group["mol"].spin_multiplicity
                ):
                    group["mol_list"].append(mol)
                    matched = True
                    break

            if not matched:
                groups.append({"mol": mol_copy, "mol_list": [mol]})

        for group in groups:
            yield group["mol_list"]


def confirm_molecule(mol: Molecule | dict):
    """
    Check that something that we expect to be a molecule is actually a Molecule
    object, and not a dictionary representation.

    :param mol (Molecule):
    :return:
    """

    if isinstance(mol, dict):
        return Molecule.from_dict(mol)
    else:
        return mol


def make_mol_graph(
    mol: Molecule, critic_bonds: list[list[int]] | None = None
) -> MoleculeGraph:
    """
    Construct a MoleculeGraph using OpenBabelNN with metal_edge_extender and
    (optionally) Critic2 bonding information.

    This bonding scheme was used to define bonding for the Lithium-Ion Battery
    Electrolyte (LIBE) dataset (DOI: 10.1038/s41597-021-00986-9)

    :param mol: Molecule to be converted to MoleculeGraph
    :param critic_bonds: (optional) List of lists [a, b], where a and b are
        atom indices (0-indexed)

    :return: mol_graph, a MoleculeGraph
    """
    mol_graph = MoleculeGraph.from_local_env_strategy(mol, OpenBabelNN())
    mol_graph = metal_edge_extender(mol_graph)
    if critic_bonds:
        mg_edges = mol_graph.graph.edges()
        for bond in critic_bonds:
            bond.sort()
            if bond[0] != bond[1]:
                bond_tup = (bond[0], bond[1])
                if bond_tup not in mg_edges:
                    mol_graph.add_edge(bond_tup[0], bond_tup[1])
    return mol_graph


def get_graph_hash(mol: Molecule, node_attr: str | None = None):
    """
    Return the Weisfeiler Lehman (WL) graph hash of the MoleculeGraph described
    by this molecule, using the OpenBabelNN strategy with extension for
    metal coordinate bonds

    :param mol: Molecule
    :param node_attr: Node attribute to be used to compute the WL hash
    :return: string of the WL graph hash
    """

    mg = make_mol_graph(mol)
    return weisfeiler_lehman_graph_hash(
        mg.graph.to_undirected(),
        node_attr=node_attr,
    )


def get_molecule_id(mol: Molecule, node_attr: str | None = None):
    """
    Return an MPculeID for a molecule, with the hash component
    based on a particular attribute of the molecule graph representation.

    :param mol: Molecule
    :param node_attr:Node attribute to be used to compute the WL hash

    :return: MPculeID
    """

    graph_hash = get_graph_hash(mol, node_attr=node_attr)
    return MPculeID(
        "{}-{}-{}-{}".format(
            graph_hash,
            mol.composition.alphabetical_formula.replace(" ", ""),
            str(int(mol.charge)).replace("-", "m"),
            str(mol.spin_multiplicity),
        )
    )


def jsanitize(obj, strict=False, allow_bson=False):
    """
    This method cleans an input json-like object, either a list or a dict or
    some sequence, nested or otherwise, by converting all non-string
    dictionary keys (such as int and float) to strings, and also recursively
    encodes all objects using Monty's as_dict() protocol.
    Args:
        obj: input json-like object.
        strict (bool): This parameters sets the behavior when jsanitize
            encounters an object it does not understand. If strict is True,
            jsanitize will try to get the as_dict() attribute of the object. If
            no such attribute is found, an attribute error will be thrown. If
            strict is False, jsanitize will simply call str(object) to convert
            the object to a string representation.
        allow_bson (bool): This parameters sets the behavior when jsanitize
            encounters an bson supported type such as objectid and datetime. If
            True, such bson types will be ignored, allowing for proper
            insertion into MongoDb databases.
    Returns:
        Sanitized dict that can be json serialized.
    """
    if allow_bson and (
        isinstance(obj, (datetime.datetime, bytes))
        or (bson is not None and isinstance(obj, bson.objectid.ObjectId))
    ):
        return obj

    if isinstance(obj, (list, tuple, set)):
        return [jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj]
    if np is not None and isinstance(obj, np.ndarray):
        return [
            jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj.tolist()
        ]
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.items()
        }
    if isinstance(obj, MSONable):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.as_dict().items()
        }

    if isinstance(obj, BaseModel):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.model_dump().items()
        }
    if isinstance(obj, (int, float)):
        if np.isnan(obj):
            return 0
        return obj

    if obj is None:
        return None

    if not strict:
        return obj.__str__()

    if isinstance(obj, str):
        return obj.__str__()

    return jsanitize(obj.as_dict(), strict=strict, allow_bson=allow_bson)


def utcnow() -> datetime.datetime:
    """Get UTC time right now."""
    return datetime.datetime.now(datetime.timezone.utc)


def convert_datetime(
    v: datetime.datetime | dict[str, str] | str | None,
) -> datetime.datetime:
    """Validate datetime-like objects.

    Parameters
    -----------
    v : datetime, dict[str,str], str or None

    Returns
    -----------
    datetime
    """
    if not v:
        return utcnow()

    if isinstance(v, dict):
        if v.get("$date"):
            dt = datetime.datetime.fromisoformat(v["$date"])
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt

    if isinstance(v, str):
        dt = datetime.datetime.fromisoformat(v)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt

    v = MontyDecoder().process_decoded(v)
    if isinstance(v, datetime.datetime) and not v.tzinfo:
        v = v.replace(tzinfo=datetime.timezone.utc)
    return v  # type: ignore[return-value]


def get_hash_blocked(
    file_path: FSPathType, chunk_size: int = 4 * 1024 * 1024, hasher: Any | None = None
) -> str:
    """
    Get the hash of a file in byte chunks.

    Parameters
    -----------
    file_path : FSPathType
    chunk_size : int = 1,000,000 bytes (default)
        The byte chunk size to use in iteratively computing the hash.
    hahser : function to compute hashes. Defaults to blake3 if available,
        and MD5 if not.

    Returns
    -----------
    The hash as a str
    """
    if hasher is None:
        if blake3:
            hasher = blake3.blake3()
        else:
            hasher = hashlib.md5()

    with open(str(file_path), "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            hasher.update(data)
        return hasher.hexdigest()


def dynamic_import(module_path: str) -> Any:
    """Import arbitrary module or object."""
    paths = module_path.split(".")
    for i in range(len(paths), 0, -1):
        try:
            ob = import_module(".".join(paths[:i]))
            for path in paths[i:]:
                ob = getattr(ob, path)
            return ob
        except Exception:
            continue
    raise ValueError(f"Could not import string:\n{module_path}")


def get_flat_models_from_model(
    model: BaseModel, known_models: set[BaseModel] = set()
) -> set[BaseModel]:
    """Get all sub-models from a pydantic model.

    Args:
        model (BaseModel): Pydantic model
        known_models (set[BaseModel]) : set of identified pydantic sub-models

    Returns:
        (set[BaseModel]): Set of pydantic models
    """
    known_models = set()

    def get_sub_models(model: Any):
        if lenient_issubclass(model, BaseModel):
            known_models.add(model)
            for field_info in model.model_fields.values():
                get_sub_models(field_info.annotation)
        else:
            for type_anno in get_args(model):
                get_sub_models(type_anno)

    get_sub_models(model)
    return known_models


def requires_arrow(func: Callable) -> Callable:
    """Decorator for pyarrow-dependent functionality."""

    def wrap(*args, **kwargs):
        if not ARROW_COMPATIBLE:
            raise ImportError(
                "You must `pip install pyarrow` to use this functionality."
            )
        return func(*args, **kwargs)

    return wrap
