from collections import defaultdict
from emmet.core.electronic_structure import ElectronicStructureDoc

import numpy as np
from monty.json import jsanitize
from maggma.builders import Builder
from pymatgen.core import Structure
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.bandstructure import HighSymmKpath


__author__ = "Jason Munro <jmunro@lbl.gov>"


class ElectronicStructureBuilder(Builder):
    def __init__(
        self,
        tasks,
        materials,
        electronic_structure,
        bandstructure_fs,
        dos_fs,
        mat_chunk_size,
        query=None,
        **kwargs,
    ):
        """
        Creates an electronic structure collection from a tasks collection, 
        the associated band structures and density of states file store collections, 
        and the materials collection.

        Individual bandstructures for each of the three conventions are generated.

        tasks (Store) : Store of task documents
        materials (Store) : Store of materials documents
        electronic_structure (Store) : Store of electronic structure summary data documents
        bandstructure_fs (Store) : store of bandstructures
        dos_fs (Store) : store of DOS
        mat_chunk_size (int): Chunk size of materials to process simultaneously
        query (dict): dictionary to limit tasks to be analyzed
        """

        self.tasks = tasks
        self.materials = materials
        self.electronic_structure = electronic_structure
        self.bandstructure_fs = bandstructure_fs
        self.dos_fs = dos_fs
        self.query = query if query else {}

        super().__init__(
            sources=[tasks, materials, bandstructure_fs, dos_fs],
            targets=[electronic_structure],
            **kwargs,
        )

    def get_items(self):
        """
        Gets all items to process

        Returns:
            generator or list relevant tasks and materials to process
        """

        self.logger.info("Electronic Structure Builder Started")

        # get all materials that were updated since the electronic structure was last updated
        q = dict(self.query)

        mat_ids = list(self.materials.distinct(self.materials.key, criteria=q))
        es_ids = self.electronic_structure.distinct(self.electronic_structure.key)

        mats_set = set(
            self.electronic_structure.newer_in(target=self.materials, exhaustive=True)
        ) | (set(mat_ids) - set(es_ids))

        mats = [mat for mat in mats_set]

        mat_chunk_size = 10

        mats_chunked = [
            mats[i : i + mat_chunk_size] for i in range(0, len(mats), mat_chunk_size)
        ]

        self.logger.debug(
            "Processing {} materials for electronic structure".format(len(mats))
        )

        self.total = len(mats_chunked)

        for chunk in mats_chunked:
            self.logger.debug("Handling materials: {}".format(chunk))
            mats = self._update_mat(chunk)
            yield mats

    def process_item(self, mats):
        """
        Process the band structures and dos data.

        Args:
            mat (dict): material document

        Returns:
            (dict): electronic_structure document
        """

        d_list = []

        for mat in mats:

            structure = Structure.from_dict(mat["structure"])

            self.logger.info("Processing: {}".format(mat[self.materials.key]))

            dos = None
            bs = {}

            for bs_type, bs_entry in mat["bandstructure"].items():
                bs[bs_type] = (
                    {
                        bs_entry["task_id"]: BandStructureSymmLine.from_dict(
                            bs_entry["object"]
                        )
                    }
                    if bs_entry
                    else None
                )

            if mat["dos"]:
                self.logger.info("Processing density of states")
                dos = {mat["dos"]["task_id"]: CompleteDos.from_dict(mat["dos"]["data"])}

            self.logger.info(
                "Processing band structure types: {}".format(
                    [bs_type for bs_type, bs_entry in bs.items() if bs_entry]
                )
            )

            if dos is None:
                doc = ElectronicStructureDoc(
                    material_id=mat[self.materials.key],
                    calc_id=mat["other"]["task_id"],
                    structure=structure,
                    band_gap=mat["other"]["band_gap"],
                    cbm=mat["other"]["cbm"],
                    vbm=mat["other"]["vbm"],
                    efermi=mat["other"]["efermi"],
                    is_gap_direct=mat["other"]["is_gap_direct"],
                    is_metal=mat["other"]["is_metal"],
                )
            else:
                doc = ElectronicStructureDoc.from_bsdos(
                    material_id=mat[self.materials.key],
                    structure=structure,
                    dos=dos,
                    setyawan_curtarolo=bs["setyawan_curtarolo"],
                    hinuma=bs["hinuma"],
                    latimer_munro=bs["latimer_munro"],
                )

            d_list.append(doc)

        return d_list

    def update_targets(self, items):
        """
        Inserts electronic structure documents into the electronic_structure collection

        Args:
            items ([ElectronicStructureDoc]): A list of ElectronicStructureDoc objects to update
        """
        items = list(filter(None, items))[0]

        if len(items) > 0:
            self.logger.info("Updating {} electronic structure docs".format(len(items)))

            for item in items:
                self.electronic_structure.update(jsanitize(item.dict()))
        else:
            self.logger.info("No electronic structure docs to update")

    def _update_mat(self, mat_list):
        # find bs type for each task in task_type and store each different bs object

        mats = self.materials.query(
            properties=[
                self.materials.key,
                "structure",
                "inputs",
                "task_types",
                self.materials.last_updated_field,
            ],
            criteria={self.materials.key: {"$in": mat_list}},
        )

        mats_updated = []

        for mat in mats:

            mat["dos"] = {}
            mat["bandstructure"] = {
                "setyawan_curtarolo": {},
                "hinuma": {},
                "latimer_munro": {},
            }
            mat["other"] = {}

            seen_bs_data = defaultdict(list)
            seen_dos_data = []
            seen_other_data = []

            for task_id in mat["task_types"].keys():

                # Handle all line-mode tasks
                try:
                    if "NSCF Line" in mat["task_types"][task_id]:

                        bs_type = None

                        task_query = self.tasks.query_one(
                            properties=[
                                "last_updated",
                                "input.is_hubbard",
                                "orig_inputs.kpoints",
                                "input.structure",
                            ],
                            criteria={"task_id": str(task_id)},
                        )

                        structure = Structure.from_dict(
                            task_query["input"]["structure"]
                        )

                        kpoints = task_query["orig_inputs"]["kpoints"]
                        labels_dict = {
                            label: point
                            for label, point in zip(
                                kpoints["labels"], kpoints["kpoints"]
                            )
                            if label is not None
                        }

                        bs_type = self._obtain_path_type(labels_dict, structure)

                        if bs_type is None:
                            bs_dict = self.bandstructure_fs.query_one(
                                {"self.bandstructure_fs.key": str(task_id)}
                            )["data"]

                            bs = BandStructureSymmLine.from_dict(bs_dict)

                            bs_type = self._obtain_path_type(
                                bs.labels_dict, bs.structure
                            )

                        is_hubbard = task_query["input"]["is_hubbard"]
                        nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]
                        lu_dt = task_query["last_updated"]

                        if bs_type is not None:
                            seen_bs_data[bs_type].append(
                                {
                                    "task_id": str(task_id),
                                    "is_hubbard": int(is_hubbard),
                                    "nkpoints": int(nkpoints),
                                    "updated_on": lu_dt,
                                }
                            )
                except Exception:
                    self.logger.info(
                        "Problem processing calculation with id {}".format(task_id)
                    )
                    pass

                # Handle uniform tasks
                if "NSCF Uniform" in mat["task_types"][task_id]:
                    task_query = self.tasks.query_one(
                        properties=[
                            "last_updated",
                            "input.is_hubbard",
                            "orig_inputs.kpoints",
                        ],
                        criteria={"task_id": str(task_id)},
                    )

                    is_hubbard = task_query["input"]["is_hubbard"]

                    if (
                        task_query["orig_inputs"]["kpoints"]["generation_style"]
                        == "Monkhorst"
                    ):
                        nkpoints = np.prod(
                            task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0
                        )
                    else:
                        nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

                    lu_dt = task_query["last_updated"]

                    seen_dos_data.append(
                        {
                            "task_id": str(task_id),
                            "is_hubbard": int(is_hubbard),
                            "nkpoints": int(nkpoints),
                            "updated_on": lu_dt,
                        }
                    )

                # Handle uniform tasks
                if "Static" or "Structure Optimization" in mat["task_types"][task_id]:
                    task_query = self.tasks.query_one(
                        properties=[
                            "last_updated",
                            "input.is_hubbard",
                            "orig_inputs.kpoints",
                            "calcs_reversed",
                        ],
                        criteria={"task_id": str(task_id)},
                    )

                    is_hubbard = task_query["input"]["is_hubbard"]

                    if (
                        task_query["orig_inputs"]["kpoints"]["generation_style"]
                        == "Monkhorst"
                    ):
                        nkpoints = np.prod(
                            task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0
                        )
                    else:
                        nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

                    lu_dt = task_query["last_updated"]

                    seen_other_data.append(
                        {
                            "is_static": True
                            if "Static" in mat["task_types"][task_id]
                            else False,
                            "task_id": str(task_id),
                            "is_hubbard": int(is_hubbard),
                            "nkpoints": int(nkpoints),
                            "updated_on": lu_dt,
                            "calcs_reversed": task_query["calcs_reversed"],
                        }
                    )

            for bs_type in mat["bandstructure"]:
                # select "blessed" bs of each type
                if seen_bs_data[bs_type]:
                    sorted_data = sorted(
                        seen_bs_data[bs_type],
                        key=lambda entry: (
                            entry["is_hubbard"],
                            entry["nkpoints"],
                            entry["updated_on"],
                        ),
                        reverse=True,
                    )

                    mat["bandstructure"][bs_type]["task_id"] = str(
                        sorted_data[0]["task_id"]
                    )
                    mat["bandstructure"][bs_type][
                        "object"
                    ] = self.bandstructure_fs.query_one(
                        criteria={"metadata.task_id": str(sorted_data[0]["task_id"])}
                    )

            if seen_dos_data:

                sorted_dos_data = sorted(
                    seen_dos_data,
                    key=lambda entry: (
                        entry["is_hubbard"],
                        entry["nkpoints"],
                        entry["updated_on"],
                    ),
                    reverse=True,
                )

                mat["dos"]["task_id"] = str(sorted_dos_data[0]["task_id"])
                mat["dos"]["object"] = self.dos_fs.query_one(
                    criteria={"metadata.task_id": str(sorted_dos_data[0]["task_id"])}
                )

            if seen_other_data:

                sorted_dos_data = sorted(
                    seen_dos_data,
                    key=lambda entry: (
                        entry["is_static"],
                        entry["is_hubbard"],
                        entry["nkpoints"],
                        entry["updated_on"],
                    ),
                    reverse=True,
                )

                mat["other"]["task_id"] = str(sorted_dos_data[0]["task_id"])

                task_output_data = sorted_dos_data[0]["calcs_reversed"][-1]["output"]
                mat["other"]["band_gap"] = task_output_data["bandgap"]

                for prop in ["efermi", "cbm", "vbm", "is_gap_direct", "is_metal"]:
                    mat["other"][prop] = task_output_data[prop]

            mats_updated.append(mat)

        return mats_updated

    @staticmethod
    def _obtain_path_type(
        labels_dict, structure, symprec=0.1, angle_tolerance=5, atol=1e-5
    ):

        type_dict = {"sc": "setyawan_curtarolo", "hin": "hinuma", "lm": "latimer_munro"}

        bs_type = None

        if any([label.islower() for label in labels_dict]):
            bs_type = "lm"
        else:
            for ptype in ["sc", "hin"]:
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

        return type_dict[bs_type]
