import os
import numpy as np
from maggma.builders import MapBuilder
from pymatgen import Structure
from atomate.utils.utils import load_class

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_validation_settings = os.path.join(
    module_dir, "settings", "task_validation.yaml"
)


class TaskTagger(MapBuilder):
    def __init__(
        self,
        tasks,
        task_types,
        input_sets=None,
        kpts_tolerance=0.9,
        kspacing_tolerance=0.22,  # TODO - this value should be much lower. Set high for now due to bandgap parsing bug.
        LDAU_fields=["LDAUU", "LDAUJ", "LDAUL"],
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_types (Store): Store of task_types for tasks
            input_sets (Dict): dictionary of task_type and pymatgen input set to validate against
            kpts_tolerance (float): relative tolerance to allow kpts to lag behind the InputSet settings
                (i.e., k-point density may be as low as kpts_tolerance times the InputSet value)
            kspacing_tolerance (float): absolute tolerance to allow KSPACING to differ from the InputSet settings
                (i.e., KSPACING may be as much as kspacing_tolerance smaller or larger than the InputSet value)
            LDAU_fields (list(String)): LDAU fields to check for consistency
        """
        self.tasks = tasks
        self.task_types = task_types
        self.input_sets = input_sets or {
            "GGA Structure Optimization": "MPRelaxSet",
            "GGA+U Structure Optimization": "MPRelaxSet",
            "GGA Static": "MPStaticSet",
            "GGA+U Static": "MPStaticSet",
            "SCAN Structure Optimization": "MPScanRelaxSet",
            "SCAN Static": "MPScanStaticSet",
            "R2SCAN Structure Optimization": "MPScanRelaxSet",
            "R2SCAN Static": "MPScanStaticSet",
            "PBEsol Structure Optimization": "MPScanRelaxSet",
            "PBEsol Static": "MPScanStaticSet",
        }
        self.kpts_tolerance = kpts_tolerance
        self.kspacing_tolerance = kspacing_tolerance
        self.LDAU_fields = LDAU_fields

        self._input_sets = {
            name: load_class("pymatgen.io.vasp.sets", inp_set)
            for name, inp_set in self.input_sets.items()
        }

        self.kwargs = kwargs

        super().__init__(
            source=tasks,
            target=task_types,
            projection=["orig_inputs",
                        "output.structure",
                        "output.bandgap",
                        "input.hubbards"
                        ],
            **kwargs,
        )

    def unary_function(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        tt = task_type(item["orig_inputs"])
        iv = is_valid(
            item["output"]["structure"],
            item["output"]["bandgap"],
            item["orig_inputs"],
            self._input_sets,
            self.kpts_tolerance,
            self.kspacing_tolerance,
            item.get("input",{}).get("hubbards",{})
        )

        d = {"task_type": tt, **iv}
        return d


def task_type(inputs, include_calc_type=True):
    """
    Determines the task_type

    Args:
        inputs (dict): inputs dict with an incar, kpoints, potcar, and poscar dictionaries
        include_calc_type (bool): whether to include calculation type
            in task_type such as HSE, GGA, SCAN, etc.
    """

    calc_type = []

    incar = inputs.get("incar", {})
    try:
        functional = inputs.get("potcar", {}).get("functional", "PBE")
    except Exception:
        functional = "PBE"

    METAGGA_TYPES = {"TPSS", "RTPSS", "M06L", "MBJL", "SCAN", "R2SCAN", "MS0", "MS1", "MS2"}

    if include_calc_type:
        if incar.get("LHFCALC", False):
            calc_type.append("HSE")
        elif incar.get("METAGGA", "").strip().upper() in METAGGA_TYPES:
            calc_type.append(incar["METAGGA"].strip().upper())
        elif incar.get("LDAU", False):
            calc_type.append("GGA+U")
        elif incar.get("GGA", "").strip().upper() == "PS":
            calc_type.append("PBEsol")
        elif functional == "PBE":
            calc_type.append("GGA")
        elif functional == "PW91":
            calc_type.append("PW91")
        elif functional == "Perdew-Zunger81":
            calc_type.append("LDA")

    if incar.get("ICHARG", 0) > 10:
        try:
            kpts = inputs.get("kpoints") or {}
            kpt_labels = kpts.get("labels") or []
            num_kpt_labels = len(list(filter(None.__ne__, kpt_labels)))
        except Exception as e:
            raise Exception(
                "Couldn't identify total number of kpt labels: {}".format(e)
            )

        if num_kpt_labels > 0:
            calc_type.append("NSCF Line")
        else:
            calc_type.append("NSCF Uniform")

    elif incar.get("LEPSILON", False):
        if incar.get("IBRION", 0) > 6:
            calc_type.append("DFPT")
        calc_type.append("Dielectric")

    elif incar.get("IBION", 0) > 6:
        calc_type.append("DFPT")

    elif incar.get("LCHIMAG", False):
        calc_type.append("NMR Nuclear Shielding")

    elif incar.get("LEFG", False):
        calc_type.append("NMR Electric Field Gradient")

    elif incar.get("NSW", 1) == 0:
        calc_type.append("Static")

    elif incar.get("ISIF", 2) == 3 and incar.get("IBRION", 0) > 0:
        calc_type.append("Structure Optimization")

    elif incar.get("ISIF", 3) == 2 and incar.get("IBRION", 0) > 0:
        calc_type.append("Deformation")

    return " ".join(calc_type)


def is_valid(
    structure,
    bandgap,
    inputs,
    input_sets,
    kpts_tolerance=0.9,
    kspacing_tolerance=0.22,  # TODO - this value should be much lower. Set high for now due to bandgap parsing bug.
    hubbards={},
):
    """
    Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

    Args:
        structure (dict or Structure): the output Structure from the calculation
        bandgap (float): The output bandgap of the calculation, in eV
        inputs (dict): a dict representation of the inputs in traditional pymatgen InputSet form
        input_sets (dict): a dictionary of task_types -> pymatgen InputSet for validation
        kpts_tolerance (float): relative tolerance to allow kpts to lag behind the InputSet settings
            (i.e., k-point density may be as low as kpts_tolerance times the InputSet value)
        kspacing_tolerance (float): absolute tolerance to allow KSPACING to differ from the InputSet settings
            (i.e., KSPACING may be as much as kspacing_tolerance smaller or larger than the InputSet value)
        LDAU_fields (list(String)): LDAU fields to check for consistency
    """

    if isinstance(structure, dict):
        structure = Structure.from_dict(structure)
    tt = task_type(inputs)

    d = {"is_valid": True, "_warnings": []}

    if tt in input_sets:
        if "SCAN" in tt or "PBEsol" in tt:
            # MPScanRelaxSet takes bandgap as an additional kwarg
            valid_input_set = input_sets[tt](structure, bandgap)
        else:
            valid_input_set = input_sets[tt](structure)

        # Checking K-Points
        # Calculations that use KSPACING will not have a .kpoints attr
        if valid_input_set.kpoints:
            valid_num_kpts = valid_input_set.kpoints.num_kpts or np.prod(
                valid_input_set.kpoints.kpts[0]
            )
            num_kpts = inputs.get("kpoints", {}).get("nkpoints", 0) or np.prod(
                inputs.get("kpoints", {}).get("kpoints", [0, 0, 0])
            )
            d["kpts_ratio"] = num_kpts / valid_num_kpts
            if d["kpts_ratio"] < kpts_tolerance:
                d["is_valid"] = False
                d["_warnings"].append("Too few KPoints")
        else:
            valid_kspacing = valid_input_set.incar.get("KSPACING", 0)
            kspacing = inputs["incar"].get("KSPACING")
            d["kspacing_delta"] = kspacing - valid_kspacing
            if abs(d["kspacing_delta"]) > kspacing_tolerance:
                d["is_valid"] = False
                d["_warnings"].append("KSPACING differs")

        # Checking ENCUT
        encut = inputs.get("incar", {}).get("ENCUT")
        valid_encut = valid_input_set.incar["ENCUT"]
        d["encut_ratio"] = float(encut) / valid_encut
        if d["encut_ratio"] < 1:
            d["is_valid"] = False
            d["_warnings"].append("ENCUT too low")

        # Checking U-values
        if valid_input_set.incar.get("LDAU", False) or len(hubbards) > 0:
            # Assemble required input_set LDAU params into dictionary
            input_set_hubbards = dict(
                zip(
                    valid_input_set.poscar.site_symbols,
                    valid_input_set.incar.get("LDAUU", []),
                )
            )

            all_els = list(set(input_set_hubbards.keys()) | set(hubbards.keys()))
            diff = {
                el: (input_set_hubbards.get(el, 0), hubbards.get(el, 0))
                for el in all_els
                if input_set_hubbards.get(el) != hubbards.get(el)
            }

            if any(v[0] != v[1] for v in diff.values()):

                d["is_valid"] = False
                d["_warnings"].append("LDAU parameters don't match")
                d["_warnings"].extend(
                    [
                        f"U-value for {el} should be {good} but was {bad}"
                        for el, (bad, good) in diff.items()
                    ]
                )

        # check smearing settings
        ismear = inputs["incar"].get("ISMEAR", 1)

        # ISMEAR > 0 is only appropriate for metals, per VASP docs
        # if ismear > 0 and bandgap > 0:
        #     d["is_valid"] = False
        #     d["_warnings"].append("Inappropriate smearing settings")

    if len(d["_warnings"]) == 0:
        del d["_warnings"]

    return d
