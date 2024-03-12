from collections import defaultdict
from math import ceil
import itertools
import re
import boto3
import numpy as np
from botocore.handlers import disable_signing
from maggma.builders import Builder
from maggma.utils import grouper
from pymatgen.analysis.magnetism.analyzer import CollinearMagneticStructureAnalyzer
from pymatgen.core import Structure
from pymatgen.electronic_structure.core import Spin
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.dos import CompleteDos
from pymatgen.symmetry.bandstructure import HighSymmKpath
from pymatgen.analysis.structure_matcher import StructureMatcher
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.io.vasp.sets import MPStaticSet

from emmet.core.settings import EmmetSettings
from emmet.core.electronic_structure import ElectronicStructureDoc
from emmet.core.utils import jsanitize

from emmet.builders.utils import query_open_data

SETTINGS = EmmetSettings()


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
        **kwargs,
    ):
        """
        Creates an electronic structure collection from a tasks collection,
        the associated band structures and density of states file store collections,
        and the materials collection.

        Individual bandstructures for each of the three conventions are generated.

        tasks (Store): Store of task documents
        materials (Store): Store of materials documents
        electronic_structure (Store): Store of electronic structure summary data documents
        bandstructure_fs (Store, str): Store of bandstructures, or S3 URL string with prefix
            (e.g. s3://materialsproject-parsed/bandstructures).
        dos_fs (Store, str): Store of DOS, or S3 URL string with bucket and prefix
            (e.g. s3://materialsproject-parsed/dos).
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

        self._s3_resource = None

        sources = [tasks, materials]

        fs_stores = [bandstructure_fs, dos_fs]

        for store in fs_stores:
            if isinstance(store, str):
                if not re.match("^s3://.*", store):
                    raise ValueError(
                        "Please provide an S3 URL "
                        "in the format s3://{bucket_name}/{prefix}"
                    )

                if self._s3_resource is None:
                    self._s3_resource = boto3.resource("s3")
                    self._s3_resource.meta.client.meta.events.register(
                        "choose-signer.s3.*", disable_signing
                    )

            else:
                sources.append(store)

        super().__init__(
            sources=sources,
            targets=[electronic_structure],
            chunk_size=chunk_size,
            **kwargs,
        )

    def prechunk(self, number_splits: int):  # pragma: no cover
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

        # Default summary data
        d = dict(
            material_id=mat[self.materials.key],
            deprecated=mat["deprecated"],
            task_id=mat["other"]["task_id"],
            meta_structure=structure,
            band_gap=mat["other"]["band_gap"],
            cbm=mat["other"]["cbm"],
            vbm=mat["other"]["vbm"],
            efermi=mat["other"]["efermi"],
            is_gap_direct=mat["other"]["is_gap_direct"],
            is_metal=mat["other"]["is_metal"],
            magnetic_ordering=mat["other"]["magnetic_ordering"],
            origins=mat["origins"],
            warnings=[],
        )

        # Eigenvalue band property checks
        eig_values = mat["other"].get("eigenvalue_band_properties", None)

        if eig_values is not None:
            if not np.isclose(
                mat["other"]["band_gap"], eig_values["bandgap"], atol=0.2, rtol=0.0
            ):
                d["warnings"].append(
                    "Regular parsed band gap and band gap from eigenvalue_band_properties do not agree. "
                    "Using data from eigenvalue_band_properties where appropriate."
                )

                d["band_gap"] = eig_values["bandgap"]
                d["cbm"] = eig_values["cbm"]
                d["vbm"] = eig_values["vbm"]
                d["is_gap_direct"] = eig_values["is_gap_direct"]
                d["is_metal"] = (
                    True if np.isclose(d["band_gap"], 0.0, atol=0.01, rtol=0) else False
                )

        if dos is None:
            doc = ElectronicStructureDoc.from_structure(**d)

        else:
            try:
                doc = ElectronicStructureDoc.from_bsdos(
                    material_id=mat[self.materials.key],
                    structures=structures,
                    dos=dos,
                    is_gap_direct=d["is_gap_direct"],
                    is_metal=d["is_metal"],
                    deprecated=d["deprecated"],
                    origins=d["origins"],
                    **bs,
                )
                doc = self._bsdos_checks(doc, dos[mat["dos"]["task_id"]], structures)

            except Exception:
                d["warnings"].append(
                    "Band structure and/or data exists but an error occured while processing."
                )
                doc = ElectronicStructureDoc.from_structure(**d)

        # Magnetic ordering check
        mag_orderings = {}
        if doc.bandstructure is not None:
            mag_orderings.update(
                {
                    bs_summary.task_id: bs_summary.magnetic_ordering
                    for bs_type, bs_summary in doc.bandstructure
                    if bs_summary is not None
                }
            )

        if doc.dos is not None:
            dos_dict = doc.dos.model_dump()
            mag_orderings.update(
                {dos_dict["total"][Spin.up]["task_id"]: dos_dict["magnetic_ordering"]}
            )

        for task_id, ordering in mag_orderings.items():
            if doc.magnetic_ordering != ordering:
                doc.warnings.append(
                    f"Summary data magnetic ordering does not agree with the ordering from {task_id}"
                )

        # LMAXMIX check, VASP default is 2
        expected_lmaxmix = MPStaticSet(structure).incar.get("LMAXMIX", 2)
        if mat["dos"] and mat["dos"]["lmaxmix"] != expected_lmaxmix:
            doc.warnings.append(
                "An incorrect calculation parameter may lead to errors in the band gap of "
                f"0.1-0.2 eV (LMAXIX is {mat['dos']['lmaxmix']} and should be {expected_lmaxmix} for "
                f"{mat['dos']['task_id']}). A correction calculation is planned."
            )

        for bs_type, bs_entry in mat["bandstructure"].items():
            if bs_entry["lmaxmix"] != expected_lmaxmix:
                doc.warnings.append(
                    "An incorrect calculation parameter may lead to errors in the band gap of "
                    f"0.1-0.2 eV (LMAXIX is {bs_entry['lmaxmix']} and should be {expected_lmaxmix} for "
                    f"{bs_entry['task_id']}). A correction calculation is planned."
                )

        return doc.model_dump()

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

    def _bsdos_checks(self, doc, dos, structures):
        # Band gap difference check for uniform and line-mode calculations
        bgap_diff = []
        for bs_type, bs_summary in doc.bandstructure:
            if bs_summary is not None:
                bgap_diff.append(doc.band_gap - bs_summary.band_gap)

        if dos is not None:
            bgap_diff.append(doc.band_gap - dos.get_gap())

        if any(abs(gap) > 0.25 for gap in bgap_diff):
            if doc.warnings is None:
                doc.warnings = []
            doc.warnings.append(
                "Absolute difference between blessed band gap and at least one "
                "line-mode or uniform calculation band gap is larger than 0.25 eV."
            )

        # Line-mode and uniform structure primitive checks

        pair_list = []
        for task_id, struct in structures.items():
            pair_list.append((task_id, struct))

            struct_prim = SpacegroupAnalyzer(struct).get_primitive_standard_structure(
                international_monoclinic=False
            )

            if not np.allclose(
                struct.lattice.matrix, struct_prim.lattice.matrix, atol=1e-3
            ):
                if doc.warnings is None:
                    doc.warnings = []

                if np.isclose(struct_prim.volume, struct.volume, atol=5, rtol=0):
                    doc.warnings.append(
                        f"The input structure for {task_id} is primitive but may not exactly match the "
                        f"standard primitive setting."
                    )
                else:
                    doc.warnings.append(
                        f"The input structure for {task_id} does not match the expected standard primitive"
                    )

        # Check line-mode and uniform for same structure
        sm = StructureMatcher()
        for pair in itertools.combinations(pair_list, 2):
            if not sm.fit(pair[0][1], pair[1][1]):
                if doc.warnings is None:
                    doc.warnings = []

                doc.warnings.append(
                    f"The input structures between bandstructure calculations {pair[0][0]} and {pair[1][0]} "
                    f"are not equivalent"
                )

        return doc

    def _update_materials_doc(self, mat_id):
        # find bs type for each task in task_type and store each different bs object

        mat = self.materials.query_one(
            properties=[
                self.materials.key,
                "structure",
                "inputs",
                "task_types",
                "deprecated",
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
                        "input.incar",
                        "orig_inputs.kpoints",
                        "input.parameters",
                        "output.structure",
                    ],
                    criteria={"task_id": str(task_id)},
                )

                fs_id = str(
                    task_query["calcs_reversed"][0].get("bandstructure_fs_id", None)
                )

                if fs_id is not None:
                    structure = Structure.from_dict(task_query["output"]["structure"])

                    kpoints = task_query["orig_inputs"]["kpoints"]

                    labels_dict = {
                        label: point
                        for label, point in zip(kpoints["labels"], kpoints["kpoints"])
                        if label is not None
                    }

                    try:
                        bs_type = self._obtain_path_type(labels_dict, structure)
                    except Exception:
                        bs_type = None

                    if bs_type is None:
                        if isinstance(self.bandstructure_fs, str):
                            _, _, bucket, prefix = self.bandstructure_fs.strip(
                                "/"
                            ).split("/")

                            bs_dict = query_open_data(
                                bucket,
                                prefix,
                                task_id,
                                monty_decode=False,
                                s3_resource=self._s3_resource,
                            )
                        else:
                            bs_dict = self.bandstructure_fs.query_one(
                                {self.bandstructure_fs.key: str(task_id)}
                            )

                        if bs_dict is not None:
                            bs = BandStructureSymmLine.from_dict(bs_dict["data"])

                            labels_dict = {
                                label: kpoint.frac_coords
                                for label, kpoint in bs.labels_dict.items()
                            }

                            try:
                                bs_type = self._obtain_path_type(
                                    labels_dict, bs.structure
                                )
                            except Exception:
                                bs_type = None

                        # Clear bs data
                        bs = None
                        bs_dict = None

                    is_hubbard = task_query["input"]["is_hubbard"]
                    lmaxmix = task_query["input"]["incar"].get(
                        "LMAXMIX", 2
                    )  # VASP default is 2, alternatively could project `parameters`
                    nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]
                    lu_dt = task_query["last_updated"]

                    if bs_type is not None:
                        bs_calcs[bs_type].append(
                            {
                                "fs_id": fs_id,
                                "task_id": task_id,
                                "is_hubbard": int(is_hubbard),
                                "lmaxmix": lmaxmix,
                                "nkpoints": int(nkpoints),
                                "updated_on": lu_dt,
                                "output_structure": structure,
                                "labels_dict": labels_dict,
                            }
                        )

            # Handle uniform tasks
            if "NSCF Uniform" in mat["task_types"][task_id]:
                task_query = self.tasks.query_one(
                    properties=[
                        "calcs_reversed",
                        "last_updated",
                        "input.is_hubbard",
                        "input.incar",
                        "orig_inputs.kpoints",
                        "input.parameters",
                        "output.structure",
                    ],
                    criteria={"task_id": str(task_id)},
                )

                fs_id = str(task_query["calcs_reversed"][0].get("dos_fs_id", None))

                if fs_id is not None:
                    lmaxmix = task_query["input"]["incar"].get(
                        "LMAXMIX", 2
                    )  # VASP default is 2, alternatively could project `parameters`

                    is_hubbard = task_query["input"]["is_hubbard"]

                    structure = Structure.from_dict(task_query["output"]["structure"])

                    if (
                        task_query["orig_inputs"]["kpoints"]["generation_style"]
                        == "Monkhorst"
                        or task_query["orig_inputs"]["kpoints"]["generation_style"]
                        == "Gamma"
                    ):
                        nkpoints = np.prod(
                            task_query["orig_inputs"]["kpoints"]["kpoints"][0], axis=0
                        )

                    else:
                        nkpoints = task_query["orig_inputs"]["kpoints"]["nkpoints"]

                    nedos = task_query["input"]["parameters"]["NEDOS"]
                    lu_dt = task_query["last_updated"]

                    dos_calcs.append(
                        {
                            "fs_id": fs_id,
                            "task_id": task_id,
                            "is_hubbard": int(is_hubbard),
                            "lmaxmix": lmaxmix,
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

                if (
                    last_calc["input"]["kpoints"]["generation_style"] == "Monkhorst"
                    or last_calc["input"]["kpoints"]["generation_style"] == "Gamma"
                ):
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

        materials_doc["origins"] = []

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

                materials_doc["bandstructure"][bs_type]["lmaxmix"] = sorted_bs_data[0][
                    "lmaxmix"
                ]
                if isinstance(self.bandstructure_fs, str):
                    _, _, bucket, prefix = self.bandstructure_fs.strip("/").split("/")
                    bs_obj = query_open_data(
                        bucket,
                        prefix,
                        sorted_bs_data[0]["task_id"],
                        monty_decode=False,
                        s3_resource=self._s3_resource,
                    )
                else:
                    bs_obj = self.bandstructure_fs.query_one(
                        criteria={"fs_id": sorted_bs_data[0]["fs_id"]}
                    )

                materials_doc["bandstructure"][bs_type]["object"] = (
                    bs_obj["data"] if bs_obj is not None else None
                )

                materials_doc["bandstructure"][bs_type][
                    "output_structure"
                ] = sorted_bs_data[0]["output_structure"]

                materials_doc["origins"].append(
                    {
                        "name": bs_type,
                        "task_id": sorted_bs_data[0]["task_id"],
                        "last_updated": sorted_bs_data[0]["updated_on"],
                    }
                )

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

            materials_doc["dos"]["lmaxmix"] = sorted_dos_data[0]["lmaxmix"]

            if isinstance(self.bandstructure_fs, str):
                _, _, bucket, prefix = self.dos_fs.strip("/").split("/")
                dos_obj = query_open_data(
                    bucket,
                    prefix,
                    sorted_dos_data[0]["task_id"],
                    monty_decode=False,
                    s3_resource=self._s3_resource,
                )
            else:
                dos_obj = self.dos_fs.query_one(
                    criteria={"fs_id": sorted_dos_data[0]["fs_id"]}
                )

            materials_doc["dos"]["object"] = (
                dos_obj["data"] if dos_obj is not None else None
            )

            materials_doc["dos"]["output_structure"] = sorted_dos_data[0][
                "output_structure"
            ]

            materials_doc["origins"].append(
                {
                    "name": "dos",
                    "task_id": sorted_dos_data[0]["task_id"],
                    "last_updated": sorted_dos_data[0]["updated_on"],
                }
            )

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
            materials_doc["other"]["last_updated"] = sorted_other_data[0]["updated_on"]

            materials_doc["other"]["is_metal"] = (
                materials_doc["other"]["band_gap"] == 0.0
            )

            materials_doc["origins"].append(
                {
                    "name": "electronic_structure",
                    "task_id": sorted_other_data[0]["task_id"],
                    "last_updated": sorted_other_data[0]["updated_on"],
                }
            )

            for prop in [
                "efermi",
                "cbm",
                "vbm",
                "is_gap_direct",
                "is_metal",
                "eigenvalue_band_properties",
            ]:
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
