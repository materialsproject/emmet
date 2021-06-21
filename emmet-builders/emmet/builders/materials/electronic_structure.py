from collections import defaultdict
from math import ceil

import numpy as np
from maggma.builders import Builder
from maggma.utils import grouper
from pymatgen.analysis.magnetism.analyzer import CollinearMagneticStructureAnalyzer
from pymatgen.core import Structure
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.bandstructure import HighSymmKpath

from emmet.core import SETTINGS
from emmet.core.electronic_structure import ElectronicStructureDoc
from emmet.core.utils import jsanitize


class ElectronicStructureBuilder(Builder):
    def __init__(
        self,
        tasks,
        materials,
        electronic_structure,
        bandstructure_fs,
        dos_fs,
        chunk_size=10,
        query=None,
        **kwargs
    ):
        """
        Creates an electronic structure collection from a tasks collection,
        the associated band structures and density of states file store collections,
        and the materials collection.

        Individual bandstructures for each of the three conventions are generated.

        tasks (Store): Store of task documents
        materials (Store): Store of materials documents
        electronic_structure (Store): Store of electronic structure summary data documents
        bandstructure_fs (Store): Store of bandstructures
        dos_fs (Store): Store of DOS
        chunk_size (int): Chunk size to use for processing. Defaults to 10.
        query (dict): Dictionary to limit materials to be analyzed
        """

        self.tasks = tasks
        self.materials = materials
        self.electronic_structure = electronic_structure
        self.bandstructure_fs = bandstructure_fs
        self.dos_fs = dos_fs
        self.chunk_size = chunk_size
        self.query = query if query else {}

        super().__init__(
            sources=[tasks, materials, bandstructure_fs, dos_fs],
            targets=[electronic_structure],
            chunk_size=chunk_size,
            **kwargs,
        )

    def prechunk(self, number_splits: int):
        """
        Prechunk method to perform chunking by the key field
        """
        q = dict(self.query)

        keys = self.electronic_structure.newer_in(
            self.materials, criteria=q, exhaustive=True
        )

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.materials.key: {"$in": list(split)}}}

    def get_items(self):
        """
        Gets all items to process

        Returns:
            generator or list relevant tasks and materials to process
        """

        self.logger.info("Electronic Structure Builder Started")

        q = dict(self.query)

        mat_ids = self.materials.distinct(self.materials.key, criteria=q)
        es_ids = self.electronic_structure.distinct(self.electronic_structure.key)

        mats_set = set(
            self.electronic_structure.newer_in(
                target=self.materials, criteria=q, exhaustive=True
            )
        ) | (set(mat_ids) - set(es_ids))

        mats = [mat for mat in mats_set]

        self.logger.info(
            "Processing {} materials for electronic structure".format(len(mats))
        )

        self.total = len(mats)

        for mat in mats:
            mat = self._update_materials_doc(mat)
            yield mat

    def process_item(self, mat):
        """
        Process the band structures and dos data.

        Args:
            mat (dict): material document

        Returns:
            (dict): electronic_structure document
        """

        structure = Structure.from_dict(mat["structure"])

        self.logger.info("Processing: {}".format(mat[self.materials.key]))

        dos = None
        bs = {}
        structures = {}

        for bs_type, bs_entry in mat["bandstructure"].items():
            if bs_entry.get("object", None) is not None:
                bs[bs_type] = (
                    {
                        bs_entry["task_id"]: BandStructureSymmLine.from_dict(
                            bs_entry["object"]
                        )
                    }
                    if bs_entry
                    else None
                )

                structures[bs_entry["task_id"]] = bs_entry["output_structure"]

        if mat["dos"]:
            if mat["dos"]["object"] is not None:
                self.logger.info("Processing density of states")
                dos = {
                    mat["dos"]["task_id"]: CompleteDos.from_dict(mat["dos"]["object"])
                }

                structures[mat["dos"]["task_id"]] = mat["dos"]["output_structure"]

        if bs:
            self.logger.info(
                "Processing band structure types: {}".format(
                    [bs_type for bs_type, bs_entry in bs.items() if bs_entry]
                )
            )

        if dos is None:
            doc = ElectronicStructureDoc.from_structure(
                material_id=mat[self.materials.key],
                task_id=mat["other"]["task_id"],
                structure=structure,
                band_gap=mat["other"]["band_gap"],
                cbm=mat["other"]["cbm"],
                vbm=mat["other"]["vbm"],
                efermi=mat["other"]["efermi"],
                is_gap_direct=mat["other"]["is_gap_direct"],
                is_metal=mat["other"]["is_metal"],
                magnetic_ordering=mat["other"]["magnetic_ordering"],
            )
        else:
            doc = ElectronicStructureDoc.from_bsdos(
                material_id=mat[self.materials.key],
                structures=structures,
                dos=dos,
                is_gap_direct=mat["other"]["is_gap_direct"],
                is_metal=mat["other"]["is_metal"],
                **bs,
            )

            bgap_diff = []
            for bs_type, bs_summary in doc.bandstructure:
                if bs_summary is not None:
                    bgap_diff.append(doc.band_gap - bs_summary.band_gap)

            if any(abs(gap) > 0.25 for gap in bgap_diff):
                if doc.warnings is None:
                    doc.warnings = []
                doc.warnings.append(
                    "Absolute difference between blessed band gap and at least one\
                    line-mode calculation band gap is larger than 0.25 eV."
                )

        return doc.dict()

    def update_targets(self, items):
        """
        Inserts electronic structure documents into the electronic_structure collection

        Args:
            items ([Dict]): A list of ElectronicStructureDoc dictionaries to update
        """

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} electronic structure docs".format(len(items)))
            self.electronic_structure.update(docs=jsanitize(items, allow_bson=True))
        else:
            self.logger.info("No electronic structure docs to update")

    def _update_materials_doc(self, mat_id):
        # find bs type for each task in task_type and store each different bs object

        mat = self.materials.query_one(
            properties=[
                self.materials.key,
                "structure",
                "inputs",
                "task_types",
                self.materials.last_updated_field,
            ],
            criteria={self.materials.key: mat_id},
        )

        mat["dos"] = {}
        mat["bandstructure"] = defaultdict(dict)
        mat["other"] = {}

        bs_calcs = defaultdict(list)
        dos_calcs = []
        other_calcs = []

        for task_id in mat["task_types"].keys():

            # Handle all line-mode tasks
            if "NSCF Line" in mat["task_types"][task_id]:

                bs_type = None

                task_query = self.tasks.query_one(
                    properties=[
                        "calcs_reversed",
                        "last_updated",
                        "input.is_hubbard",
                        "orig_inputs.kpoints",
                        "input.parameters",
                        "output.structure",
                    ],
                    criteria={"task_id": str(task_id)},
                )

                fs_id = str(task_query["calcs_reversed"][0]["bandstructure_fs_id"])

                structure = Structure.from_dict(task_query["output"]["structure"])

                kpoints = task_query["orig_inputs"]["kpoints"]
                labels_dict = {
                    label: point
                    for label, point in zip(kpoints["labels"], kpoints["kpoints"])
                    if label is not None
                }

                bs_type = self._obtain_path_type(labels_dict, structure)

                if bs_type is None:

                    bs_dict = self.bandstructure_fs.query_one(
                        {self.bandstructure_fs.key: str(task_id)}
                    )

                    if bs_dict is not None:

                        bs = BandStructureSymmLine.from_dict(bs_dict["data"])

                        bs_type = self._obtain_path_type(bs.labels_dict, bs.structure)

                is_hubbard = task_query["input"]["is_hubbard"]
                nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]
                lu_dt = task_query["last_updated"]

                if bs_type is not None:
                    bs_calcs[bs_type].append(
                        {
                            "fs_id": fs_id,
                            "task_id": task_id,
                            "is_hubbard": int(is_hubbard),
                            "nkpoints": int(nkpoints),
                            "updated_on": lu_dt,
                            "output_structure": structure,
                        }
                    )

            # Handle uniform tasks
            if "NSCF Uniform" in mat["task_types"][task_id]:
                task_query = self.tasks.query_one(
                    properties=[
                        "calcs_reversed",
                        "last_updated",
                        "input.is_hubbard",
                        "orig_inputs.kpoints",
                        "input.parameters",
                        "output.structure",
                    ],
                    criteria={"task_id": str(task_id)},
                )

                fs_id = str(task_query["calcs_reversed"][0]["dos_fs_id"])

                is_hubbard = task_query["input"]["is_hubbard"]

                structure = Structure.from_dict(task_query["output"]["structure"])

                if task_query["orig_inputs"]["kpoints"]["generation_style"] == "Monkhorst":
                    nkpoints = np.prod(task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0)

                else:
                    nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

                nedos = task_query["input"]["parameters"]["NEDOS"]
                lu_dt = task_query["last_updated"]

                dos_calcs.append(
                    {
                        "fs_id": fs_id,
                        "task_id": task_id,
                        "is_hubbard": int(is_hubbard),
                        "nkpoints": int(nkpoints),
                        "nedos": int(nedos),
                        "updated_on": lu_dt,
                        "output_structure": structure,
                    }
                )

            # Handle static and structure opt tasks
            if "Static" or "Structure Optimization" in mat["task_types"][task_id]:
                task_query = self.tasks.query_one(
                    properties=[
                        "last_updated",
                        "input.is_hubbard",
                        "orig_inputs.kpoints",
                        "calcs_reversed",
                        "output.structure",
                    ],
                    criteria={"task_id": str(task_id)},
                )

                structure = Structure.from_dict(task_query["output"]["structure"])

                other_mag_ordering = CollinearMagneticStructureAnalyzer(
                    structure
                ).ordering

                is_hubbard = task_query["input"]["is_hubbard"]

                last_calc = task_query["calcs_reversed"][-1]

                if last_calc["input"]["kpoints"]["generation_style"] == "Monkhorst":
                    nkpoints = np.prod(
                        last_calc["input"]["kpoints"]["kpoints"][0], axis=0
                    )
                else:
                    nkpoints = last_calc["input"]["kpoints"]["nkpoints"]

                lu_dt = task_query["last_updated"]

                other_calcs.append(
                    {
                        "is_static": True
                        if "Static" in mat["task_types"][task_id]
                        else False,
                        "task_id": task_id,
                        "is_hubbard": int(is_hubbard),
                        "nkpoints": int(nkpoints),
                        "magnetic_ordering": other_mag_ordering,
                        "updated_on": lu_dt,
                        "calcs_reversed": task_query["calcs_reversed"],
                    }
                )

        updated_materials_doc = self._obtain_blessed_calculations(
            mat, bs_calcs, dos_calcs, other_calcs
        )

        return updated_materials_doc

    def _obtain_blessed_calculations(
        self, materials_doc, bs_calcs, dos_calcs, other_calcs
    ):

        bs_types = ["setyawan_curtarolo", "hinuma", "latimer_munro"]

        for bs_type in bs_types:
            # select "blessed" bs of each type
            if bs_calcs[bs_type]:
                sorted_bs_data = sorted(
                    bs_calcs[bs_type],
                    key=lambda entry: (
                        entry["is_hubbard"],
                        entry["nkpoints"],
                        entry["updated_on"],
                    ),
                    reverse=True,
                )

                materials_doc["bandstructure"][bs_type]["task_id"] = sorted_bs_data[0][
                    "task_id"
                ]

                bs_obj = self.bandstructure_fs.query_one(
                    criteria={"fs_id": sorted_bs_data[0]["fs_id"]}
                )

                materials_doc["bandstructure"][bs_type]["object"] = (
                    bs_obj["data"] if bs_obj is not None else None
                )

                materials_doc["bandstructure"][bs_type]["output_structure"] = sorted_bs_data[0]["output_structure"]

            if dos_calcs:

                sorted_dos_data = sorted(
                    dos_calcs,
                    key=lambda entry: (
                        entry["is_hubbard"],
                        entry["nkpoints"],
                        entry["nedos"],
                        entry["updated_on"],
                    ),
                    reverse=True,
                )

                materials_doc["dos"]["task_id"] = sorted_dos_data[0]["task_id"]

                dos_obj = self.dos_fs.query_one(
                    criteria={"fs_id": sorted_dos_data[0]["fs_id"]}
                )
                materials_doc["dos"]["object"] = (
                    dos_obj["data"] if dos_obj is not None else None
                )

                materials_doc["dos"]["output_structure"] = sorted_dos_data[0]["output_structure"]

            if other_calcs:

                sorted_other_data = sorted(
                    other_calcs,
                    key=lambda entry: (
                        entry["is_static"],
                        entry["is_hubbard"],
                        entry["nkpoints"],
                        entry["updated_on"],
                    ),
                    reverse=True,
                )

                materials_doc["other"]["task_id"] = str(sorted_other_data[0]["task_id"])

                task_output_data = sorted_other_data[0]["calcs_reversed"][-1]["output"]
                materials_doc["other"]["band_gap"] = task_output_data["bandgap"]
                materials_doc["other"]["magnetic_ordering"] = sorted_other_data[0][
                    "magnetic_ordering"
                ]

                materials_doc["other"]["is_metal"] = (
                    materials_doc["other"]["band_gap"] == 0.0
                )

                for prop in ["efermi", "cbm", "vbm", "is_gap_direct", "is_metal"]:

                    # First try other calcs_reversed entries if properties are not found in last
                    if prop not in task_output_data:
                        for calc in sorted_other_data[0]["calcs_reversed"]:
                            if calc["output"].get(prop, None) is not None:
                                materials_doc["other"][prop] = calc["output"][prop]
                    else:
                        materials_doc["other"][prop] = task_output_data[prop]

        return materials_doc

    @staticmethod
    def _obtain_path_type(
        labels_dict,
        structure,
        symprec=SETTINGS.SYMPREC,
        angle_tolerance=SETTINGS.ANGLE_TOL,
        atol=1e-5,
    ):

        bs_type = None

        if any([label.islower() for label in labels_dict]):
            bs_type = "latimer_munro"
        else:
            for ptype in ["setyawan_curtarolo", "hinuma"]:
                hskp = HighSymmKpath(
                    structure,
                    has_magmoms=False,
                    magmom_axis=None,
                    path_type=ptype,
                    symprec=symprec,
                    angle_tolerance=angle_tolerance,
                    atol=atol,
                )
                hs_labels_full = hskp.kpath["kpoints"]
                hs_path_uniq = set(
                    [label for segment in hskp.kpath["path"] for label in segment]
                )

                hs_labels = {
                    k: hs_labels_full[k] for k in hs_path_uniq if k in hs_path_uniq
                }

                shared_items = {
                    k: labels_dict[k]
                    for k in labels_dict
                    if k in hs_labels
                    and np.allclose(labels_dict[k], hs_labels[k], atol=1e-3)
                }

                if len(shared_items) == len(labels_dict) and len(shared_items) == len(
                    hs_labels
                ):
                    bs_type = ptype

        return bs_type
