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
from pymatgen.entries.computed_entries import ComputedStructureEntry

__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"

from pymatgen.entries.computed_entries import ComputedEntry


def s_hash(el):
    return el.data["comp_delith"]


# MatDoc = namedtuple("MatDoc", ["material_id", "structure", "formula_pretty", "framework"])

REDOX_ELEMENTS = [
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Nb",
    "Mo",
    "Sn",
    "Sb",
    "W",
    "Re",
    "Bi",
    "C",
    "Hf",
]

# WORKING_IONS = ["Li", "Be", "Na", "Mg", "K", "Ca", "Rb", "Sr", "Cs", "Ba"]

MAT_PROPS = [
    "structure",
    "material_id",
    "formula_pretty",
]

sg_fields = ["number", "hall_number", "international", "hall", "choice"]


def generic_groupby(list_in, comp=operator.eq):
    """
    Group a list of unsortable objects
    Args:
        list_in: A list of generic objects
        comp: (Default value = operator.eq) The comparator
    Returns:
        [int] list of labels for the input list
    """
    list_out = [None] * len(list_in)
    label_num = 0
    for i1, ls1 in enumerate(list_out):
        if ls1 is not None:
            continue
        list_out[i1] = label_num
        for i2, ls2 in list(enumerate(list_out))[i1 + 1 :]:
            if comp(list_in[i1], list_in[i2]):
                if list_out[i2] is None:
                    list_out[i2] = list_out[i1]
                else:
                    list_out[i1] = list_out[i2]
                    label_num -= 1
        label_num += 1
    return list_out


class StructureGroupBuilder(Builder):
    def __init__(
        self,
        materials: MongoStore,
        sgroups: MongoStore,
        working_ion: str,
        query: dict = None,
        ltol: float = 0.2,
        stol: float = 0.3,
        angle_tol: float = 5.0,
        check_newer: bool = True,
        **kwargs,
    ):
        """
        Aggregate materials entries into sgroups that are topotactically similar to each other.
        This is an incremental builder that makes ensures that each materials id belongs to one StructureGroupDoc document
        Args:
            materials (Store): Store of materials documents that contains the structures
            sgroups (Store): Store of grouped material ids
            query (dict): dictionary to limit materials to be analyzed ---
                            only applied to the materials when we need to group structures
                            the phase diagram is still constructed with the entire set
        """
        self.materials = materials
        self.sgroups = sgroups
        self.working_ion = working_ion
        self.query = query if query else {}
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.check_newer = check_newer
        super().__init__(sources=[materials], targets=[sgroups], **kwargs)

    def prechunk(self, number_splits: int) -> Iterable[Dict]:
        """
        TODO can implement this for distributed runs by adding filters
        """
        pass

    def get_items(self):
        """
        Summary of the steps:
        - query the materials database for different chemical systems that satisfies the base query
          "contains redox element and working ion"
        - Get the full chemsys list of interest
        - The main loop is over all these chemsys.  within the main loop:
            - get newest timestamp for the material documents (max_mat_time)
            - get the oldest timestamp for the target documents (min_target_time)
            - if min_target_time is < max_mat_time then nuke all the target documents
        """

        # All potentially interesting chemsys must contain the working ion
        base_query = {
            "$and": [
                {"elements": {"$in": REDOX_ELEMENTS + [self.working_ion]}},
                self.query.copy(),
            ]
        }
        self.logger.debug(f"Initial Chemsys QUERY: {base_query}")

        # get a chemsys that only contains the working ion since the working ion
        # must be present for there to be voltage steps
        all_chemsys = self.materials.distinct("chemsys", criteria=base_query)
        # Contains the working ion but not ONLY the working ion
        all_chemsys = [
            *filter(
                lambda x: self.working_ion in x and len(x) > 1,
                [chemsys_.split("-") for chemsys_ in all_chemsys],
            )
        ]

        self.logger.debug(
            f"Performing initial checks on {len(all_chemsys)} chemical systems containing redox elements with or without the Working Ion."
        )
        self.total = len(all_chemsys)

        for chemsys_l in all_chemsys:
            chemsys = "-".join(sorted(chemsys_l))
            chemsys_wo = "-".join(sorted(set(chemsys_l) - {self.working_ion}))
            chemsys_query = {
                "$and": [
                    {"chemsys": {"$in": [chemsys_wo, chemsys]}},
                    self.query.copy(),
                ]
            }
            self.logger.debug(f"QUERY: {chemsys_query}")
            all_mats_in_chemsys = list(
                self.materials.query(
                    criteria=chemsys_query,
                    properties=MAT_PROPS + [self.materials.last_updated_field],
                )
            )
            self.logger.debug(
                f"Found {len(all_mats_in_chemsys)} materials in {chemsys_wo}"
            )
            if self.check_newer:
                all_target_docs = list(
                    self.sgroups.query(
                        criteria={"chemsys": chemsys},
                        properties=[
                            "material_id",
                            self.sgroups.last_updated_field,
                            "grouped_ids",
                        ],
                    )
                )
                self.logger.debug(
                    f"Found {len(all_target_docs)} Grouped documents in {chemsys_wo}"
                )

                mat_times = [
                    mat_doc[self.materials.last_updated_field]
                    for mat_doc in all_mats_in_chemsys
                ]
                max_mat_time = max(mat_times, default=datetime.min)
                self.logger.debug(
                    f"The newest material doc was generated at {max_mat_time}."
                )

                target_times = [
                    g_doc[self.materials.last_updated_field]
                    for g_doc in all_target_docs
                ]
                min_target_time = min(target_times, default=datetime.max)
                self.logger.debug(
                    f"The newest GROUP doc was generated at {min_target_time}."
                )

                mat_ids = set(
                    [mat_doc["material_id"] for mat_doc in all_mats_in_chemsys]
                )

                # If any material id is missing or if any material id has been updated
                target_mat_ids = set()
                for g_doc in all_target_docs:
                    target_mat_ids |= set(g_doc["grouped_ids"])

                self.logger.debug(
                    f"There are {len(mat_ids)} material ids in the source database vs {len(target_mat_ids)} in the target database."
                )
                if mat_ids == target_mat_ids and max_mat_time < min_target_time:
                    continue
                else:
                    self.logger.info(
                        f"Nuking all {len(target_mat_ids)} documents in chemsys {chemsys} in the target database."
                    )
                    self._remove_targets(list(target_mat_ids))

            yield {"chemsys": chemsys, "materials": all_mats_in_chemsys}

    def update_targets(self, items: List):
        items = list(filter(None, chain.from_iterable(items)))
        if len(items) > 0:
            self.logger.info("Updating {} sgroups documents".format(len(items)))
            for struct_group_dict in items:
                struct_group_dict[self.sgroups.last_updated_field] = datetime.utcnow()
            self.sgroups.update(docs=items, key=["material_id"])
        else:
            self.logger.info("No items to update")

    def _entry_from_mat_doc(self, mdoc):
        # Note since we are just structure grouping we don't need to be careful with energy or correction
        # All of the energy analysis is left to other builders
        d_ = {
            "entry_id": mdoc["material_id"],
            "structure": mdoc["structure"],
            "energy": -math.inf,
            "correction": -math.inf,
        }
        return ComputedStructureEntry.from_dict(d_)

    def process_item(self, item: Any) -> Any:
        entries = [*map(self._entry_from_mat_doc, item["materials"])]
        s_groups = StructureGroupDoc.from_ungrouped_structure_entries(
            entries=entries,
            ignored_species=[self.working_ion],
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
        )
        # append the working_ion to the group ids
        for sg in s_groups:
            sg.material_id = f"{sg.material_id}_{self.working_ion}"
        return [sg.dict() for sg in s_groups]

    def _remove_targets(self, rm_ids):
        self.sgroups.remove_docs({"material_id": {"$in": rm_ids}})


