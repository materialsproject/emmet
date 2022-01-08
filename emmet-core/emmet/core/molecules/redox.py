import logging
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Union
import copy
from collections import defaultdict

from typing_extensions import Literal

import numpy as np
from pydantic import Field
import networkx as nx

from pymatgen.core.structure import Molecule
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN, metal_edge_extender

from pymatgen.core.periodic_table import Specie, Element

from emmet.core import SETTINGS
from emmet.core.mpid import MPID
from emmet.core.qchem.task import TaskDocument
from emmet.core.qchem.molecule import evaluate_molecule
from emmet.core.molecules.molecule_property import PropertyDoc
from emmet.core.molecules.bonds import metals



reference_potentials = {"H": 4.44,
                        "Li": 1.4,
                        "Mg": 2.06,
                        "Ca": 1.60}

class RedoxDoc(PropertyDoc):
    """
    Molecular properties related to reduction and oxidation, including
    vertical ionization energies and electron affinities, as well as reduction
    and oxidation potentials
    """

    electron_affinity: float = Field(description="Vertical electron affinity in eV")

    ea_id: MPID = Field(description="MPID for electron affinity")

    ionization_energy: float = Field(description="Vertical ionization energy in eV")

    ie_id: MPID = Field(description="MPID for ionization energy")

    reduction_free_energy: float = Field(description="Adiabatic free energy of reduction")

    red_id = MPID = Field(description="MPID for adiabatic reduction")

    oxidation_free_energy: float = Field(description="Adiabatic free energy of oxidation")

    ox_id = MPID = Field(description="MPID for adiabatic oxidation")

    reduction_potentials: Dict[str, float] = Field(description="Reduction potentials with various reference electrodes")

    oxidation_potentials: Dict[str, float] = Field(description="Oxidation potentials with various reference electrodes")

    @classmethod
    def from_tasks(
        cls,
        tasks: List[TaskDocument],
        **kwargs
    ):
        """
        Construct documents describing molecular redox properties from task documents.
        Note that multiple documents may be made by this procedure.

        General procedure:
        1. Group tasks by composition
        2. Group by covalent molecule graph
        3. Group by level of theory (LOT)
        3. Within each group, construct documents, preferring higher LOT

        :param tasks:
        :param kwargs:
        :return:
        """

        docs = list()

        # First, group tasks by formula
        tasks_by_formula = defaultdict(list)
        for t in tasks:
            tasks_by_formula[t.formula_alphabetical].append(t)
            
        for form_group in tasks_by_formula.values():
            mol_graphs_nometal = list()
            group_by_graph = defaultdict(list)

            # Within each group, group by the covalent molecular graph
            for task in form_group:
                if task.output.optimized_molecule is not None:
                    mol = task.output.optimized_molecule
                else:
                    mol = task.output.initial_molecule

                mol_nometal = copy.deepcopy(mol)
                mol_nometal.remove_species(metals)
                mol_nometal.set_charge_and_spin(0)
                mg_nometal = MoleculeGraph.with_local_env_strategy(mol_nometal, OpenBabelNN())
                match = None
                for i, mg in mol_graphs_nometal:
                    if mg_nometal.isomorphic_to(mg):
                        match = i
                        break

                if match is None:
                    group_by_graph[len(mol_graphs_nometal)].append(task)
                    mol_graphs_nometal.append(mg_nometal)
                else:
                    group_by_graph[match].append(task)

            # Now finally, group by level of theory
            for graph_group in group_by_graph.values():
                lot_groups = defaultdict(list)
                for task in graph_group:
                    lot_groups[task.level_of_theory].append(task)

                # Now see if we have enough data for a full document