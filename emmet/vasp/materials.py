from pathlib import Path
from datetime import datetime
from itertools import chain, groupby
from operator import itemgetter
from typing import Optional, Dict, List, Iterator

from monty.json import jsanitize
from pymatgen import Structure
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator
from pymatgen.analysis.piezo import PiezoTensor
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from maggma.stores import Store
from maggma.builders import Builder
from emmet.vasp.task_tagger import task_type
from emmet.common.utils import load_settings
from emmet.magic_numbers import LTOL, STOL, ANGLE_TOL, SYMPREC
from pydash.objects import get, set_, has

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

module_dir = Path(__file__).parent
default_mat_settings = module_dir / "settings" / "materials_settings.json"


class MaterialsBuilder(Builder):
    """
    The Materials Builder aggregates VASP task documents by structure similarity into materials
    properties documents.
    The process is as follows:

        1.) Find all documents with the same formula
        2.) Select only task documents for the task_types we can select properties from
        3.) Aggregate task documents based on strucutre similarity
        4.) Convert task docs to property docs with metadata for selection and aggregation
        5.) Select the best property doc for each property
        6.) Build material document from best property docs
        7.) Post-process material document
        8.) Validate material document

    """

    def __init__(
        self,
        tasks: Store,
        materials: Store,
        task_types: Optional[Store] = None,
        materials_settings: Path = None,
        query: Optional[Dict] = None,
        symprec: float = SYMPREC,
        ltol: float = LTOL,
        stol: float = STOL,
        angle_tol: float = ANGLE_TOL,
        **kwargs,
    ):
        """
        Creates a materials collection from tasks and tags

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents to generate
            materials_settings (Path): Path to settings files
            query (dict): dictionary to limit tasks to be analyzed
            symprec (float): tolerance for SPGLib spacegroup finding
            ltol (float): StructureMatcher tuning parameter for matching tasks to materials
            stol (float): StructureMatcher tuning parameter for matching tasks to materials
            angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        """

        self.tasks = tasks
        self.materials_settings = materials_settings
        self.materials = materials
        self.task_types = task_types
        self.query = query if query else {}
        self.symprec = symprec
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.kwargs = kwargs

        self.__settings = load_settings(self.materials_settings, default_mat_settings)
        # Projection for only the fields we need to build the materials doc
        projected_from_tasks = [d["tasks_key"] for d in self.__settings]
        projected_from_tasks += [
            "formula_pretty",
            self.tasks.key,
            self.tasks.last_updated_field,
            "sbxn",
            "tags"
        ]

        projected_from_tasks = [p.split(".") for p in projected_from_tasks]
        projected_from_tasks = [
            [k for k in p if k != "0"] for p in projected_from_tasks
        ]
        projected_from_tasks = [".".join(p) for p in projected_from_tasks]

        self.projected_from_tasks = list(
            set(projected_from_tasks + ["input.parameters"])
        )
        self.allowed_tasks = {
            t_type for d in self.__settings for t_type in d["quality_score"]
        }

        sources = [tasks]
        if self.task_types:
            sources.append(self.task_types)
        super().__init__(sources=sources, targets=[materials], **kwargs)

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("Materials builder started")
        self.logger.info(f"Allowed task types: {self.allowed_tasks}")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        # Save timestamp to mark buildtime for material documents
        self.timestamp = datetime.utcnow()

        # Get all processed tasks:
        q = dict(self.query)
        q["state"] = "successful"

        self.logger.info("Finding tasks to process")
        all_tasks = set(self.tasks.distinct(self.tasks.key, q))
        processed_tasks = set(self.materials.distinct("task_ids"))
        to_process_tasks = all_tasks - processed_tasks
        to_process_forms = self.tasks.distinct(
            "formula_pretty", {self.tasks.key: {"$in": list(to_process_tasks)}}
        )
        self.logger.info(f"Found {len(to_process_tasks)} unprocessed tasks")
        self.logger.info(f"Found {len(to_process_forms)} unprocessed formulas")

        # Set total for builder bars to have a total
        self.total = len(to_process_forms)

        if self.task_types:
            invalid_ids = set(
                self.task_types.distinct(self.task_types.key, {"is_valid": False})
            )
        else:
            invalid_ids = set()

        for formula in to_process_forms:
            tasks_q = dict(q)
            tasks_q["formula_pretty"] = formula
            tasks = list(
                self.tasks.query(criteria=tasks_q, properties=self.projected_from_tasks)
            )
            for t in tasks:
                if t[self.tasks.key] in invalid_ids or "deprecated" in t.get("tags",[]):
                    t["is_valid"] = False
                else:
                    t["is_valid"] = True

            yield tasks

    def process_item(self, tasks: List[Dict]) -> List[Dict]:
        """
        Process the tasks into a list of materials

        Args:
            tasks [dict] : a list of task docs

        Returns:
            ([dict],list) : a list of new materials docs and a list of task_ids that were processsed
        """
        try:

            formula = tasks[0]["formula_pretty"]
            t_ids = [t[self.tasks.key] for t in tasks]
            self.logger.debug(f"Processing {formula} : {t_ids}")

            materials = []
            grouped_tasks = self.filter_and_group_tasks(tasks)

            for group in grouped_tasks:
                mat = self.make_mat(group)
                if mat and self.valid(mat):
                    self.post_process(mat)
                    materials.append(mat)

            self.logger.debug(f"Produced {len(materials)} materials for {formula}")

            return materials
        except Exception as e:
            self.logger.error(e)
            return [None]

    def update_targets(self, items: List[List[Dict]]):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding
                processed task_ids
        """

        items = list(filter(None, chain.from_iterable(items)))

        for item in items:
            item.update({"_bt": self.timestamp})

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} materials")
            self.materials.update(docs=items)
        else:
            self.logger.info("No items to update")

    def make_mat(self, task_group: List[Dict]) -> Dict:
        """
        Converts a group of tasks into one material
        """

        # Convert the task to properties and flatten
        all_props = list(
            chain.from_iterable([self.task_to_prop_list(t) for t in task_group])
        )

        mat_id = find_mat_id(all_props)

        # Sort and group based on property
        sorted_props = sorted(all_props, key=itemgetter("materials_key"))
        grouped_props = groupby(sorted_props, key=itemgetter("materials_key"))

        # Choose the best prop for each materials key: highest quality score and lowest energy calculation
        best_props = [find_best_prop(props) for _, props in grouped_props]

        # Add in the provenance for the properties
        origins = [
            {
                k: prop[k]
                for k in ["materials_key", "task_type", "task_id", "last_updated"]
            }
            for prop in best_props
            if prop.get("track", False)
        ]

        # Store any bad props
        invalid_props = [
            prop["materials_key"] for prop in best_props if not prop["is_valid"]
        ]

        # Store all the task_ids
        task_ids = list(set([t["task_id"] for t in task_group]))
        deprecated_tasks = list(
            set([t["task_id"] for t in task_group if not t.get("is_valid", True)])
        )

        # Store task_types
        task_types = {t["task_id"]: t["task_type"] for t in all_props}

        # Store sandboxes
        sandboxes = list(set(chain.from_iterable([k["sbxn"] for k in best_props])))

        mat = {
            self.materials.last_updated_field: max(
                [prop["last_updated"] for prop in all_props]
            ),
            "created_at": min([prop["last_updated"] for prop in all_props]),
            "task_ids": task_ids,
            "deprecated_tasks": deprecated_tasks,
            self.materials.key: mat_id,
            "origins": origins,
            "task_types": task_types,
            "invalid_props": invalid_props,
            "_sbxn": sandboxes,
        }

        for prop in best_props:
            set_(mat, prop["materials_key"], prop["value"])

        return mat

    def filter_and_group_tasks(self, tasks: List[Dict]) -> Iterator[List[Dict]]:
        """
        Groups tasks by structure matching
        """

        filtered_tasks = [
            t for t in tasks if task_type(t["orig_inputs"]) in self.allowed_tasks
        ]

        structures = []

        for idx, t in enumerate(filtered_tasks):
            s = Structure.from_dict(t["output"]["structure"])
            s.index = idx
            structures.append(s)

        grouped_structures = group_structures(
            structures,
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            symprec=self.symprec,
        )

        for group in grouped_structures:
            yield [filtered_tasks[struc.index] for struc in group]

    def task_to_prop_list(self, task: Dict) -> List[Dict]:
        """
        Converts a task into an list of properties with associated metadata
        """
        t_type = task_type(task["orig_inputs"])
        t_id = task[self.tasks.key]

        _SPECIAL_TAGS = ["LASPH", "ISPIN"]
        # Convert the task doc into a serious of properties in the materials
        # doc with the right document structure
        props = []
        for prop in self.__settings:
            if t_type in prop["quality_score"].keys():
                if has(task, prop["tasks_key"]):
                    props.append(
                        {
                            "value": get(task, prop["tasks_key"]),
                            "task_type": t_type,
                            "task_id": t_id,
                            "quality_score": prop["quality_score"][t_type],
                            "special_tags": sum(
                                [
                                    task.get("input", {})
                                    .get("parameters", {})
                                    .get(tag, False)
                                    for tag in _SPECIAL_TAGS
                                ]
                            ),
                            "max_forces": task.get("analysis", {}).get(
                                "max_force", 10000
                            )
                            or 10000,
                            "track": prop.get("track", False),
                            "aggregate": prop.get("aggregate", False),
                            "last_updated": task[self.tasks.last_updated_field],
                            "energy": get(task, "output.energy_per_atom", 0.0),
                            "materials_key": prop["materials_key"],
                            "is_valid": task.get("is_valid", True),
                            "sbxn": task.get("sbxn", []),
                        }
                    )
                elif not prop.get("optional", False):
                    self.logger.error(
                        f"Failed getting {prop['tasks_key']} for task: {t_id}"
                    )
        return props

    def valid(self, doc: Dict) -> bool:
        """
        Determines if the resulting material document is valid
        """
        if doc["task_id"] is None:
            return False
        elif "structure" not in doc:
            return False

        return True

    def post_process(self, mat: Dict):
        """
        Any extra post-processing on a material doc
        """

        # Add structure metadata back into document and convert back to conventional standard
        if "structure" in mat:
            structure = Structure.from_dict(mat["structure"])
            mat["structure"] = structure.as_dict()
            mat.update(structure_metadata(structure, symprec=self.symprec))

        # Deprecate materials with bad structures or energies
        if "structure" in mat["invalid_props"]:
            mat.update({"deprecated": True})
        elif "thermo.energy_per_atom" in mat["invalid_props"]:
            mat.update({"deprecated": True})
        else:
            mat.update({"deprecated": False})

        # Reorder voigt output from VASP to standard voigt notation
        # TODO: Update this in the drone or in pymatgen
        if has(mat, "piezo.ionic"):
            mat["piezo"]["ionic"] = PiezoTensor.from_vasp_voigt(
                mat["piezo"]["ionic"]
            ).voigt.tolist()
        if has(mat, "piezo.static"):
            mat["piezo"]["static"] = PiezoTensor.from_vasp_voigt(
                mat["piezo"]["static"]
            ).voigt.tolist()

        if "initial_structures" in mat:
            # Reduce unique structures using tight tolerancees
            init_strucs = [Structure.from_dict(d) for d in mat["initial_structures"]]
            num_init_strucs = len(init_strucs)
            sm = StructureMatcher(
                primitive_cell=True,
                scale=True,
                attempt_supercell=False,
                allow_subset=False,
                comparator=ElementComparator(),
            )
            init_strucs = [g[0].as_dict() for g in sm.group_structures(init_strucs)]
            mat["initial_structures"] = jsanitize(init_strucs)
            self.logger.debug(
                "Reducing initial structures based on structure matching from"
                f" {num_init_strucs} to {len(init_strucs)}"
            )

        for entry in mat.get("entries", {}).values():
            entry["entry_id"] = mat[self.materials.key]

        for entry_type in list(mat.get("entries", {}).keys()):
            if any(
                f"entries.{entry_type}." in invalid_prop
                for invalid_prop in mat.get("invalid_props", [])
            ):
                del mat["entries"][entry_type]

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key, unique=True)
        self.tasks.ensure_index("state")
        self.tasks.ensure_index("formula_pretty")
        self.tasks.ensure_index(self.tasks.last_updated_field)

        # Search index for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index("task_ids")
        self.materials.ensure_index(self.materials.last_updated_field)

        if self.task_types:
            self.task_types.ensure_index(self.task_types.key)
            self.task_types.ensure_index("is_valid")


def find_mat_id(props: List[Dict]):

    # Only consider structure optimization task_ids for material task_id
    possible_mat_ids = [
        prop["task_id"]
        for prop in props
        if "Structure Optimization" in prop["task_type"]
    ]

    # Sort task_ids by ID
    mat_to_int = [ID_to_int(d) for d in possible_mat_ids]
    possible_mat_ids = sorted(zip(mat_to_int, possible_mat_ids), key=itemgetter(0))

    if len(possible_mat_ids) == 0:
        return None
    else:
        return possible_mat_ids[0][1]


def find_best_prop(props: List[Dict]) -> Dict:
    """
    Takes a list of property docs all for the same property
    1.) Sorts according to valid tasks, highest quality score and lowest energy
    2.) Checks if this is an aggregation prop and aggregates
    3.) Returns best property
    """

    # Sort for highest quality score and lowest energy
    sorted_props = sorted(
        props,
        key=lambda doc: (
            -1 * doc["is_valid"],
            -1 * doc["quality_score"],
            -1 * doc["special_tags"],
            doc["energy"],
        ),
    )
    if sorted_props[0].get("aggregate", False):
        # Make this a list of lists and then flatten to deal with mixed value typing
        vals = [
            prop["value"] if isinstance(prop["value"], list) else [prop["value"]]
            for prop in sorted_props
        ]
        vals = list(chain.from_iterable(vals))
        prop = sorted_props[0]
        prop["value"] = vals
        # Can"t track an aggregated property
        prop["track"] = False
    else:
        prop = sorted_props[0]

    return prop


def structure_metadata(structure: Structure, symprec=SYMPREC) -> Dict:
    """
    Generates metadata based on a structure
    """
    comp = structure.composition
    elsyms = sorted(set([e.symbol for e in comp.elements]))

    sg = SpacegroupAnalyzer(structure, 0.1)
    symmetry = {"symprec": 0.1}
    if not sg.get_symmetry_dataset():
        sg = SpacegroupAnalyzer(structure, 1e-3, 1)
        symmetry["symprec"] = 1e-3

    symmetry.update(
        {
            "source": "spglib",
            "symbol": sg.get_space_group_symbol(),
            "number": sg.get_space_group_number(),
            "point_group": sg.get_point_group_symbol(),
            "crystal_system": sg.get_crystal_system(),
            "hall": sg.get_hall(),
        }
    )

    meta = {
        "nsites": structure.num_sites,
        "elements": elsyms,
        "nelements": len(elsyms),
        "composition": comp.as_dict(),
        "composition_reduced": comp.reduced_composition.as_dict(),
        "formula_pretty": comp.reduced_formula,
        "formula_anonymous": comp.anonymized_formula,
        "chemsys": "-".join(elsyms),
        "volume": structure.volume,
        "density": structure.density,
        "symmetry": symmetry,
    }

    return meta


def group_structures(
    structures: List[Structure],
    ltol: float = LTOL,
    stol: float = STOL,
    angle_tol: float = ANGLE_TOL,
    symprec: float = SYMPREC,
) -> Iterator[List[Structure]]:
    """
    Groups structures according to space group and structure matching

    Args:
        structures ([Structure]): list of structures to group
        ltol (float): StructureMatcher tuning parameter for matching tasks to materials
        stol (float): StructureMatcher tuning parameter for matching tasks to materials
        angle_tol (float): StructureMatcher tuning parameter for matching tasks to materials
        symprec (float): symmetry tolerance for space group finding
    """

    sm = StructureMatcher(
        ltol=ltol,
        stol=stol,
        angle_tol=angle_tol,
        primitive_cell=True,
        scale=True,
        attempt_supercell=False,
        allow_subset=False,
        comparator=ElementComparator(),
    )

    def get_sg(struc):
        # helper function to get spacegroup with a loose tolerance
        try:
            sg = struc.get_space_group_info(symprec=symprec)[1]
        except Exception:
            sg = -1

        return sg

    # First group by spacegroup number then by structure matching
    for sg, pregroup in groupby(sorted(structures, key=get_sg), key=get_sg):
        for group in sm.group_structures(list(pregroup)):
            yield group


def ID_to_int(s_id: str) -> int:
    """
    Converts a string id to tuple
    falls back to assuming ID is an Int if it can't process
    Assumes string IDs are of form "[chars]-[int]" such as mp-234
    """
    if isinstance(s_id, str):
        return (s_id.split("-")[0], int(str(s_id).split("-")[-1]))
    elif isinstance(s_id, (int, float)):
        return s_id
    else:
        raise Exception(f"Could not parse {s_id} into a number")
