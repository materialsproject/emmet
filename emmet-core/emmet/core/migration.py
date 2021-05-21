import logging
import math
import operator
from datetime import datetime
from itertools import groupby
from typing import Iterable, List, Union

from monty.json import MontyDecoder
from pydantic import BaseModel, Field, validator
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher
from pymatgen.core import Composition, Structure
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.core.structure_group import StructureGroupDoc

__author__ = "Jimmy Shen"
__email__ = "jmmshn@gmail.com"

logger = logging.getLogger(__name__)


class MigrationGraphDoc(BaseModel):
    """
    Migration Graph
    """

    battery_id: str = Field(
        None,
        description="The id for this migration graph document, shared with "
        "insertion electrode since the same kind of structure "
        "grouping is performed.",
    )

    # host_structure: Structure = Field(
    #     None,
    #     description="Host structure (structure without the working ion)",
    # )
    #
    # migration_graph: StructureGraph = Field(
    #     None,
    #     description="The StructureGraph object that contains all of the migration sites"
    # )
    #
    # framework: Composition = Field(
    #     None,
    #     description="The chemical compositions of the host framework",
    # )
    #
    # elements: List[Element] = Field(
    #     None,
    #     description="The atomic species contained in the host structure (not including the working ion).",
    # )
    #
    # nelements: int = Field(
    #     None,
    #     description="The number of elements in the material (not including the working ion).",
    # )
    #
    # chemsys: str = Field(
    #     None,
    #     description="The chemical system the host lattice belongs to (not including the working ion)",
    # )

    found_path: bool = Field(
        None, description="True, if an intercalating path is found."
    )

    ltol: float = Field(
        None, description="Lattice length tolerance parameter for the StructureMatcher."
    )

    stol: float = Field(
        None, description="site position tolerance parameter for the StructureMatcher."
    )

    angle_tol: float = Field(
        None, description="Bond angle tolerance parameter for the StructureMatcher."
    )

    symprec: float = Field(None, description="SPGLIB tolerance parameter.")

    migration_graph_object: MigrationGraph = Field(
        None, description="The migration pathway object forom " "pymatgen-diffussion."
    )

    barrier: float = Field(
        None,
        description="The highest energy difference along the path with the "
        "lowest cumulative absolute energy difference.",
    )

    last_updated: datetime = Field(
        None,
        description="Timestamp when this document was built.",
    )

    # Make sure that the datetime field is properly formatted
    @validator("last_updated", pre=True)
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)

    @classmethod
    def from_entries(
        cls,
        entries: List[ComputedStructureEntry],
        working_ion_entry: ComputedEntry,
        ltol: float,
        stol: float,
        angle_tol: float,
        symprec: float,
        min_distance_cutoff: float = 5.0,
        max_distance_cutoff: float = 10.0,
        **kwargs,
    ) -> Union["MigrationGraphDoc", None]:
        """
        Parse a list of entries and construct the migration graph.
        The tolerances must be explicitly provided.
        Args:
            entries: A list of entries that is already grouped together.
            working_ion_entry: Computed entry containing the metallic phase of the working ion.
            ltol: length tolerance parameter
            stol: site tolerance parameter
            angle_tol: angular tolerance parameter
            symprec: SPGLIB tolerance parameter
            min_distance_cutoff: The initial guess for the bonding distance, if no intercalation pathways are found,
                                    the threshold will be increased by 1 Angstrom until max_distance_cutoff
            max_distance_cutoff: The maximum we allowed to increase the distance cutoff to look for
                                    intercalation pathways
            kwargs: Additional kwargs to help search and filter, should be taken directly from electrode document.

        Returns:
            A MigrationGraphDocument
        """
        migrating_species = working_ion_entry.composition.reduced_formula
        cur_id = kwargs.get("battery_id", "MISSING battery_id")

        slist = MigrationGraph.get_structure_from_entries(
            entries=entries,
            migrating_ion_entry=working_ion_entry,
            ltol=ltol,
            stol=stol,
            angle_tol=angle_tol,
            symprec=symprec,
        )

        if len(slist) == 0:
            logger.warning(
                f"No structure with meta-stable sites could be generate for id: [{cur_id}]"
            )
            return None

        struct = slist[0]
        d_cut = min_distance_cutoff
        mg = None
        while d_cut <= max_distance_cutoff:
            mg = MigrationGraph.with_distance(
                structure=struct,
                migrating_specie=migrating_species,
                max_distance=d_cut,
                symprec=0.01,
            )
            mg.assign_cost_to_graph()
            u, path_hops = next(mg.get_path())
            if len(path_hops) != 0:
                break
            d_cut += 1.0

        if mg is None:
            logger.warning(f"No Migration graph could be generate for id: [{cur_id}]")
            return None

        # adding the energy difference
        for lab, d in mg.unique_hops.items():
            e_u = mg.only_sites.sites[d["iindex"]].properties["insertion_energy"]
            e_v = mg.only_sites.sites[d["eindex"]].properties["insertion_energy"]
            ediff = abs(e_u - e_v)
            mg.add_data_to_similar_edges(
                target_label=d["hop_label"], data={"ediff": ediff}
            )

        mg.assign_cost_to_graph(cost_keys=["ediff"])
        lowest_cost, best_path = math.inf, []

        for u, path in mg.get_path():
            cum_cost = sum([hop["cost"] for hop in path])
            if cum_cost < lowest_cost:
                lowest_cost, best_path = cum_cost, path

        all_sites_along_path = set()

        for hop in best_path:
            all_sites_along_path |= {hop["iindex"], hop["eindex"]}

        site_energies = [
            mg.only_sites.sites[ii_].properties["insertion_energy"]
            for ii_ in all_sites_along_path
        ]
        barrier = max(site_energies) - min(site_energies)

        fields = {
            "ltol": ltol,
            "stol": stol,
            "angle_tol": angle_tol,
            "migration_graph_object": mg,
            "barrier": barrier,
        }

        fields.update(kwargs)
        return cls(**fields)
