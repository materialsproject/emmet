import math
import operator
from collections import namedtuple
from datetime import datetime
from functools import lru_cache
from itertools import chain, groupby
from pprint import pprint
from typing import Any, Dict, Iterable, List

from maggma.builders import Builder, MapBuilder
from maggma.stores import MongoStore
from monty.json import MontyEncoder
from numpy import unique
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.core import Composition, Structure
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.electrode import InsertionElectrodeDoc
from emmet.core.structure_group import StructureGroupDoc
from emmet.core.utils import jsanitize

__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"


class GroupedThermoDocsBuilder(Builder):
    """
    Used grouped ID to fetch entries from the thermo collection
    This can be subclassed to accomplish more things with the entries
    """

    def __init__(
        self,
        grouped_materials: MongoStore,
        thermo: MongoStore,
        target: MongoStore,
        query: dict = None,
        **kwargs,
    ):
        """
        Group ThermoDocuments together
        Args:
            grouped_materials:
            thermo: The thermo collection, documents are retrieved with the "material_ids" field
            target: The target collection the key from the grouped_materials collection is mapped directly here
            query: The query to be performed on the grouped_materials collection
            **kwargs:
        """
        self.grouped_materials = grouped_materials
        self.thermo = thermo
        self.target = target
        self.query = query if query else {}

        super().__init__(
            sources=[self.grouped_materials, self.thermo],
            targets=[self.target],
            **kwargs,
        )

    def get_items(self):
        """
        Retrieve the thermo documents
        """

        def get_thermo_docs(mat_ids):
            self.logger.debug(
                f"Looking for {len(mat_ids)} material_id in the Thermo DB."
            )
            thermo_docs = list(
                self.thermo.query(
                    {
                        "$and": [
                            {"material_id": {"$in": mat_ids}},
                        ]
                    },
                    properties=[
                        "material_id",
                        "_sbxn",
                        "thermo",
                        "entries",
                        "energy_type",
                        "energy_above_hull",
                    ],
                )
            )
            self.logger.debug(f"Found for {len(thermo_docs)} Thermo Documents.")
            if len(thermo_docs) != len(mat_ids):
                missing_ids = set(mat_ids) - set(
                    [t_["material_id"] for t_ in thermo_docs]
                )
                self.logger.warn(
                    f"The following ids are missing from the entries in thermo {missing_ids}.\n"
                    "The is likely due to the fact that a calculation other than GGA or GGA+U was "
                    "validated for the materials builder."
                )
                return None
            return thermo_docs

        q_ = {"$and": [self.query, {"has_distinct_compositions": True}]}
        self.total = self.grouped_materials.count(q_)
        for group_doc in self.grouped_materials.query(q_):
            group_doc["thermo_docs"] = get_thermo_docs(group_doc["material_ids"])
            yield group_doc

    def process_item(self, item) -> Dict:
        return item

    def update_targets(self, items: List):
        items = list(filter(None, items))
        if len(items) > 0:
            self.logger.info("Updating {} documents".format(len(items)))
            for struct_group_dict in items:
                struct_group_dict[
                    self.grouped_materials.last_updated_field
                ] = datetime.utcnow()
            self.target.update(docs=items, key=self.grouped_materials.key)
        else:
            self.logger.info("No items to update")


class InsertionElectrodeBuilder(GroupedThermoDocsBuilder):
    def get_items(self):
        """
        Get items
        """

        @lru_cache(1000)
        def get_working_ion_entry(working_ion):
            with self.thermo as store:
                working_ion_docs = [*store.query({"chemsys": working_ion})]
            best_wion = min(working_ion_docs, key=lambda x: x["energy_per_atom"])
            return best_wion

        for item in super().get_items():
            item["working_ion_doc"] = get_working_ion_entry(item["ignored_species"][0])
            item["working_ion"] = item["ignored_species"][0]
            yield item

    def process_item(self, item) -> Dict:
        """
        - Add volume information to each entry to create the insertion electrode document
        - Add the host structure
        """
        if item["thermo_docs"] is None:
            return None

        self.logger.debug(
            f"Working on {item['group_id']} with {len(item['thermo_docs'])}"
        )

        entries = [
            tdoc_["entries"][tdoc_["energy_type"]] for tdoc_ in item["thermo_docs"]
        ]
        entries = list(map(ComputedStructureEntry.from_dict, entries))

        working_ion_entry = ComputedEntry.from_dict(
            item["working_ion_doc"]["entries"][item["working_ion_doc"]["energy_type"]]
        )
        working_ion = working_ion_entry.composition.reduced_formula

        decomp_energies = {
            d_["material_id"]: d_["energy_above_hull"] for d_ in item["thermo_docs"]
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
            battery_id=item["group_id"],
            host_structure=host_structure,
        )
        if ie is None:
            return None  # {"failed_reason": "unable to create InsertionElectrode document"}
        return jsanitize(ie.dict())

    def update_targets(self, items: List):
        items = list(filter(None, items))
        if len(items) > 0:
            self.logger.info("Updating {} battery documents".format(len(items)))
            for struct_group_dict in items:
                struct_group_dict[
                    self.grouped_materials.last_updated_field
                ] = datetime.utcnow()
            self.insertion_electrode.update(docs=items, key=["battery_id"])
        else:
            self.logger.info("No items to update")


class MigrationGraphBuilder(InsertionElectrodeBuilder):
    def process_item(self, item) -> Dict:
        pass
