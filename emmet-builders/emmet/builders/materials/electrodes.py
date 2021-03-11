import operator
import math
from collections import namedtuple
from datetime import datetime
from functools import lru_cache
from itertools import groupby, chain
from pprint import pprint
from typing import Iterable, Dict, List, Any

from emmet.core.electrode import InsertionElectrodeDoc
from emmet.core.structure_group import StructureGroupDoc
from emmet.core.utils import jsanitize
from maggma.builders import Builder, MapBuilder
from maggma.stores import MongoStore
from monty.json import MontyEncoder
from numpy import unique
from pymatgen.core import Composition
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.core import Structure
from pymatgen.entries.computed_entries import ComputedStructureEntry, ComputedEntry

__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"

class InsertionElectrodeBuilder(MapBuilder):
    def __init__(
        self,
        grouped_materials: MongoStore,
        insertion_electrode: MongoStore,
        thermo: MongoStore,
        query: dict = None,
        **kwargs,
    ):
        self.grouped_materials = grouped_materials
        self.insertion_electrode = insertion_electrode
        self.thermo = thermo
        qq_ = {} if query is None else query
        qq_.update({"structure_matched": True, "has_distinct_compositions": True})
        super().__init__(
            source=self.grouped_materials,
            target=self.insertion_electrode,
            query=qq_,
            **kwargs,
        )

    def get_items(self):
        """"""

        @lru_cache()
        def get_working_ion_entry(working_ion):
            with self.thermo as store:
                working_ion_docs = [*store.query({"chemsys": working_ion})]
            best_wion = min(
                working_ion_docs, key=lambda x: x["energy_per_atom"]
            )
            return best_wion

        def modify_item(item):
            self.logger.debug(
                f"Looking for {len(item['grouped_ids'])} material_id in the Thermo DB."
            )
            with self.thermo as store:
                thermo_docs = [
                    *store.query(
                        {
                            "$and": [
                                {"material_id": {"$in": item["grouped_ids"]}},
                            ]
                        },
                        properties=["material_id", "_sbxn", "thermo", "entries", "energy_type", "energy_above_hull"],
                    )
                ]

            self.logger.debug(f"Found for {len(thermo_docs)} Thermo Documents.")

            if len(item["ignored_species"]) != 1:
                raise ValueError(
                    "Insertion electrode can only be defined for one working ion species"
                )

            working_ion_doc = get_working_ion_entry(item["ignored_species"][0])
            return {
                "material_id": item["material_id"],
                "working_ion_doc": working_ion_doc,
                "working_ion": item["ignored_species"][0],
                "thermo_docs": thermo_docs,
            }

        yield from map(modify_item, super().get_items())

    def unary_function(self, item):
        """
        - Add volume information to each entry to create the insertion electrode document
        - Add the host structure
        """
        entries = [tdoc_["entries"][tdoc_["energy_type"]] for tdoc_ in item["thermo_docs"]]
        entries = list(map(ComputedStructureEntry.from_dict, entries))
        working_ion_entry = ComputedEntry.from_dict(
            item["working_ion_doc"]["entries"][item["working_ion_doc"]['energy_type']]
        )
        working_ion = working_ion_entry.composition.reduced_formula

        decomp_energies = {
            d_["material_id"]: d_["energy_above_hull"]
            for d_ in item["thermo_docs"]
        }

        least_wion_ent = min(
            entries, key=lambda x: x.composition.get_atomic_fraction(working_ion)
        )
        host_structure = least_wion_ent.structure.copy()
        host_structure.remove_species([item["working_ion"]])

        for ient in entries:
            ient.data["volume"] = ient.structure.volume
            ient.data["decomposition_energy"] = decomp_energies[ient.entry_id]

        ie = InsertionElectrodeDoc.from_entries(
            grouped_entries=entries,
            working_ion_entry=working_ion_entry,
            task_id=item["material_id"],
            host_structure=host_structure,
        )
        if ie is None:
            return {"failed_reason": "unable to create InsertionElectrode document"}
        return jsanitize(ie.dict())
