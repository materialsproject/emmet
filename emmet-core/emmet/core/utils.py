import copy
import datetime
from enum import Enum
from itertools import groupby
from typing import Any, Dict, Iterator, List, Optional, Union

import numpy as np

from monty.json import MSONable

from pydantic import BaseModel

from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher
from pymatgen.analysis.structure_matcher import (
    AbstractComparator,
    ElementComparator,
    StructureMatcher,
)
from pymatgen.core.structure import Molecule, Structure
from pymatgen.util.graph_hashing import weisfeiler_lehman_graph_hash

from emmet.core.mpid import MPculeID
from emmet.core.settings import EmmetSettings

try:
    import bson
except ImportError:
    bson = None  # type: ignore

SETTINGS = EmmetSettings()


def get_sg(struc, symprec=SETTINGS.SYMPREC) -> int:
    """helper function to get spacegroup with a loose tolerance"""
    try:
        return struc.get_space_group_info(symprec=symprec)[1]
    except Exception:
        return -1


def group_structures(
    structures: List[Structure],
    ltol: float = SETTINGS.LTOL,
    stol: float = SETTINGS.STOL,
    angle_tol: float = SETTINGS.ANGLE_TOL,
    symprec: float = SETTINGS.SYMPREC,
    comparator: AbstractComparator = ElementComparator(),
) -> Iterator[List[Structure]]:
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


def group_molecules(molecules: List[Molecule]):
    """
    Groups molecules according to composition, charge, and equality

    Note: this function is (currently) only used in the MoleculesAssociationBuilder.
        At that stage, we want to link calculations that are performed on
        identical structures. Collapsing similar structures on the basis of e.g.
        graph isomorphism happens at a later stage.

    Args:
        molecules (List[Molecule])
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
        groups: List[Dict[str, Any]] = list()
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


def confirm_molecule(mol: Union[Molecule, Dict]):
    """
    Check that something that we expect to be a molecule is actually a Molecule
    object, and not a dictionary representation.

    :param mol (Molecule):
    :return:
    """

    if isinstance(mol, Dict):
        return Molecule.from_dict(mol)
    else:
        return mol


def make_mol_graph(
    mol: Molecule, critic_bonds: Optional[List[List[int]]] = None
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
    mol_graph = MoleculeGraph.with_local_env_strategy(mol, OpenBabelNN())
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


def get_graph_hash(mol: Molecule, node_attr: Optional[str] = None):
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


def get_molecule_id(mol: Molecule, node_attr: Optional[str] = None):
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


class ValueEnum(Enum):
    """
    Enum that serializes to string as the value
    """

    def __str__(self):
        return str(self.value)

    def __eq__(self, obj: object) -> bool:
        """Special Equals to enable converting strings back to the enum"""
        if isinstance(obj, str):
            return super().__eq__(self.__class__(obj))
        elif isinstance(obj, self.__class__):
            return super().__eq__(obj)
        return False

    def __hash__(self):
        """Get a hash of the enum."""
        return hash(str(self))

    def as_dict(self):
        """Create a serializable representation of the enum."""
        return str(self.value)


class DocEnum(ValueEnum):
    """
    Enum with docstrings support
    from: https://stackoverflow.com/a/50473952
    """

    def __new__(cls, value, doc=None):
        """add docstring to the member of Enum if exists

        Args:
            value: Enum member value
            doc: Enum member docstring, None if not exists
        """
        self = object.__new__(cls)  # calling super().__new__(value) here would fail
        self._value_ = value
        if doc is not None:
            self.__doc__ = doc
        return self


def get_enum_source(enum_name, doc, items):
    header = f"""
class {enum_name}(ValueEnum):
    \"\"\" {doc} \"\"\"\n
"""
    items = [f'    {const} = "{val}"' for const, val in items.items()]

    return header + "\n".join(items)
