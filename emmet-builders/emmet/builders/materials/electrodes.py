import operator
from collections import namedtuple
from datetime import datetime
from functools import lru_cache
from itertools import groupby, chain
from typing import Iterable, Dict, List, Any

from maggma.builders import Builder, MapBuilder
from maggma.stores import MongoStore
from numpy import unique
from pymatgen import Composition
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.core import Structure

__author__ = "Jimmy Shen"
__email__ = "jmmshn@lbl.gov"

from pymatgen.entries.computed_entries import ComputedEntry


def s_hash(el):
    return el.data["comp_delith"]


MatDoc = namedtuple("MatDoc", ["task_id", "structure", "formula_pretty", "framework"])

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

MAT_PROPS = [
    "structure",
    "task_id",
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
        groups: MongoStore,
        working_ion: str,
        query: dict = None,
        ltol: float = 0.2,
        stol: float = 0.3,
        angle_tol: float = 5.0,
        check_newer: bool = True,
        **kwargs,
    ):
        """
        Calculates physical parameters of battery materials the battery entries using
        groups of ComputedStructureEntry and the entry for the most stable version of the working_ion in the system
        Args:
            materials (Store): Store of materials documents that contains the structures
            groups (Store): Store of grouped material ids
            query (dict): dictionary to limit materials to be analyzed ---
                            only applied to the materials when we need to group structures
                            the phase diagram is still constructed with the entire set
        """
        self.materials = materials
        self.groups = groups
        self.working_ion = working_ion
        self.query = query if query else {}
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.check_newer = check_newer
        super().__init__(sources=[materials], targets=[groups], **kwargs)

    def prechunk(self, number_splits: int) -> Iterable[Dict]:
        """
        Only used in distributed runs
        """
        pass

    def get_items(self):
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
                "chemsys": {"$in": [chemsys_wo, chemsys]},
                "_sbxn": {"$in": ["core"]},
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
                    self.groups.query(
                        criteria=chemsys_query,
                        properties=[
                            "task_id",
                            self.groups.last_updated_field,
                            "grouped_task_ids",
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

                mat_ids = set([mat_doc["task_id"] for mat_doc in all_mats_in_chemsys])

                # If any material id is missing or if any material id has been updated
                target_mat_ids = set()
                for g_doc in all_target_docs:
                    target_mat_ids |= set(g_doc["grouped_task_ids"])

                self.logger.debug(
                    f"There are {len(mat_ids)} material ids in the source database vs {len(target_mat_ids)} in the target database."
                )
                if mat_ids == target_mat_ids and max_mat_time < min_target_time:
                    yield None
                    continue
            yield {"chemsys": chemsys, "materials": all_mats_in_chemsys}

    def update_targets(self, items: List):
        items = list(filter(None, chain.from_iterable(items)))
        if len(items) > 0:
            self.logger.info("Updating {} groups documents".format(len(items)))
            for k in items:
                k[self.groups.last_updated_field] = datetime.utcnow()
            self.groups.update(docs=items, key=["task_id"])
        else:
            self.logger.info("No items to update")

    def process_item(self, item: Any) -> Any:
        if item is None:
            return item

        def get_framework(formula):
            dd_ = Composition(formula).as_dict()
            if self.working_ion in dd_:
                dd_.pop(self.working_ion)
            return Composition.from_dict(dd_).reduced_formula

        sm = StructureMatcher(
            comparator=ElementComparator(),
            primitive_cell=True,
            ignored_species=[self.working_ion],
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
        )

        # Convert the material documents for easier grouping
        mat_docs = [
            MatDoc(
                task_id=mat_doc["task_id"],
                structure=Structure.from_dict(mat_doc["structure"]),
                formula_pretty=mat_doc["formula_pretty"],
                framework=get_framework(mat_doc["formula_pretty"]),
            )
            for mat_doc in item["materials"]
        ]

        def get_doc_from_group(group, structure_matched=True):
            """
            Create a results document from macthed or unmatched groups
            """
            different_comps = set([ts_.formula_pretty for ts_ in group])
            if not structure_matched or (
                structure_matched and len(different_comps) > 1
            ):
                ids = [ts_.task_id for ts_ in group]
                formulas = {ts_.task_id: ts_.formula_pretty for ts_ in group}
                entry_data = {
                    ts_.task_id: {
                        "composition": ts_.structure.composition.as_dict(),
                        "volume": ts_.structure.volume,
                    }
                    for ts_ in group
                }
                lowest_id = sorted(ids, key=get_id_num)[0]

                return {
                    "task_id": f"{lowest_id}_{self.working_ion}",
                    "structure_matched": structure_matched,
                    "has_distinct_compositions": len(different_comps) > 1,
                    "grouped_task_ids": ids,
                    "formulas": formulas,
                    "entry_data": entry_data,
                    "framework": framework,
                    "working_ion": self.working_ion,
                    "chemsys": item["chemsys"],
                }
            return None

        results = []
        # must sort before grouping
        mat_docs.sort(key=lambda x: x.framework)
        framework_groups = groupby(mat_docs, key=lambda x: x.framework)

        frame_group_cnt_ = 0
        for framework, f_group in framework_groups:
            f_group_l = list(f_group)
            self.logger.debug(
                f"Performing structure matching for {framework} with {len(f_group_l)} documents."
            )
            ungrouped_structures = []
            g_cnt = 0
            for g in self._group_struct(f_group_l, sm):
                res_doc = get_doc_from_group(g, structure_matched=True)
                if res_doc is not None:
                    self.logger.debug(
                        f"These ids were grouped {res_doc.get('grouped_task_ids', None)}"
                    )
                    frame_group_cnt_ += len(res_doc["grouped_task_ids"])
                    results.append(res_doc)
                else:
                    ungrouped_structures.extend(g)
            self.logger.debug(
                f"These ids were ungrouped {[_.task_id for _ in ungrouped_structures]}"
            )
            self.logger.debug(
                f"Created {g_cnt} groups with {len(ungrouped_structures)} remaining unmatched"
            )

            if ungrouped_structures:
                frame_group_cnt_ += len(ungrouped_structures)
                results.append(
                    get_doc_from_group(ungrouped_structures, structure_matched=False)
                )

        self.logger.debug(
            f"Total number of materials ids processed: {frame_group_cnt_}"
        )
        if frame_group_cnt_ != len(mat_docs):
            raise RuntimeError(
                "The number of procssed IDs at the end does not match the number of supplied materials documents."
                "Something is seriously wrong, please rebuild the entire database and see if the problem persists."
            )
        return results

    def _group_struct(self, g, sm):
        """
        group the entries together based on similarity of the delithiated primitive cells
        Args:
            g: a list of entries
        Returns:
            subgroups: subgroups that are grouped together based on structure
        """
        labs = generic_groupby(
            g, comp=lambda x, y: sm.fit(x.structure, y.structure, symmetric=True)
        )
        for ilab in unique(labs):
            sub_g = [g[itr] for itr, jlab in enumerate(labs) if jlab == ilab]
            yield [el for el in sub_g]

    def _host_comp(self, formula):
        dd_ = Composition(formula).as_dict()
        if self.working_ion in dd_:
            dd_.pop(self.working_ion)
        return Composition.from_dict(dd_).reduced_formula

    def _get_simlar_formula_in_group(self, formula_group):
        for k, g in groupby(formula_group, self._host_comp):
            yield list(g)  # Store group iterator as a list


class InsertionElectrodeBuilder(MapBuilder):
    def __init__(
        self,
        grouped_materials: MongoStore,
        insertion_electrode: MongoStore,
        thermo: MongoStore,
        material: MongoStore,
        **kwargs,
    ):
        self.grouped_materials = grouped_materials
        self.insertion_electrode = insertion_electrode
        self.thermo = thermo
        self.material = material
        super().__init__(
            source=self.grouped_materials,
            target=self.insertion_electrode,
            query={"structure_matched": True, "has_distinct_compositions": True},
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
                f"Looking for {len(item['grouped_task_ids'])} task_ids in the Thermo DB."
            )
            with self.thermo as store:
                thermo_docs = [
                    *store.query(
                        {
                            "$and": [
                                {"task_id": {"$in": item["grouped_task_ids"]}},
                                {"_sbxn": {"$in": ["core"]}},
                            ]
                        },
                        properties=["task_id", "_sbxn", "thermo"],
                    )
                ]

            with self.material as store:
                material_docs = [
                    *store.query(
                        {
                            "$and": [
                                {"task_id": {"$in": item["grouped_task_ids"]}},
                                {"_sbxn": {"$in": ["core"]}},
                            ]
                        },
                        properties=["task_id", "structure"],
                    )
                ]

            self.logger.debug(f"Found for {len(thermo_docs)} Thermo Documents.")
            working_ion_doc = get_working_ion_entry(item["working_ion"])
            return {
                "task_id": item["task_id"],
                "working_ion_doc": working_ion_doc,
                "entry_data": item["entry_data"],
                "thermo_docs": thermo_docs,
                "material_docs": material_docs,
            }

        yield from map(modify_item, super().get_items())

    def unary_function(self, item):
        """
        - Add volume information to each entry to create the insertion electrode document
        - Add the host structure
        - TODO parse the structures in the different materials documents and create a simple migration graph
        """
        entries = [tdoc_["thermo"]["entry"] for tdoc_ in item["thermo_docs"]]
        entries = list(map(ComputedEntry.from_dict, entries))
        working_ion_entry = ComputedEntry.from_dict(
            item["working_ion_doc"]["thermo"]["entry"]
        )
        working_ion = working_ion_entry.composition.reduced_formula
        decomp_energies = {
            d_["task_id"]: d_["thermo"]["e_above_hull"] for d_ in item["thermo_docs"]
        }
        for ient in entries:
            if (
                Composition(item["entry_data"][ient.entry_id]["composition"])
                != ient.composition
            ):
                raise RuntimeError(
                    f"In {item['task_id']}: the compositions for task {ient.entry_id} are matched between the StructureGroup DB and the Thermo DB "
                )
            ient.data["volume"] = item["entry_data"][ient.entry_id]["volume"]
            ient.data["decomposition_energy"] = decomp_energies[ient.entry_id]

        failed = False
        try:
            ie = InsertionElectrode.from_entries(entries, working_ion_entry)
        except:
            failed = True

        if failed or ie.num_steps < 1:
            res = {"task_id": item["task_id"], "has_step": False}
        else:
            res = {"task_id": item["task_id"], "has_step": True}
            res.update(ie.get_summary_dict())
            res["InsertionElectrode"] = ie.as_dict()
            least_wion_ent = min(
                entries, key=lambda x: x.composition.get_atomic_fraction(working_ion)
            )
            mdoc_ = next(
                filter(
                    lambda x: x["task_id"] == least_wion_ent.entry_id,
                    item["material_docs"],
                )
            )
            host_structure = Structure.from_dict(mdoc_["structure"])
            res["host_structure"] = host_structure.as_dict()
        return res


def get_id_num(task_id):
    if isinstance(task_id, int):
        return task_id
    if isinstance(task_id, str) and "-" in task_id:
        return int(task_id.split("-")[-1])
    else:
        raise ValueError("TaskID needs to be either a number or of the form xxx-#####")
