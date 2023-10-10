from datetime import datetime
from typing import Dict, List, Union, Optional
import numpy as np
from pydantic import Field, PyObject
from pathlib import Path
from monty.os.path import zpath

from pymatgen.io.vasp.sets import VaspInputSet
from pymatgen.io.vasp.sets import MPMetalRelaxSet ########################################################
from pymatgen.io.vasp.inputs import Potcar

from emmet.core.tasks import TaskDoc
from emmet.core.settings import EmmetSettings
from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID
from emmet.core.utils import DocEnum
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.calc_types.enums import CalcType, TaskType
from emmet.core.vasp.calc_types import RunType, calc_type, run_type, task_type

from emmet.core.vasp.validation.check_incar import _check_incar
from emmet.core.vasp.validation.check_common_errors import _check_common_errors
from emmet.core.vasp.validation.check_kpoints_kspacing import _check_kpoints_kspacing


SETTINGS = EmmetSettings()


## TODO: check for surface/slab calculations. Especially necessary for external calcs.
## TODO: implement check to make sure calcs are within some amount (e.g. 250 meV) of the convex hull in the MPDB



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

    reasons: List[str] = Field(
        None, description="List of deprecation tags detailing why this task isn't valid"
    )
    
    warnings: List[str] = Field(
        [], description="List of potential warnings about this calculation")

    # data: Dict = Field(
    #     description="Dictionary of data used to perform validation."
    #     " Useful for post-mortem analysis"
    # )

    class Config:
        extra = "allow"

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDocument,
        kpts_tolerance: float = SETTINGS.VASP_KPTS_TOLERANCE,
        kspacing_tolerance: float = SETTINGS.VASP_KSPACING_TOLERANCE,
        input_sets: Dict[str, PyObject] = SETTINGS.VASP_DEFAULT_INPUT_SETS,
        LDAU_fields: List[str] = SETTINGS.VASP_CHECKED_LDAU_FIELDS, ### Unused
        max_allowed_scf_gradient: float = SETTINGS.VASP_MAX_SCF_GRADIENT,
        potcar_hashes: Optional[Dict[CalcType, Dict[str, str]]] = None,
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
                initial equillibriation period. Note this is in eV per atom.
            potcar_hashes: Dictionary of potcar hash data. Mapping is calculation type -> potcar symbol -> hash value.
        """        
        
        bandgap = task_doc.output.bandgap
        calcs_reversed = task_doc.calcs_reversed
        calcs_reversed = [calc.dict() for calc in calcs_reversed] # convert to dictionary to use built-in `.get()` method       ###################################################
        
        parameters = task_doc.input.parameters # used for most input tag checks (as this is more reliable than examining the INCAR file directly in most cases)
        incar = calcs_reversed[0]['input']['incar'] # used for INCAR tag checks where you need to look at the actual INCAR (semi-rare)
        if task_doc.orig_inputs == None:
            orig_inputs = {}
        else:
            orig_inputs = task_doc.orig_inputs.dict()
            if orig_inputs["kpoints"] != None:
                orig_inputs["kpoints"] = orig_inputs["kpoints"].as_dict()
            
        
        ionic_steps = calcs_reversed[0]['output']['ionic_steps']
        nionic_steps = len(ionic_steps)
        
        try:
            potcar = Potcar.from_file(zpath("POTCAR")) #############################################################################
        except:
            potcar = None
        
        
        calc_type = _get_calc_type(calcs_reversed, orig_inputs)
        task_type = _get_task_type(calcs_reversed, orig_inputs)
        run_type = _get_run_type(calcs_reversed)        
        
        num_ionic_steps_to_avg_drift_over = 3 ########################################################## maybe move to settings
        fft_grid_tolerance = 0.9 ####################################################################### maybe move to settings
        allow_kpoint_shifts = False #################################################################### maybe move to settings
        allow_explicit_kpoint_mesh = "auto" # or True or False ######################################### maybe move to settings
        if allow_explicit_kpoint_mesh == "auto":
            if "NSCF" in calc_type.name:
                allow_explicit_kpoint_mesh = True
            else:
                allow_explicit_kpoint_mesh = False
        
        chemsys = task_doc.chemsys
        
        vasp_version = calcs_reversed[0]['vasp_version']
        vasp_version = vasp_version.split(".")
        vasp_version = vasp_version[0] + "." + vasp_version[1] + "." + vasp_version[2]
        vasp_major_version = int(vasp_version.split(".")[0])
        vasp_minor_version = int(vasp_version.split(".")[1])
        vasp_patch_version = int(vasp_version.split(".")[2])

        
        if calcs_reversed[0].get("input", {}).get("structure", None):
            structure = calcs_reversed[0]["input"]["structure"]
        else:
            structure = task_doc.input.structure or task_doc.output.structure
            

        reasons = []
        # data = {}  # type: ignore
        warnings: List[str] = []
        
        
        if run_type not in ["GGA", "GGA+U", "PBE", "PBE+U", "R2SCAN"]:
            reasons.append(f"FUNCTIONAL --> Functional {run_type} not currently accepted.")
                
        try:
            valid_input_set = _get_input_set(
                run_type, task_type, calc_type, structure, input_sets, bandgap
            )
        except Exception as e:
            reasons.append("NO MATCHING MP INPUT SET --> no matching MP input set was found. If you believe this to be a mistake, please create a GitHub issue.")
            valid_input_set = None

            print(f"Error while finding MP input set: {e}.")

            
            
        if parameters == {} or parameters == None:
            reasons.append("CAN NOT PROPERLY PARSE CALCULATION --> Issue parsing input parameters from the vasprun.xml file.")
        elif valid_input_set:

            if potcar_hashes:
                _check_potcars(reasons, warnings, calcs_reversed, calc_type, potcar_hashes)
            
            ## TODO: check for surface/slab calculations!!!!!!

            reasons = _check_vasp_version(
                reasons, 
                vasp_version, 
                vasp_major_version, 
                vasp_minor_version, 
                vasp_patch_version, 
                parameters,
                incar
            )    
                
            reasons = _check_common_errors(
                reasons, 
                warnings, 
                task_doc, 
                calcs_reversed,
                parameters, 
                incar, 
                structure, 
                max_allowed_scf_gradient, 
                ionic_steps,
                num_ionic_steps_to_avg_drift_over,
            )
            
            reasons = _check_kpoints_kspacing(
                reasons,
                task_type,
                parameters,
                kpts_tolerance, 
                valid_input_set, 
                calcs_reversed, 
                allow_explicit_kpoint_mesh, 
                allow_kpoint_shifts,
                structure,
            )
            
            reasons = _check_incar(
                reasons,
                warnings,
                valid_input_set, 
                structure, 
                task_doc, 
                calcs_reversed,
                ionic_steps,
                nionic_steps, 
                parameters, 
                incar, 
                potcar, 
                vasp_major_version, 
                vasp_minor_version, 
                vasp_patch_version,
                task_type,
                fft_grid_tolerance,
            )

            
        # Unsure about what might be a better way to do this...
        task_id = task_doc.task_id if task_doc.task_id != None else -1
    
        validation_doc = ValidationDoc(
            task_id=task_id,
            calc_type=calc_type,
            run_type=run_type,
            task_type=task_type,
            valid=len(reasons) == 0,
            reasons=reasons,
            # data=data,
            warnings=warnings,
        )

        return validation_doc

    @classmethod
    def from_directory(
        cls,
        dir_name: Union[Path, str],
        kpts_tolerance: float = SETTINGS.VASP_KPTS_TOLERANCE,
        kspacing_tolerance: float = SETTINGS.VASP_KSPACING_TOLERANCE,
        input_sets: Dict[str, PyObject] = SETTINGS.VASP_DEFAULT_INPUT_SETS,
        LDAU_fields: List[str] = SETTINGS.VASP_CHECKED_LDAU_FIELDS, ### Unused
        max_allowed_scf_gradient: float = SETTINGS.VASP_MAX_SCF_GRADIENT,
        potcar_hashes: Optional[Dict[CalcType, Dict[str, str]]] = None,
    ) -> "ValidationDoc":
        """
        Determines if a calculation is valid based on expected input parameters from a pymatgen inputset

        Args:
            dir_name: the directory containing the calculation files to process
            kpts_tolerance: the tolerance to allow kpts to lag behind the input set settings
            kspacing_tolerance:  the tolerance to allow kspacing to lag behind the input set settings
            input_sets: a dictionary of task_types -> pymatgen input set for validation
            pseudo_dir: directory of pseudopotential directory to ensure correct hashes
            LDAU_fields: LDAU fields to check for consistency
            max_allowed_scf_gradient: maximum uphill gradient allowed for SCF steps after the
                initial equillibriation period. Note this is in eV per atom.
            potcar_hashes: Dictionary of potcar hash data. Mapping is calculation type -> potcar symbol -> hash value.
        """
        try: 
            task_doc = TaskDoc.from_directory(
                dir_name = dir_name,
                volumetric_files = (),
            )
            validation_doc = ValidationDoc.from_task_doc(
                task_doc = task_doc,
                kpts_tolerance = kpts_tolerance,
                kspacing_tolerance = kspacing_tolerance,
                input_sets = input_sets,
                LDAU_fields = LDAU_fields, ### Unused
                max_allowed_scf_gradient = max_allowed_scf_gradient,
                potcar_hashes = potcar_hashes,
            )

            return validation_doc
        except Exception as e:
            print(e)
            if "no vasp files found" in str(e).lower():
                raise Exception(f"NO CALCULATION FOUND --> {dir_name} is not a VASP calculation directory.")
            else:
                raise Exception(f"CAN NOT PARSE CALCULATION --> Issue parsing results. This often means your calculation did not complete. The error stack reads: \n {e}")
            



def _get_input_set(run_type, task_type, calc_type, structure, input_sets, bandgap):
    
    ## TODO: For every input set key in emmet.core.settings.VASP_DEFAULT_INPUT_SETS,
    ##       with "GGA" in it, create an equivalent dictionary item with "PBE" instead.
    ## In the mean time, the below workaround is used.
    gga_pbe_structure_opt_calc_types = [
        CalcType.GGA_Structure_Optimization, 
        CalcType.GGA_U_Structure_Optimization, 
        CalcType.PBE_Structure_Optimization, 
        CalcType.PBE_U_Structure_Optimization,
    ]
    
    # Ensure inputsets get proper additional input values
    if "SCAN" in run_type.value:
        valid_input_set: VaspInputSet = input_sets[str(calc_type)](structure, bandgap=bandgap)  # type: ignore

    elif task_type == TaskType.NSCF_Uniform:
        valid_input_set = input_sets[str(calc_type)](structure, mode="uniform")
    elif task_type == TaskType.NSCF_Line:
        valid_input_set = input_sets[str(calc_type)](structure, mode="line")
    
    elif "dielectric" in str(task_type).lower():
        valid_input_set = input_sets[str(calc_type)](structure, lepsilon = True)

    elif task_type == TaskType.NMR_Electric_Field_Gradient:
        valid_input_set = input_sets[str(calc_type)](structure, mode="efg")
    elif task_type == TaskType.NMR_Nuclear_Shielding:
        valid_input_set = input_sets[str(calc_type)](structure, mode="cs") # Is this correct? Someone more knowledgeable either fix this or remove this comment if it is correct please!

    elif calc_type in gga_pbe_structure_opt_calc_types:
        if bandgap == 0:
            valid_input_set = MPMetalRelaxSet(structure)
        else:
            valid_input_set = input_sets[str(calc_type)](structure)

    else:
        valid_input_set = input_sets[str(calc_type)](structure)
        
    return valid_input_set


def _check_potcars(reasons, warnings, calcs_reversed, calc_type, valid_potcar_hashes):
    """
    Checks to make sure the POTCAR is equivalent to the correct POTCAR from the
    pymatgen input set.
    """
    
    ### TODO: Update potcar checks. Whether using hashing or not!
    ##################################### TODO: Only create a warning for NSCF / dielectric / DFPT / any other NSCF calc types

    try:
        potcar_details = calcs_reversed[0]["input"]["potcar_spec"]

        incorrect_potcars = []
        for entry in potcar_details:
            symbol = entry["titel"].split(" ")[1]
            hash = valid_potcar_hashes[str(calc_type)].get(symbol, None)

            if not hash or hash != entry["hash"]:
                incorrect_potcars.append(symbol)


        if len(incorrect_potcars) > 0:
            # format error string
            incorrect_potcars = [potcar.split("_")[0] for potcar in incorrect_potcars]
            if len(incorrect_potcars) == 2:
                incorrect_potcars = ", ".join(incorrect_potcars[:-1]) + f" and {incorrect_potcars[-1]}"
            elif len(incorrect_potcars) >= 3:
                incorrect_potcars = ", ".join(incorrect_potcars[:-1]) + "," + f" and {incorrect_potcars[-1]}"

            reasons.append(f"PSEUDOPOTENTIALS --> Incorrect POTCAR files were used for {incorrect_potcars}. "
                "Alternatively, our potcar checker may have an issue--please create a GitHub issue if you "
                "believe the POTCARs used are correct."
            )

    except KeyError:
        # Assume it is an old calculation without potcar_spec data and treat it as failing the POTCAR check
        reasons.append("Old version of Emmet --> potcar_spec is not saved in TaskDoc and cannot be validated. Hence, it is marked as invalid")


def _check_vasp_version(reasons, vasp_version, vasp_major_version, vasp_minor_version, vasp_patch_version, parameters, incar):
    if vasp_major_version == 6:
        pass
    elif (vasp_major_version == 5) and ("METAGGA" in incar.keys()) and (parameters.get("ISPIN", 1) == 2):
        reasons.append("POTENTIAL BUG --> We believe that there may be a bug with spin-polarized calculations for METAGGAs " \
                       "in some versions of VASP 5. Please create a new GitHub issue if you believe this " \
                       "is not the case and we will consider changing this check!")
    elif (vasp_major_version == 5) and (vasp_minor_version == 4) and (vasp_patch_version == 4):
        pass
    else:
        reasons.append(f"VASP VERSION --> This calculation is using VASP version {vasp_version}, but we only allow versions 5.4.4 and >=6.0.0 (as of July 2023).")
    return reasons


def _get_run_type(calcs_reversed) -> RunType:
    params = calcs_reversed[0].get("input", {}).get("parameters", {})
    incar = calcs_reversed[0].get("input", {}).get("incar", {})
    return run_type({**params, **incar})


def _get_task_type(calcs_reversed, orig_inputs):
    inputs = (
        calcs_reversed[0].get("input", {})
        if len(calcs_reversed) > 0
        else orig_inputs
    )
    return task_type(inputs)


def _get_calc_type(calcs_reversed, orig_inputs):
    inputs = (
        calcs_reversed[0].get("input", {})
        if len(calcs_reversed) > 0
        else orig_inputs
    )
    params = calcs_reversed[0].get("input", {}).get("parameters", {})
    incar = calcs_reversed[0].get("input", {}).get("incar", {})

    return calc_type(inputs, {**params, **incar})