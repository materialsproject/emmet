import logging
from collections import defaultdict
from typing import Dict, List, Any, Union

import numpy as np
from pydantic import Field
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.analysis.local_env import NearNeighbors
from pymatgen.core import Structure
from pymatgen.core.periodic_table import Specie
from typing_extensions import Literal

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID

AVAILABLE_METHODS = {nn.__name__: nn for nn in NearNeighbors.__subclasses__()}


class BondingDoc(PropertyDoc):
    """Structure graphs representing chemical bonds calculated from structure
    using near neighbor strategies as defined in pymatgen."""

    property_name = "bonding"

    structure_graph: StructureGraph = Field(
        description="Structure graph",

    )

    method: str = Field(description="Method used to compute structure graph.")

    bond_types: Dict[str, List[float]] = Field(
        description="Dictionary of bond types to their length, e.g. a Fe-O to "
        "a list of the lengths of Fe-O bonds in Angstrom."
    )
    bond_length_stats: Dict[str, Any] = Field(
        description="Dictionary of statistics of bonds in structure "
        "with keys all_weights, min, max, mean and variance."
    )
    coordination_envs: List[str] = Field(
        description="List of co-ordination environments, e.g. ['Mo-S(6)', 'S-Mo(3)']."
    )
    coordination_envs_anonymous: List[str] = Field(
        description="List of co-ordination environments without elements "
        "present, e.g. ['A-B(6)', 'A-B(3)']."
    )

    @classmethod
    def from_structure(
        cls,
        structure,
        material_id,
        preferred_methods=(
            "CrystalNN",
            "MinimumDistanceNN",
        ),
        **kwargs
    ):
        """
        Calculate

        :param structure: ideally an oxidation state-decorated structure
        :param material_id: mpid
        :param preferred_methods: list of strings of NearNeighbor classes or NearNeighbor instances
        :param deprecated: whether source material is or is not deprecated
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        bonding_info = None
        preferred_methods = [  # type: ignore
            AVAILABLE_METHODS[method]() if isinstance(method, str) else method
            for method in preferred_methods
        ]

        for method in preferred_methods:

            try:

                sg = StructureGraph.with_local_env_strategy(structure, method)

                # ensure edge weights are specifically bond lengths
                edge_weights = []
                for u, v, d in sg.graph.edges(data=True):
                    jimage = np.array(d["to_jimage"])
                    dist = sg.structure.get_distance(u, v, jimage=jimage)
                    edge_weights.append((u, v, d["to_jimage"], dist))
                for u, v, to_jimage, dist in edge_weights:
                    sg.alter_edge(u, v, to_jimage=to_jimage, new_weight=dist)

                bonding_info = {
                    "method": method.__class__.__name__,
                    "structure_graph": sg,
                    "bond_types": sg.types_and_weights_of_connections,
                    "bond_length_stats": sg.weight_statistics,
                    "coordination_envs": sg.types_of_coordination_environments(),
                    "coordination_envs_anonymous": sg.types_of_coordination_environments(
                        anonymous=True
                    ),
                }

                break

            except Exception as e:

                logging.warning(
                    "Failed to calculate bonding: {} {} {}".format(
                        material_id, method, e
                    )
                )

        if bonding_info:

            return super().from_structure(
                meta_structure=structure,
                material_id=material_id,
                **bonding_info,
                **kwargs
            )
