import math
import operator
from datetime import datetime
from functools import lru_cache
from itertools import chain
from math import ceil
from typing import Any, Iterator, Dict, List

from maggma.builders import Builder
from maggma.stores import MongoStore
from maggma.utils import grouper
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.electrode import InsertionElectrodeDoc
from emmet.core.structure_group import StructureGroupDoc
from emmet.core.utils import jsanitize
from emmet.builders.settings import EmmetBuildSettings


def s_hash(el):
    return el.data["comp_delith"]


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

WORKING_IONS = ["Li", "Be", "Na", "Mg", "K", "Ca", "Rb", "Sr", "Cs", "Ba"]

MAT_PROPS = ["structure", "material_id", "formula_pretty", "entries"]

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


default_build_settings = EmmetBuildSettings()


class StructureGroupBuilder(Builder):
    def __init__(
        self,
        materials: MongoStore,
        sgroups: MongoStore,
        working_ion: str,
        query: dict = None,
        ltol: float = default_build_settings.LTOL,
        stol: float = default_build_settings.STOL,
        angle_tol: float = default_build_settings.ANGLE_TOL,
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

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        all_chemsys = self.materials.distinct("chemsys", criteria=q)

        new_chemsys_list = []

        for chemsys in all_chemsys:
            elements = [
                element for element in chemsys.split("-") if element != self.working_ion
            ]
            new_chemsys = "-".join(sorted(elements))
            new_chemsys_list.append(new_chemsys)

        N = ceil(len(new_chemsys_list) / number_splits)

        for split in grouper(new_chemsys_list, N):
            new_split_add = []
            for chemsys in split:
                elements = [element for element in chemsys.split("-")] + [
                    self.working_ion
                ]
                new_chemsys = "-".join(sorted(elements))
                new_split_add.append(new_chemsys)

            yield {"query": {"chemsys": {"$in": new_split_add + split}}}

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
        other_wions = list(set(WORKING_IONS) - {self.working_ion})
        # All potentially interesting chemsys must contain the working ion
        base_query = {
            "$and": [
                self.query.copy(),
                {"elements": {"$in": REDOX_ELEMENTS}},
                {"elements": {"$in": [self.working_ion]}},
                {"elements": {"$nin": other_wions}},
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
                            "group_id",
                            self.sgroups.last_updated_field,
                            "material_ids",
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
                target_ids = set()
                for g_doc in all_target_docs:
                    target_ids |= set(g_doc["material_ids"])

                self.logger.debug(
                    f"There are {len(mat_ids)} material ids in the source database vs {len(target_ids)} in the target database."
                )
                if mat_ids == target_ids and max_mat_time < min_target_time:
                    self.logger.info(f"Skipping chemsys {chemsys}.")
                    yield None
                elif len(target_ids) == 0:
                    self.logger.info(
                        f"No documents in chemsys {chemsys} in the target database."
                    )
                    yield {"chemsys": chemsys, "materials": all_mats_in_chemsys}
                else:
                    self.logger.info(
                        f"Nuking all {len(target_ids)} documents in chemsys {chemsys} in the target database."
                    )
                    self._remove_targets(list(target_ids))
                    yield {"chemsys": chemsys, "materials": all_mats_in_chemsys}
            else:
                yield {"chemsys": chemsys, "materials": all_mats_in_chemsys}

    def update_targets(self, items: List):
        items = list(filter(None, chain.from_iterable(items)))
        if len(items) > 0:
            self.logger.info("Updating {} sgroups documents".format(len(items)))
            for struct_group_dict in items:
                struct_group_dict[self.sgroups.last_updated_field] = datetime.utcnow()
            self.sgroups.update(docs=items, key=["group_id"])
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
        if item is None:
            return None
        entries = [*map(self._entry_from_mat_doc, item["materials"])]
        s_groups = StructureGroupDoc.from_ungrouped_structure_entries(
            entries=entries,
            ignored_species=[self.working_ion],
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
        )
        return [sg.dict() for sg in s_groups]

    def _remove_targets(self, rm_ids):
        self.sgroups.remove_docs({"material_ids": {"$in": rm_ids}})


class InsertionElectrodeBuilder(Builder):
    def __init__(
        self,
        grouped_materials: MongoStore,
        thermo: MongoStore,
        insertion_electrode: MongoStore,
        query: dict = None,
        **kwargs,
    ):
        self.grouped_materials = grouped_materials
        self.insertion_electrode = insertion_electrode
        self.thermo = thermo
        self.query = query if query else {}

        super().__init__(
            sources=[self.grouped_materials, self.thermo],
            targets=[self.insertion_electrode],
            **kwargs,
        )

    def prechunk(self, number_splits: int) -> Iterator[Dict]:
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.grouped_materials.distinct(self.grouped_materials.key, criteria=q)

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.grouped_materials.key: {"$in": list(split)}}}

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

        def get_thermo_docs(mat_ids):
            self.logger.debug(
                f"Looking for {len(mat_ids)} material_id in the Thermo DB."
            )
            thermo_docs = list(
                self.thermo.query(
                    {"$and": [{"material_id": {"$in": mat_ids}}]},
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

            # if len(item["ignored_species"]) != 1:
            #     raise ValueError(
            #         "Insertion electrode can only be defined for one working ion species"
            #     )

            return thermo_docs
            # return {
            #     "group_id": item["group_id"],
            #     "working_ion_doc": working_ion_doc,
            #     "working_ion": item["ignored_species"][0],
            #     "thermo_docs": thermo_docs,
            # }

        q_ = {"$and": [self.query, {"has_distinct_compositions": True}]}
        self.total = self.grouped_materials.count(q_)
        for group_doc in self.grouped_materials.query(q_):
            working_ion_doc = get_working_ion_entry(group_doc["ignored_species"][0])
            thermo_docs = get_thermo_docs(group_doc["material_ids"])
            if thermo_docs:
                yield {
                    "group_id": group_doc["group_id"],
                    "working_ion_doc": working_ion_doc,
                    "working_ion": group_doc["ignored_species"][0],
                    "thermo_docs": thermo_docs,
                }
            else:
                yield None

    def process_item(self, item) -> Dict:
        """
        - Add volume information to each entry to create the insertion electrode document
        - Add the host structure
        """
        if item is None:
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

        decomp_energies = {
            d_["material_id"]: d_["energy_above_hull"] for d_ in item["thermo_docs"]
        }

        for ient in entries:
            ient.data["volume"] = ient.structure.volume
            ient.data["decomposition_energy"] = decomp_energies[ient.entry_id]

        ie = InsertionElectrodeDoc.from_entries(
            grouped_entries=entries,
            working_ion_entry=working_ion_entry,
            battery_id=item["group_id"],
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