class InsertionElectrodeBuilder(MapBuilder):
    def __init__(
        self,
        grouped_materials: MongoStore,
        insertion_electrode: MongoStore,
        thermo: MongoStore,
        material: MongoStore,
        query: dict = None,
        **kwargs,
    ):
        self.grouped_materials = grouped_materials
        self.insertion_electrode = insertion_electrode
        self.thermo = thermo
        self.material = material
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

        @lru_cache(None)
        def get_working_ion_entry(working_ion):
            with self.thermo as store:
                working_ion_docs = [*store.query({"chemsys": working_ion})]
            best_wion = min(
                working_ion_docs, key=lambda x: x["thermo"]["energy_per_atom"]
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
                        properties=["material_id", "_sbxn", "thermo"],
                    )
                ]

            with self.material as store:
                material_docs = [
                    *store.query(
                        {
                            "$and": [
                                {"material_id": {"$in": item["grouped_ids"]}},
                                {"_sbxn": {"$in": ["core"]}},
                            ]
                        },
                        properties=["material_id", "structure"],
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
                "material_docs": material_docs,
            }

        yield from map(modify_item, super().get_items())

    def unary_function(self, item):
        """
        - Add volume information to each entry to create the insertion electrode document
        - Add the host structure
        """
        entries = [tdoc_["thermo"]["entry"] for tdoc_ in item["thermo_docs"]]
        entries = list(map(ComputedEntry.from_dict, entries))
        working_ion_entry = ComputedEntry.from_dict(
            item["working_ion_doc"]["thermo"]["entry"]
        )
        working_ion = working_ion_entry.composition.reduced_formula
        decomp_energies = {
            d_["material_id"]: d_["thermo"]["e_above_hull"]
            for d_ in item["thermo_docs"]
        }
        mat_structures = {
            mat_d_["material_id"]: Structure.from_dict(mat_d_["structure"])
            for mat_d_ in item["material_docs"]
        }

        least_wion_ent = min(
            entries, key=lambda x: x.composition.get_atomic_fraction(working_ion)
        )
        mdoc_ = next(
            filter(
                lambda x: x["material_id"] == least_wion_ent.entry_id,
                item["material_docs"],
            )
        )
        host_structure = Structure.from_dict(mdoc_["structure"])
        host_structure.remove_species([item["working_ion"]])

        for ient in entries:
            if mat_structures[ient.entry_id].composition != ient.composition:
                raise RuntimeError(
                    f"In {item['material_id']}: the compositions for task {ient.entry_id} are matched "
                    "between the StructureGroup DB and the Thermo DB "
                )
            ient.data["volume"] = mat_structures[ient.entry_id].volume
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
