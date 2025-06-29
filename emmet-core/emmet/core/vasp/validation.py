"""Current MP tools to validate VASP calculations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
from pydantic import ConfigDict, Field, ImportString, field_validator
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.inputs import Kpoints
from pymatgen.io.vasp.sets import VaspInputSet

from emmet.core.base import EmmetBaseModel
from emmet.core.common import convert_datetime
from emmet.core.mpid import MPID
from emmet.core.settings import EmmetSettings
from emmet.core.tasks import TaskDoc
from emmet.core.utils import DocEnum, utcnow
from emmet.core.vasp.calc_types.enums import CalcType, TaskType
from emmet.core.vasp.task_valid import TaskDocument

if TYPE_CHECKING:
    from collections.abc import Sequence

SETTINGS = EmmetSettings()


class DeprecationMessage(DocEnum):
    MANUAL = "M", "Manual deprecation"
    SYMMETRY = (
        "S001",
        "Could not determine crystalline space group, needed for input set check.",
    )
    KPTS = "C001", "Too few KPoints"
    KSPACING = "C002", "KSpacing not high enough"
    ENCUT = "C002", "ENCUT too low"
    FORCES = "C003", "Forces too large"
    MAG = "C004", "At least one site magnetization is too large"
    POTCAR = (
        "C005",
        "At least one POTCAR used does not agree with the pymatgen input set",
    )
    CONVERGENCE = "E001", "Calculation did not converge"
    MAX_SCF = "E002", "Max SCF gradient too large"
    LDAU = "I001", "LDAU Parameters don't match the inputset"
    SET = ("I002", "Cannot validate due to missing or problematic input set")
    UNKNOWN = "U001", "Cannot validate due to unknown calc type"


class ValidationDoc(EmmetBaseModel):
    """
    Validation document for a VASP calculation
    """

    task_id: MPID = Field(..., description="The task_id for this validation document")
    valid: bool = Field(False, description="Whether this task is valid or not")
    last_updated: datetime = Field(
        description="Last updated date for this document",
        default_factory=utcnow,
    )
    reasons: list[DeprecationMessage | str] | None = Field(
        None, description="List of deprecation tags detailing why this task isn't valid"
    )
    warnings: list[str] = Field(
        [], description="List of potential warnings about this calculation"
    )
    data: dict = Field(
        description="Dictioary of data used to perform validation."
        " Useful for post-mortem analysis"
    )
    model_config = ConfigDict(extra="allow")
    nelements: int | None = Field(None, description="Number of elements.")
    symmetry_number: int | None = Field(
        None,
        title="Space Group Number",
        description="The spacegroup number for the lattice.",
    )

    @field_validator("last_updated", mode="before")
    @classmethod
    def handle_datetime(cls, v):
        return convert_datetime(cls, v)

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDoc | TaskDocument,
        kpts_tolerance: float = SETTINGS.VASP_KPTS_TOLERANCE,
        kspacing_tolerance: float = SETTINGS.VASP_KSPACING_TOLERANCE,
        input_sets: dict[str, ImportString] = SETTINGS.VASP_DEFAULT_INPUT_SETS,
        LDAU_fields: list[str] = SETTINGS.VASP_CHECKED_LDAU_FIELDS,
        max_allowed_scf_gradient: float = SETTINGS.VASP_MAX_SCF_GRADIENT,
        max_magmoms: dict[str, float] = SETTINGS.VASP_MAX_MAGMOM,
        potcar_stats: dict[CalcType, dict[str, str]] | None = None,
    ) -> "ValidationDoc":
        """
        Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

        Args:
            task_doc: the task document to process
            kpts_tolerance: the tolerance to allow kpts to lag behind the input set settings
            kspacing_tolerance:  the tolerance to allow kspacing to lag behind the input set settings
            input_sets: a dictionary of task_types -> pymatgen input set for validation
            pseudo_dir: directory of pseudopotential directory to ensure correct hashes
            LDAU_fields: LDAU fields to check for consistency
            max_allowed_scf_gradient: maximum uphill gradient allowed for SCF steps after the
                initial equillibriation period
            potcar_stats: Dictionary of potcar stat data. Mapping is calculation type -> potcar symbol -> hash value.
        """

        nelements = task_doc.nelements or None
        symmetry_number = task_doc.symmetry.number if task_doc.symmetry else None

        bandgap = task_doc.output.bandgap
        calc_type = task_doc.calc_type
        task_type = task_doc.task_type
        run_type = task_doc.run_type
        inputs = task_doc.orig_inputs
        chemsys = task_doc.chemsys
        calcs_reversed = [
            calc if not hasattr(calc, "model_dump") else calc.model_dump()
            for calc in task_doc.calcs_reversed
        ]

        if calcs_reversed[0].get("input", {}).get("structure", None):
            structure = calcs_reversed[0]["input"]["structure"]
        else:
            structure = task_doc.input.structure or task_doc.output.structure

        if isinstance(structure, dict):
            structure = Structure.from_dict(structure)

        reasons = []
        data = {}  # type: ignore
        warnings: list[str] = []

        if str(calc_type) in input_sets:
            try:
                valid_input_set = _get_input_set(
                    run_type, task_type, calc_type, structure, input_sets, bandgap
                )

            except (TypeError, KeyError, ValueError):
                reasons.append(DeprecationMessage.SET)
                valid_input_set = None

            try:
                # Sometimes spglib can't determine space group with the default
                # `symprec` and `angle_tolerance`. In these cases,
                # `Structure.get_space_group_info()` fails
                valid_input_set.structure.get_space_group_info()
            except Exception:
                reasons.append(DeprecationMessage.SYMMETRY)
                valid_input_set = None

            if valid_input_set:
                # Checking POTCAR summary_stats if a directory is supplied
                if potcar_stats:
                    if _potcar_stats_check(task_doc, potcar_stats):
                        if task_type in [
                            TaskType.NSCF_Line,
                            TaskType.NSCF_Uniform,
                            TaskType.DFPT_Dielectric,
                            TaskType.Dielectric,
                        ]:
                            warnings.append(DeprecationMessage.POTCAR.__doc__)  # type: ignore
                        else:
                            reasons.append(DeprecationMessage.POTCAR)

                # Checking K-Points
                # Calculations that use KSPACING will not have a .kpoints attr

                if task_type != TaskType.NSCF_Line:
                    # Not validating k-point data for line-mode calculations as constructing
                    # the k-path is too costly for the builder and the uniform input set is used.

                    if valid_input_set.kpoints is not None:
                        if _kpoint_check(
                            valid_input_set,
                            inputs,
                            calcs_reversed,
                            data,
                            kpts_tolerance,
                        ):
                            reasons.append(DeprecationMessage.KPTS)

                    else:
                        # warnings
                        _kspacing_warnings(
                            valid_input_set, inputs, data, warnings, kspacing_tolerance
                        )

                # warn, but don't invalidate if wrong ISMEAR
                valid_ismear = valid_input_set.incar.get("ISMEAR", 1)
                incar = inputs.get("incar", {})
                curr_ismear = incar.get("ISMEAR", 1)
                if curr_ismear != valid_ismear:
                    warnings.append(
                        f"Inappropriate smearing settings. Set to {curr_ismear},"
                        f" but should be {valid_ismear}"
                    )

                # Checking ENCUT
                encut = incar.get("ENCUT")
                valid_encut = valid_input_set.incar["ENCUT"]
                data["encut_ratio"] = float(encut) / valid_encut  # type: ignore
                if data["encut_ratio"] < 1:
                    reasons.append(DeprecationMessage.ENCUT)

                # U-value checks
                if _u_value_checks(task_doc, valid_input_set, warnings):
                    reasons.append(DeprecationMessage.LDAU)

                # Check the max upwards SCF step
                if _scf_upward_check(
                    calcs_reversed, inputs, data, max_allowed_scf_gradient, warnings
                ):
                    reasons.append(DeprecationMessage.MAX_SCF)

                # Check for Am and Po elements. These currently do not have proper elemental entries
                # and will not get treated properly by the thermo builder.
                if ("Am" in chemsys) or ("Po" in chemsys):
                    reasons.append(DeprecationMessage.MANUAL)

                # Check for magmom anomalies for specific elements
                if _magmom_check(calcs_reversed, structure, max_magmoms=max_magmoms):
                    reasons.append(DeprecationMessage.MAG)
            else:
                if "Unrecognized" in str(calc_type):
                    reasons.append(DeprecationMessage.UNKNOWN)
                else:
                    reasons.append(DeprecationMessage.SET)

        doc = ValidationDoc(
            task_id=task_doc.task_id,
            calc_type=calc_type,
            run_type=task_doc.run_type,
            valid=len(reasons) == 0,
            reasons=reasons,
            data=data,
            warnings=warnings,
            nelements=nelements,
            symmetry_number=symmetry_number,
        )

        return doc


def _get_input_set(run_type, task_type, calc_type, structure, input_sets, bandgap):
    # Ensure inputsets get proper additional input values
    if "SCAN" in run_type.value:
        valid_input_set: VaspInputSet = input_sets[str(calc_type)](structure, bandgap=bandgap)  # type: ignore
    elif task_type == TaskType.NSCF_Uniform or task_type == TaskType.NSCF_Line:
        # Constructing the k-path for line-mode calculations is too costly, so
        # the uniform input set is used instead and k-points are not checked.
        valid_input_set = input_sets[str(calc_type)](structure, mode="uniform")

    elif task_type == TaskType.NMR_Electric_Field_Gradient:
        valid_input_set = input_sets[str(calc_type)](structure, mode="efg")

    else:
        valid_input_set = input_sets[str(calc_type)](structure)

    return valid_input_set


def _scf_upward_check(calcs_reversed, inputs, data, max_allowed_scf_gradient, warnings):
    skip = abs(inputs.get("incar", {}).get("NELMDL", -5)) - 1
    energies = [
        d["e_fr_energy"]
        for d in calcs_reversed[0]["output"]["ionic_steps"][-1]["electronic_steps"]
    ]
    if len(energies) > skip:
        max_gradient = np.max(np.gradient(energies)[skip:])
        data["max_gradient"] = max_gradient
        if max_gradient > max_allowed_scf_gradient:
            return True
    else:
        warnings.append(
            "Not enough electronic steps to compute valid gradient"
            " and compare with max SCF gradient tolerance"
        )
        return False


def _u_value_checks(task_doc, valid_input_set, warnings):
    # NOTE: Reverting to old method of just using input.hubbards which is wrong in many instances
    input_hubbards = {} if task_doc.input.hubbards is None else task_doc.input.hubbards

    if valid_input_set.incar.get("LDAU", False) or len(input_hubbards) > 0:
        # Assemble required input_set LDAU params into dictionary
        input_set_hubbards = dict(
            zip(
                valid_input_set.poscar.site_symbols,
                valid_input_set.incar.get("LDAUU", []),
            )
        )

        all_elements = list(set(input_set_hubbards.keys()) | set(input_hubbards.keys()))
        diff_ldau_params = {
            el: (input_set_hubbards.get(el, 0), input_hubbards.get(el, 0))
            for el in all_elements
            if not np.allclose(input_set_hubbards.get(el, 0), input_hubbards.get(el, 0))
        }

        if len(diff_ldau_params) > 0:
            warnings.extend(
                [
                    f"U-value for {el} should be {good} but was {bad}"
                    for el, (good, bad) in diff_ldau_params.items()
                ]
            )
            return True

    return False


def _kpoint_check(input_set, inputs, calcs_reversed, data, kpts_tolerance):
    """
    Checks to make sure the total number of kpoints is correct
    """
    valid_num_kpts = input_set.kpoints.num_kpts or np.prod(input_set.kpoints.kpts[0])

    if calcs_reversed:
        input_dict = calcs_reversed[0].get("input", {})

        if not input_dict:
            input_dict = inputs

    else:
        input_dict = inputs

    kpoints = input_dict.get("kpoints", {})
    if isinstance(kpoints, Kpoints):
        kpoints = kpoints.as_dict()
    elif kpoints is None:
        kpoints = {}
    num_kpts = kpoints.get("nkpoints", 0) or np.prod(kpoints.get("kpoints", [1, 1, 1]))

    data["kpts_ratio"] = num_kpts / valid_num_kpts
    return data["kpts_ratio"] < kpts_tolerance


def _kspacing_warnings(input_set, inputs, data, warnings, kspacing_tolerance):
    """
    Issues warnings based on KSPACING values
    """
    valid_kspacing = input_set.incar.get("KSPACING", 0)
    if kspacing := inputs.get("incar", {}).get("KSPACING"):
        data["kspacing_delta"] = kspacing - valid_kspacing
        # larger KSPACING means fewer k-points
        if data["kspacing_delta"] > kspacing_tolerance:
            warnings.append(
                f"KSPACING is greater than input set: {data['kspacing_delta']}"
                f" lower than {kspacing_tolerance} "
            )
        elif data["kspacing_delta"] < kspacing_tolerance:
            warnings.append(
                f"KSPACING is lower than input set: {data['kspacing_delta']}"
                f" lower than {kspacing_tolerance} "
            )


def _potcar_stats_check(
    task_doc,
    potcar_stats: dict,
    exclude_keys: Sequence[str] | None = ["sha256", "copyr"],
):
    """
    Checks to make sure the POTCAR summary stats is equal to the correct
    value from the pymatgen input set.
    """
    data_tol = 1.0e-6
    excl: set[str] = set([k.lower() for k in (exclude_keys or [])])

    try:
        potcar_details = task_doc.calcs_reversed[0].model_dump()["input"]["potcar_spec"]

    except KeyError:
        # Assume it is an old calculation without potcar_spec data and treat it as passing POTCAR hash check
        return False

    use_legacy_hash_check = False
    if any(entry.get("summary_stats", None) is None for entry in potcar_details):
        # potcar_spec doesn't include summary_stats kwarg needed to check potcars
        # fall back to header hash checking
        use_legacy_hash_check = True

    all_match = True
    for entry in potcar_details:
        if not entry["titel"]:
            all_match = False
            break

        symbol = entry["titel"].split(" ")[1]
        ref_summ_stats = potcar_stats[str(task_doc.calc_type)].get(symbol, None)

        if not ref_summ_stats:
            # Symbol differs from reference set - deprecate
            all_match = False
            break

        if use_legacy_hash_check:
            all_match = any(
                all(
                    entry[key] == ref_stat[key]
                    for key in (
                        "hash",
                        "titel",
                    )
                )
                for ref_stat in ref_summ_stats
            )

        else:
            entry_keys = {
                key: set([k.lower() for k in entry["summary_stats"]["keywords"][key]])
                - excl
                for key in ["header", "data"]
            }
            all_match = False
            for ref_stat in ref_summ_stats:
                ref_keys = {
                    key: set([k.lower() for k in ref_stat["keywords"][key]]) - excl
                    for key in ["header", "data"]
                }

                key_match = all(entry_keys[k] == v for k, v in ref_keys.items())

                data_match = False
                if key_match:
                    data_match = all(
                        abs(
                            ref_stat["stats"][key][stat]
                            - entry["summary_stats"]["stats"][key][stat]
                        )
                        < data_tol
                        for stat in ["MEAN", "ABSMEAN", "VAR", "MIN", "MAX"]
                        for key in ["header", "data"]
                    )
                all_match = key_match and data_match

                if all_match:
                    # Found at least one match to reference POTCAR summary stats,
                    # that suffices for the check
                    break

        if not all_match:
            break

    return not all_match


def _magmom_check(
    calcs_reversed: list, structure: Structure, max_magmoms: dict[str, float]
):
    """
    Checks for maximum magnetization values for specific elements.
    Returns True if the maximum absolute value outlined below is exceded for the associated element.
    """
    if (outcar := calcs_reversed[0]["output"]["outcar"]) and (
        mag_info := outcar.get("magnetization", [])
    ):
        return any(
            abs(mag_info[isite].get("tot", 0.0))
            > abs(max_magmoms.get(site.label, np.inf))
            for isite, site in enumerate(structure)
        )
    return False


def _get_unsorted_symbol_set(structure: Structure):
    """
    Have to build structure_symbol set manually to ensure
    we get the right order since pymatgen sorts its symbol_set list.
    """
    return list(
        {
            str(sp): 1 for site in structure for sp, v in site.species.items() if v != 0
        }.keys()
    )
