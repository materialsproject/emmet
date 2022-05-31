from datetime import datetime
from typing import Dict, List, Union

import numpy as np
from pydantic import Field, PyObject
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.sets import VaspInputSet

from emmet.core.settings import EmmetSettings
from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID
from emmet.core.utils import DocEnum
from emmet.core.vasp.task_valid import TaskDocument

SETTINGS = EmmetSettings()


class DeprecationMessage(DocEnum):
    MANUAL = "M", "Manual deprecation"
    KPTS = "C001", "Too few KPoints"
    KSPACING = "C002", "KSpacing not high enough"
    ENCUT = "C002", "ENCUT too low"
    FORCES = "C003", "Forces too large"
    MAG = "C004", "At least one site magnetization is too large"
    CONVERGENCE = "E001", "Calculation did not converge"
    MAX_SCF = "E002", "Max SCF gradient too large"
    LDAU = "I001", "LDAU Parameters don't match the inputset"


class ValidationDoc(EmmetBaseModel):
    """
    Validation document for a VASP calculation
    """

    task_id: MPID = Field(..., description="The task_id for this validation document")
    valid: bool = Field(False, description="Whether this task is valid or not")
    last_updated: datetime = Field(
        description="Last updated date for this document",
        default_factory=datetime.utcnow,
    )
    reasons: List[Union[DeprecationMessage, str]] = Field(
        None, description="List of deprecation tags detailing why this task isn't valid"
    )
    warnings: List[str] = Field(
        [], description="List of potential warnings about this calculation"
    )
    data: Dict = Field(
        description="Dictioary of data used to perform validation."
        " Useful for post-mortem analysis"
    )

    class Config:
        extra = "allow"

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDocument,
        kpts_tolerance: float = SETTINGS.VASP_KPTS_TOLERANCE,
        kspacing_tolerance: float = SETTINGS.VASP_KSPACING_TOLERANCE,
        input_sets: Dict[str, PyObject] = SETTINGS.VASP_DEFAULT_INPUT_SETS,
        LDAU_fields: List[str] = SETTINGS.VASP_CHECKED_LDAU_FIELDS,
        max_allowed_scf_gradient: float = SETTINGS.VASP_MAX_SCF_GRADIENT,
    ) -> "ValidationDoc":
        """
        Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

        Args:
            task_doc: the task document to process
            kpts_tolerance: the tolerance to allow kpts to lag behind the input set settings
            kspacing_tolerance:  the tolerance to allow kspacing to lag behind the input set settings
            input_sets: a dictionary of task_types -> pymatgen input set for validation
            LDAU_fields: LDAU fields to check for consistency
            max_allowed_scf_gradient: maximum uphill gradient allowed for SCF steps after the
                initial equillibriation period
        """

        structure = task_doc.output.structure
        calc_type = task_doc.calc_type
        inputs = task_doc.orig_inputs
        bandgap = task_doc.output.bandgap
        chemsys = task_doc.chemsys

        reasons = []
        data = {}
        warnings = []

        if str(calc_type) in input_sets:

            # Ensure inputsets that need the bandgap get it
            try:
                valid_input_set: VaspInputSet = input_sets[str(calc_type)](
                    structure, bandgap=bandgap
                )
            except TypeError:
                valid_input_set = input_sets[str(calc_type)](structure)

            # Checking K-Points
            # Calculations that use KSPACING will not have a .kpoints attr
            if valid_input_set.kpoints is not None:
                valid_num_kpts = valid_input_set.kpoints.num_kpts or np.prod(
                    valid_input_set.kpoints.kpts[0]
                )
                num_kpts = inputs.get("kpoints", {}).get("nkpoints", 0) or np.prod(
                    inputs.get("kpoints", {}).get("kpoints", [1, 1, 1])
                )
                data["kpts_ratio"] = num_kpts / valid_num_kpts
                if data["kpts_ratio"] < kpts_tolerance:
                    reasons.append(DeprecationMessage.KPTS)

            else:
                valid_kspacing = valid_input_set.incar.get("KSPACING", 0)
                if inputs.get("incar", {}).get("KSPACING"):
                    data["kspacing_delta"] = (
                        inputs["incar"].get("KSPACING") - valid_kspacing
                    )
                    # larger KSPACING means fewer k-points
                    if data["kspacing_delta"] > kspacing_tolerance:
                        warnings.append(
                            f"KSPACING is greater than input set: {data['kspacing_delta']}"
                            f" lower than {kspacing_tolerance} ",
                        )
                    elif data["kspacing_delta"] < kspacing_tolerance:
                        warnings.append(
                            f"KSPACING is lower than input set: {data['kspacing_delta']}"
                            f" lower than {kspacing_tolerance} ",
                        )

            # warn, but don't invalidate if wrong ISMEAR
            valid_ismear = valid_input_set.incar.get("ISMEAR", 1)
            curr_ismear = inputs.get("incar", {}).get("ISMEAR", 1)
            if curr_ismear != valid_ismear:
                warnings.append(
                    f"Inappropriate smearing settings. Set to {curr_ismear},"
                    f" but should be {valid_ismear}"
                )

            # Checking ENCUT
            encut = inputs.get("incar", {}).get("ENCUT")
            valid_encut = valid_input_set.incar["ENCUT"]
            data["encut_ratio"] = float(encut) / valid_encut  # type: ignore
            if data["encut_ratio"] < 1:
                reasons.append(DeprecationMessage.ENCUT)

            # U-value checks
            # NOTE: Reverting to old method of just using input.hubbards which is wrong in many instances
            input_hubbards = task_doc.input.hubbards

            if valid_input_set.incar.get("LDAU", False) or len(input_hubbards) > 0:
                # Assemble required input_set LDAU params into dictionary
                input_set_hubbards = dict(
                    zip(
                        valid_input_set.poscar.site_symbols,
                        valid_input_set.incar.get("LDAUU", []),
                    )
                )

                all_elements = list(
                    set(input_set_hubbards.keys()) | set(input_hubbards.keys())
                )
                diff_ldau_params = {
                    el: (input_set_hubbards.get(el, 0), input_hubbards.get(el, 0))
                    for el in all_elements
                    if not np.allclose(
                        input_set_hubbards.get(el, 0), input_hubbards.get(el, 0)
                    )
                }

                if len(diff_ldau_params) > 0:
                    reasons.append(DeprecationMessage.LDAU)
                    warnings.extend(
                        [
                            f"U-value for {el} should be {good} but was {bad}"
                            for el, (good, bad) in diff_ldau_params.items()
                        ]
                    )

            # Check the max upwards SCF step
            skip = abs(inputs.get("incar", {}).get("NLEMDL", -5)) - 1
            energies = [
                d["e_fr_energy"]
                for d in task_doc.calcs_reversed[0]["output"]["ionic_steps"][-1][
                    "electronic_steps"
                ]
            ]
            if len(energies) > skip:
                max_gradient = np.max(np.gradient(energies)[skip:])
                data["max_gradient"] = max_gradient
                if max_gradient > max_allowed_scf_gradient:
                    reasons.append(DeprecationMessage.MAX_SCF)
            else:
                warnings.append(
                    "Not enough electronic steps to compute valid gradient"
                    " and compare with max SCF gradient tolerance"
                )

            # Check for Am and Po elements. These currently do not have proper elemental entries
            # and will not get treated properly by the thermo builder.
            if ("Am" in chemsys) or ("Po" in chemsys):
                reasons.append(DeprecationMessage.MANUAL)

            # Check for magmom anomalies for specific elements
            if _magmom_check(task_doc, chemsys):
                reasons.append(DeprecationMessage.MAG)

        doc = ValidationDoc(
            task_id=task_doc.task_id,
            calc_type=calc_type,
            run_type=task_doc.run_type,
            valid=len(reasons) == 0,
            reasons=reasons,
            data=data,
            warnings=warnings,
        )
        return doc


def _magmom_check(task_doc, chemsys):
    """
    Checks for maximum magnetization values for specific elements.
    Returns True if the maximum absolute value outlined below is exceded for the associated element.
    """
    eles_max_vals = {"Cr": 5}

    for ele, max_val in eles_max_vals.items():
        if ele in chemsys:
            for site_num, mag in enumerate(
                task_doc.calcs_reversed[0]["output"]["outcar"]["magnetization"]
            ):
                if "structure" in task_doc.calcs_reversed[0]["output"]:
                    output_structure = task_doc.calcs_reversed[0]["output"]["structure"]
                else:
                    output_structure = task_doc.output.structure.as_dict()

                if output_structure["sites"][site_num]["label"] == ele:
                    if abs(mag["tot"]) > max_val:
                        return True

    return False


def _get_unsorted_symbol_set(structure: Structure):
    """
    Have to build structure_symbol set manually to ensure we get the right order since pymatgen sorts its symbol_set list
    """
    return list(
        {
            str(sp): 1 for site in structure for sp, v in site.species.items() if v != 0
        }.keys()
    )
