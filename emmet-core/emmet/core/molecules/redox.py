from typing import Any, Dict, List, Type, TypeVar, Union
import copy
from collections import defaultdict

from typing_extensions import Literal

from pydantic import Field

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender
from pymatgen.analysis.molecule_matcher import MoleculeMatcher

from emmet.core.utils import confirm_molecule
from emmet.core.qchem.calc_types import TaskType
from emmet.core.qchem.task import filter_task_type
from emmet.core.qchem.molecule import evaluate_lot
from emmet.core.material import PropertyOrigin
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.bonds import metals
from emmet.core.molecules.thermo import get_free_energy
from emmet.core.mpid import MPID


__author__ = "Evan Spotte-Smith <ewcspottesmith@lbl.gov>"


reference_potentials = {"H": 4.44, "Li": 1.40, "Mg": 2.06, "Ca": 1.60}


T = TypeVar("T", bound="RedoxDoc")


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
    def _group_by_formula(cls: Type[T],
                          entries: List[Dict[str, Any]]
                          ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group task entries by formula

        :param entries: List of entries (dicts derived from TaskDocuments)
        :return: Grouped molecule entries
        """

        # First, group tasks by formula
        tasks_by_formula = defaultdict(list)
        for t in entries:
            if not isinstance(t["output"], dict):
                t["output"] = t["output"].as_dict()
            tasks_by_formula[t["formula"]].append(t)

        return tasks_by_formula

    @classmethod
    def _group_by_graph(
        cls: Type[T], entries: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Group task entries by molecular graph connectivity

        :param entries: List of entries (dicts derived from TaskDocuments)
        :return: Grouped molecule entries
        """

        mol_graphs_nometal: List[MoleculeGraph] = list()
        results = defaultdict(list)

        # Within each group, group by the covalent molecular graph
        for t in entries:
            mol = confirm_molecule(t["molecule"])

            mol_nometal = copy.deepcopy(mol)

            if mol.composition.alphabetical_formula not in [m + "1" for m in metals]:
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
                results[len(mol_graphs_nometal)].append(t)
                mol_graphs_nometal.append(mg_nometal)
            else:
                results[match].append(t)

        return results

    @classmethod
    def _g_or_e(cls: Type[T], entry: Dict[str, Any]) -> float:
        """
        Single atoms may not have free energies like more complex molecules do.
        This function returns the free energy of a TaskDocument entry if
        possible, and otherwise returns the electronic energy.

        :param entry: dict representation of a TaskDocument
        :return:
        """
        try:
            result = get_free_energy(
                entry["output"]["final_energy"],
                entry["output"]["enthalpy"],
                entry["output"]["entropy"],
            )
        # Single atoms won't have enthalpy and entropy
        except TypeError:
            result = entry["output"]["final_energy"]

        return result

    @classmethod
    def from_entries(cls: Type[T], entries: List[Dict[str, Any]], **kwargs) -> List[T]:
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

        tasks_by_formula = cls._group_by_formula(entries)

        for form_group in tasks_by_formula.values():
            # Group by molecular graph connectivity
            group_by_graph = cls._group_by_graph(form_group)

            # Now finally, group by level of theory
            for graph_group in group_by_graph.values():
                lot_groups = defaultdict(list)
                for t in graph_group:
                    lot_groups[t["level_of_theory"]].append(t)

                docs_by_charge: Dict[Union[int, float], T] = dict()
                # Now try to form documents
                # Start with highest lot; keep going down until you can make complete documents
                for lot, group in sorted(
                    lot_groups.items(), key=lambda x: evaluate_lot(x[0])
                ):
                    # Sorting important because we want to make docs only from lowest-energy instances
                    relevant_calcs = filter_task_type(
                        group,
                        TaskType.Frequency_Flattening_Geometry_Optimization,
                        sort_by=lambda x: x["energy"],
                    )

                    # For single atoms, which have no FFOpt calcs
                    # (Can't geometry optimize a single atom)
                    relevant_calcs = relevant_calcs or sorted(
                        group, key=lambda x: x["energy"]
                    )

                    single_points = filter_task_type(group, TaskType.Single_Point)

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

                        ff_mol = confirm_molecule(
                            ff["output"]["optimized_molecule"]
                            or ff["output"]["initial_molecule"]
                        )

                        ff_g = cls._g_or_e(ff)

                        # Look for IE and EA SP
                        for sp in single_points:
                            sp_mol = confirm_molecule(sp["output"]["initial_molecule"])

                            # EA
                            if (
                                sp["charge"] == charge - 1
                                and mm.fit(ff_mol, sp_mol)
                                and d["ea_id"] is None
                            ):
                                d["electron_affinity"] = (
                                    sp["energy"] - ff["energy"]
                                ) * 27.2114
                                d["ea_id"] = sp["task_id"]

                            # IE
                            elif (
                                sp["charge"] == charge + 1
                                and mm.fit(ff_mol, sp_mol)
                                and d["ie_id"] is None
                            ):
                                d["ionization_energy"] = (
                                    sp["energy"] - ff["energy"]
                                ) * 27.2114
                                d["ie_id"] = sp["task_id"]

                        # If no vertical IE or EA, can't make complete doc; give up
                        if d["ea_id"] is None or d["ie_id"] is None:
                            continue

                        # Look for adiabatic reduction and oxidation calcs
                        for other in relevant_calcs:
                            # Reduction
                            if other["charge"] == charge - 1 and d["red_id"] is None:
                                other_g = cls._g_or_e(other)

                                d["reduction_free_energy"] = other_g - ff_g
                                d["reduction_potentials"] = dict()

                                for ref, pot in reference_potentials.items():
                                    d["reduction_potentials"][ref] = (
                                        -1 * d["reduction_free_energy"] - pot
                                    )

                                d["red_id"] = other["task_id"]

                            # Oxidation
                            elif other["charge"] == charge + 1 and d["ox_id"] is None:
                                other_g = cls._g_or_e(other)

                                d["oxidation_free_energy"] = other_g - ff_g
                                d["oxidation_potentials"] = dict()

                                for ref, pot in reference_potentials.items():
                                    d["oxidation_potentials"][ref] = (
                                        d["oxidation_free_energy"] - pot
                                    )

                                d["ox_id"] = other["task_id"]

                        origins = list()
                        for x in [
                            a
                            for a in [
                                ff["task_id"],
                                d["ea_id"],
                                d["ie_id"],
                                d["red_id"],
                                d["ox_id"],
                            ]
                            if a is not None
                        ]:
                            origins.append(PropertyOrigin(name="redox", task_id=x))

                        docs_by_charge[charge] = RedoxDoc.from_molecule(
                            meta_molecule=ff_mol,
                            molecule_id=ff.get("entry_id", ff["task_id"]),
                            origins=origins,
                            deprecated=False,
                            **d,
                            **kwargs
                        )

                for doc in docs_by_charge.values():
                    docs.append(doc)

        return docs
