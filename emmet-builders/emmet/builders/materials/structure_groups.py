import operator
import math
from datetime import datetime
from itertools import chain
from typing import Iterable, Dict, List, Any

from emmet.core.structure_group import StructureGroupDoc
from maggma.builders import Builder
from maggma.stores import MongoStore
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


