from datetime import datetime
from typing import Dict, List, Union

import numpy as np
from pydantic import BaseModel, Field, PyObject
from pymatgen.core import Structure

from emmet.core import SETTINGS
from emmet.core.mpid import MPID
from emmet.core.utils import DocEnum
from emmet.core.vasp.task import TaskDocument


class DeprecationMessage(DocEnum):
    MANUAL = "M", "manual deprecation"
    KPTS = "C001", "Too few KPoints"
    KSPACING = "C002", "KSpacing not high enough"
    ENCUT = "C002", "ENCUT too low"
    FORCES = "C003", "Forces too large"
    CONVERGENCE = "E001", "Calculation did not converge"
    MAX_SCF = "E002", "Max SCF gradient too large"
    LDAU = "I001", "LDAU Parameters don't match the inputset"


class ValidationDoc(BaseModel):
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

        reasons = []
        data = {}
        warnings = []

        if str(calc_type) in input_sets:

            # Ensure inputsets that need the bandgap get it
            try:
                valid_input_set = input_sets[str(calc_type)](structure, bandgap=bandgap)
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
                        reasons.append(DeprecationMessage.KSPACING)
                    elif data["kspacing_delta"] < kspacing_tolerance:
                        warnings.append(
                            f"KSPACING is lower than input set: {data['kspacing_delta']}"
                            " lower than {kspacing_tolerance} ",
                        )

            # warn, but don't invalidate if wrong ISMEAR
            valid_ismear = valid_input_set.incar.get("ISMEAR", 1)
            curr_ismear = inputs.get("incar", {}).get("ISMEAR", 1)
            if curr_ismear != valid_ismear:
                warnings.append(
                    f"Inappropriate smearing settings. Set to {curr_ismear},"
                    " but should be {valid_ismear}"
                )

            # Checking ENCUT
            encut = inputs.get("incar", {}).get("ENCUT")
            valid_encut = valid_input_set.incar["ENCUT"]
            data["encut_ratio"] = float(encut) / valid_encut  # type: ignore
            if data["encut_ratio"] < 1:
                reasons.append(DeprecationMessage.ENCUT)

            # Checking U-values
            if valid_input_set.incar.get("LDAU"):
                # Assemble actual input LDAU params into dictionary to account for possibility
                # of differing order of elements.
                structure_set_symbol_set = _get_unsorted_symbol_set(structure)
                inputs_ldau_fields = [structure_set_symbol_set] + [
                    inputs.get("incar", {}).get(k, []) for k in LDAU_fields
                ]
                input_ldau_params = {d[0]: d[1:] for d in zip(*inputs_ldau_fields)}

                # Assemble required input_set LDAU params into dictionary
                input_set_symbol_set = _get_unsorted_symbol_set(
                    valid_input_set.poscar.structure
                )
                input_set_ldau_fields = [input_set_symbol_set] + [
                    valid_input_set.incar.get(k) for k in LDAU_fields
                ]
                input_set_ldau_params = {
                    d[0]: d[1:] for d in zip(*input_set_ldau_fields)
                }

                if any(
                    input_set_ldau_params[el] != input_params
                    for el, input_params in input_ldau_params.items()
                ):
                    reasons.append(DeprecationMessage.LDAU)

        # Check the max upwards SCF step
        skip = inputs.get("incar", {}).get("NLEMDL")
        energies = [
            d["e_fr_energy"]
            for d in task_doc.calcs_reversed[0]["output"]["ionic_steps"][-1][
                "electronic_steps"
            ]
        ]
        max_gradient = np.max(np.gradient(energies)[skip:])
        data["max_gradient"] = max_gradient
        if max_gradient > max_allowed_scf_gradient:
            reasons.append(DeprecationMessage.MAX_SCF)

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


def _get_unsorted_symbol_set(structure: Structure):
    """
    Have to build structure_symbol set manually to ensure we get the right order since pymatgen sorts its symbol_set list
    """
    return list(
        {
            str(sp): 1 for site in structure for sp, v in site.species.items() if v != 0
        }.keys()
    )
