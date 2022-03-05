from typing import Dict, List, Any
import copy
from collections import defaultdict

from typing_extensions import Literal

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.core.qchem.calc_types import TaskType
from emmet.core.qchem.molecule import evaluate_lot
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.bonds import metals
from emmet.core.molecules.thermo import get_free_energy
from emmet.core.mpid import MPID


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


reference_potentials = {"H": 4.44, "Li": 1.40, "Mg": 2.06, "Ca": 1.60}


class RedoxDoc(PropertyDoc):
    """
    Molecular properties related to reduction and oxidation, including
    vertical ionization energies and electron affinities, as well as reduction
    and oxidation potentials
    """

    property_name = "redox"

    electron_affinity: float = Field(description="Vertical electron affinity in eV")

    ea_id: MPID = Field(description="Molecule ID for electron affinity")

    ionization_energy: float = Field(description="Vertical ionization energy in eV")

    ie_id: MPID = Field(description="Molecule ID for ionization energy")

    reduction_free_energy: float = Field(
        None, description="Adiabatic free energy of reduction"
    )

    red_id: MPID = Field(None, description="Molecule ID for adiabatic reduction")

    oxidation_free_energy: float = Field(
        None, description="Adiabatic free energy of oxidation"
    )

    ox_id: MPID = Field(None, description="Molecule ID for adiabatic oxidation")

    reduction_potentials: Dict[str, float] = Field(
        None, description="Reduction potentials with various reference electrodes"
    )

    oxidation_potentials: Dict[str, float] = Field(
        None, description="Oxidation potentials with various reference electrodes"
    )

    @classmethod
    def from_entries(cls, entries: List[Dict[str, Any]], **kwargs) -> List["RedoxDoc"]:
        """
        Construct documents describing molecular redox properties from task
        entry dictionaries.
        Note that multiple documents may be made by this procedure.

        General procedure:
        1. Group tasks by composition
        2. Group by covalent molecule graph
        3. Group by level of theory (LOT)
        3. Within each group, construct documents, preferring higher LOT

        :param entries: List of entries (dicts derived from TaskDocuments)
        :param kwargs: To be passed to PropertyDoc
        :return:
        """

        docs = list()

        mm = MoleculeMatcher()

        # First, group tasks by formula
        tasks_by_formula = defaultdict(list)
        for t in entries:
            tasks_by_formula[t["formula"]].append(t)

        for form_group in tasks_by_formula.values():
            mol_graphs_nometal = list()
            group_by_graph = defaultdict(list)

            # Within each group, group by the covalent molecular graph
            for t in form_group:
                mol = t["molecule"]

                if isinstance(mol, dict):
                    mol = Molecule.from_dict(mol)

                mol_nometal = copy.deepcopy(mol)

                if mol.composition.alphabetical_formula not in [
                    m + "1" for m in metals
                ]:
                    mol_nometal.remove_species(metals)

                mol_nometal.set_charge_and_spin(0)
                mg_nometal = MoleculeGraph.with_local_env_strategy(
                    mol_nometal, OpenBabelNN()
                )
                match = None
                for i, mg in enumerate(mol_graphs_nometal):
                    if mg_nometal.isomorphic_to(mg):
                        match = i
                        break

                if match is None:
                    group_by_graph[len(mol_graphs_nometal)].append(t)
                    mol_graphs_nometal.append(mg_nometal)
                else:
                    group_by_graph[match].append(t)

            # Now finally, group by level of theory
            for graph_group in group_by_graph.values():
                lot_groups = defaultdict(list)
                for t in graph_group:
                    lot_groups[t["level_of_theory"]].append(t)

                docs_by_charge = dict()
                # Now try to form documents
                # Start with highest lot; keep going down until you can make complete documents
                for lot, group in sorted(
                    lot_groups.items(), key=lambda x: evaluate_lot(x[0])
                ):
                    # Sorting important because we want to make docs only from lowest-energy instances
                    relevant_calcs = sorted(
                        [
                            f
                            for f in group
                            if f["task_type"]
                            == TaskType.Frequency_Flattening_Geometry_Optimization
                        ],
                        key=lambda x: x["output"]["final_energy"],
                    )

                    # For single atoms, which have no FFOpt calcs
                    # (Can't geometry optimize a single atom)
                    if len(relevant_calcs) == 0:
                        relevant_calcs = sorted(
                            [f for f in group],
                            key=lambda x: x["output"]["final_energy"],
                        )

                    charges = [f["charge"] for f in relevant_calcs]
                    if all([c in docs_by_charge for c in charges]):
                        continue
                    single_points = [
                        s for s in group if s["task_type"] == TaskType.Single_Point
                    ]

                    for ff in relevant_calcs:
                        d = {
                            "electron_affinity": None,
                            "ea_id": None,
                            "ionization_energy": None,
                            "ie_id": None,
                            "reduction_free_energy": None,
                            "red_id": None,
                            "oxidation_free_energy": None,
                            "ox_id": None,
                            "reduction_potentials": None,
                            "oxidations_potentials": None,
                        }

                        charge = ff["charge"]

                        # Doc already exists at a higher LOT; move on
                        if charge in docs_by_charge:
                            continue

                        ff_mol = ff["output"]["optimized_molecule"]
                        if ff_mol is None:
                            ff_mol = ff["output"]["initial_molecule"]
                        if isinstance(ff_mol, dict):
                            ff_mol = Molecule.from_dict(ff_mol)

                        try:
                            ff_g = get_free_energy(
                                ff["output"]["final_energy"],
                                ff["output"]["enthalpy"],
                                ff["output"]["entropy"],
                            )
                        # Single atoms won't have enthalpy and entropy
                        except TypeError:
                            ff_g = ff["output"]["final_energy"]

                        # Look for IE and EA SP
                        for sp in single_points:
                            sp_mol = sp["output"]["initial_molecule"]
                            if isinstance(sp_mol, dict):
                                sp_mol = Molecule.from_dict(sp_mol)

                            # EA
                            if sp["charge"] == charge - 1 and mm.fit(ff_mol, sp_mol):
                                d["electron_affinity"] = (
                                    sp["output"]["final_energy"]
                                    - ff["output"]["final_energy"]
                                ) * 27.2114
                                d["ea_id"] = sp["task_id"]

                            # IE
                            elif sp["charge"] == charge + 1 and mm.fit(ff_mol, sp_mol):
                                d["ionization_energy"] = (
                                    sp["output"]["final_energy"]
                                    - ff["output"]["final_energy"]
                                ) * 27.2114
                                d["ie_id"] = sp["task_id"]

                            if d["ea_id"] is not None and d["ie_id"] is not None:
                                break

                        # If no vertical IE or EA, can't make complete doc; give up
                        if d["ea_id"] is None or d["ie_id"] is None:
                            continue

                        # Look for adiabatic reduction and oxidation calcs
                        for other in relevant_calcs:
                            # Reduction
                            if other["charge"] == charge - 1:
                                try:
                                    other_g = get_free_energy(
                                        other["output"]["final_energy"],
                                        other["output"]["enthalpy"],
                                        other["output"]["entropy"],
                                    )
                                except TypeError:
                                    # Single atoms
                                    other_g = other["output"]["final_energy"]
                                d["reduction_free_energy"] = other_g - ff_g
                                d["reduction_potentials"] = dict()
                                for ref, pot in reference_potentials.items():
                                    d["reduction_potentials"][ref] = (
                                        -1 * d["reduction_free_energy"] - pot
                                    )
                                d["red_id"] = other["task_id"]

                            # Oxidation
                            elif other["charge"] == charge + 1:
                                try:
                                    other_g = get_free_energy(
                                        other["output"]["final_energy"],
                                        other["output"]["enthalpy"],
                                        other["output"]["entropy"],
                                    )
                                except TypeError:
                                    # Single atoms
                                    other_g = other["output"]["final_energy"]
                                d["oxidation_free_energy"] = other_g - ff_g
                                d["oxidation_potentials"] = dict()
                                for ref, pot in reference_potentials.items():
                                    d["oxidation_potentials"][ref] = (
                                        d["oxidation_free_energy"] - pot
                                    )

                                d["ox_id"] = other["task_id"]

                            if d["red_id"] is not None and d["ox_id"] is not None:
                                break

                        # Need to either be able to oxidize or reduce the molecule to make a doc
                        if d["red_id"] is None and d["ox_id"] is None:
                            continue

                        origins = list()
                        for x in [
                            ff["task_id"],
                            d["ea_id"],
                            d["ie_id"],
                            d["red_id"],
                            d["ox_id"],
                        ]:
                            if x is not None:
                                origins.append(PropertyOrigin(name="redox", task_id=x))

                        docs_by_charge[charge] = RedoxDoc.from_molecule(
                            meta_molecule=ff_mol,
                            molecule_id=ff.get("entry_id", ff["task_id"]),
                            origins=origins,
                            deprecated=False,
                            **d,
                            **kwargs
                        )
                        if all([c in docs_by_charge for c in charges]):
                            break

                for doc in docs_by_charge.values():
                    docs.append(doc)

        return docs
