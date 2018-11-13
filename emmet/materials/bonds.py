import os.path
from monty.serialization import loadfn

import numpy as np

from itertools import chain

from pymatgen import Structure
from pymatgen.analysis.local_env import NearNeighbors
from pymatgen.analysis.graphs import StructureGraph
from pymatgen import __version__ as pymatgen_version

from maggma.builders import MapBuilder
from maggma.validator import JSONSchemaValidator, msonable_schema

__author__ = "Matthew Horton <mkhorton@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
BOND_SCHEMA = os.path.join(MODULE_DIR, "schema", "bond.json")


class BondBuilder(MapBuilder):
    def __init__(self, materials, bonding, strategies=("CrystalNN", ), **kwargs):
        """
        Builder to calculate bonding in a crystallographic
        structure via near neighbor strategies, including those
        in pymatgen.analysis.local_env and using the critic2 tool.

        Args:
            materials (Store): Store of materials documents
            bonding (Store): Store of topology data
            strategies (list): List of NearNeighbor classes to use (can be
            an instance of a NearNeighbor class or its name as a string,
            in which case it will be instantiated with default arguments)
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.bonding = bonding
        self.bonding.validator = JSONSchemaValidator(loadfn(BOND_SCHEMA))

        available_strategies = {nn.__name__: nn for nn in NearNeighbors.__subclasses__()}

        # use the class if passed directly (e.g. with custom kwargs),
        # otherwise instantiate class with default options
        self.strategies = [
            strategy if isinstance(strategy, NearNeighbors) else available_strategies[strategy]()
            for strategy in strategies
        ]
        self.strategy_names = [strategy.__class__.__name__ for strategy in self.strategies]

        self.bad_task_ids = []  # Voronoi-based strategies can cause some structures to cause crash

        super().__init__(source=materials, target=bonding, ufn=self.calc, projection=["structure"], **kwargs)

    def calc(self, item):
        """
        Calculates StructureGraphs (bonding information) for a material
        """

        bonding_docs = []
        structure = Structure.from_dict(item["structure"])
        task_id = item[self.materials.key]

        # try all local_env strategies
        for strategy, strategy_name in zip(self.strategies, self.strategy_names):
            self.logger.debug("Calculating bonding for {} {}".format(task_id, strategy_name))

            # failure statistics are interesting
            try:

                sg = StructureGraph.with_local_env_strategy(structure, strategy)

                # ensure edge weights are specifically bond lengths
                edge_weights = []
                for u, v, d in sg.graph.edges(data=True):
                    jimage = np.array(d["to_jimage"])
                    dist = sg.structure.get_distance(u, v, jimage=jimage)
                    edge_weights.append((u, v, d["to_jimage"], dist))
                for u, v, to_jimage, dist in edge_weights:
                    sg.alter_edge(u, v, to_jimage=to_jimage, new_weight=dist)

                bonding_docs.append({
                    "strategy": strategy_name,
                    "graph": sg.as_dict(),
                    "summary": {
                        "bond_types": sg.types_and_weights_of_connections,
                        "bond_length_stats": sg.weight_statistics,
                        "coordination_envs": sg.types_of_coordination_environments(),
                        "coordination_envs_anonymous": sg.types_of_coordination_environments(anonymous=True)
                    },
                    "successful": True
                })

            except Exception as e:

                self.logger.warning("Failed to calculate bonding: {} {} {}".format(task_id, strategy_name, e))

                bonding_docs.append({"strategy": strategy_name, "successful": False, "error_message": str(e)})

        return {
            "pymatgen_version": str(pymatgen_version),
            "bonding": [b for b in bonding_docs if b["successful"]],
            "failed_bonding": [b["strategy"] for b in bonding_docs if not b["successful"]]
        }
