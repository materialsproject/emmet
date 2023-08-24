from datetime import datetime
from typing import Dict, List, Union, Optional

import numpy as np
from pydantic import Field, PyObject
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.sets import VaspInputSet
from pymatgen.io.vasp.inputs import Potcar

from emmet.core.settings import EmmetSettings
from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID
from emmet.core.utils import DocEnum
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.calc_types.enums import CalcType, TaskType
from emmet.core.vasp.calc_types import RunType, calc_type, run_type, task_type

from pymatgen.io.vasp.sets import MPMetalRelaxSet ########################################################

from monty.os.path import zpath

from emmet.core.vasp.validation.check_incar import _check_incar
from emmet.core.vasp.validation.check_common_errors import _check_common_errors
from emmet.core.vasp.validation.check_kpoints_kspacing import _check_kpoints_kspacing

SETTINGS = EmmetSettings()


## TODO: Update potcar checks. Whether using hashing or not!
## TODO: check for surface/slab calculations. Especially necessary for external calcs.


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

    # reasons: List[Union[DeprecationMessage, str]] = Field(
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
        LDAU_fields: List[str] = SETTINGS.VASP_CHECKED_LDAU_FIELDS,
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
                initial equillibriation period
            potcar_hashes: Dictionary of potcar hash data. Mapping is calculation type -> potcar symbol -> hash value.
        """        
        
        
        bandgap = task_doc.output.bandgap
        # bandgap = task_doc.bandgap
        calcs_reversed = task_doc.calcs_reversed
        calcs_reversed = [calc.dict() for calc in calcs_reversed] # convert to dictionary to use built-in `.get()` method       
        
        parameters = task_doc.input.parameters # used for most INCAR checks 
        incar = calcs_reversed[0]['input']['incar']
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
        task_type = _get_task_type(orig_inputs)
        run_type = _get_run_type(calcs_reversed)
        
        
        
        
        
#         calc_type = task_doc.calc_type
                
#         # ### get relevant valid (i.e. MP-compliant) input set
#         # if parameters.get("NSW",0) == 0 or nionic_steps <= 1:
#         #     task_type = TaskType("Static")
#         # else:
#         #     task_type = TaskType("Structure Optimization")
#         # run_type = calc_type + task_type
        
#         task_type = task_doc.task_type # be careful, as task_type function from Emmet not adequately broad for external calcs
#         run_type = task_doc.run_type #####################################
        
        
        
        allow_kpoint_shifts = False #############################################################################################
        allow_explicit_kpoint_mesh = "auto" # or True or False #############################################################################################
        if allow_explicit_kpoint_mesh == "auto":
            if "NSCF" in calc_type.name:
                allow_explicit_kpoint_mesh = True
            else:
                allow_explicit_kpoint_mesh = False
        num_ionic_steps_to_avg_drift_over = 3
        
        
        
        
        
        chemsys = task_doc.chemsys
        
        vasp_version = calcs_reversed[0]['vasp_version']
        vasp_version = vasp_version.split(".")
        vasp_version = vasp_version[0] + "." + vasp_version[1] + "." + vasp_version[2]
        vasp_major_version = int(vasp_version.split(".")[0])
        vasp_minor_version = int(vasp_version.split(".")[1])
        vasp_patch_version = int(vasp_version.split(".")[2])

        
        if calcs_reversed[0].get("input", {}).get("structure", None):
            # structure = Structure.from_dict(calcs_reversed[0]["input"]["structure"])
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
            reasons.append("MP INPUT SET --> There is no matching MP input set for this calculation.")
            valid_input_set = None
            print(e)
            
            
            
        if parameters == {} or parameters == None:
            reasons.append("CAN NOT PROPERLY PARSE CALCULATION --> Issue parsing input parameters from the vasprun.xml file.")
        elif valid_input_set:
            
            
            ## TODO: check for surface/slab calculations!!!!!!

            reasons = _check_vasp_version(
                reasons, 
                vasp_version, 
                vasp_major_version, 
                vasp_minor_version, 
                vasp_patch_version, 
                parameters,
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
            )
            
        else:
            reasons.append("NO MATCHING MP INPUT SET --> no matching MP input set was found. If you believe this to be a mistake, please create a GitHub issue.")
            
        # Unsure about what might be a better way to do this...
        task_id = task_doc.task_id if task_doc.task_id != None else -1
    
        doc = ValidationDoc(
            task_id=task_id,
            calc_type=calc_type,
            run_type=run_type,
            valid=len(reasons) == 0,
            reasons=reasons,
            # data=data,
            warnings=warnings,
        )

        return doc


def _get_input_set(run_type, task_type, calc_type, structure, input_sets, bandgap):
    
    gga_pbe_structure_opt_calc_types = [
        CalcType.GGA_Structure_Optimization, 
        CalcType.GGA_U_Structure_Optimization, 
        CalcType.PBE_Structure_Optimization, 
        CalcType.PBE_U_Structure_Optimization,
    ]
    
    # Ensure inputsets get proper additional input values
    if "SCAN" in run_type.value:
        valid_input_set: VaspInputSet = input_sets[str(calc_type)](structure, bandgap=bandgap)  # type: ignore

    # elif task_type == TaskType.NSCF_Uniform or task_type == TaskType.NSCF_Line:
    #     # Constructing the k-path for line-mode calculations is too costly, so
    #     # the uniform input set is used instead and k-points are not checked.
    #     valid_input_set = input_sets[str(calc_type)](structure, mode="uniform")
    elif task_type == TaskType.NSCF_Uniform:
        valid_input_set = input_sets[str(calc_type)](structure, mode="uniform")
    elif task_type == TaskType.NSCF_Line:
        valid_input_set = input_sets[str(calc_type)](structure, mode="line")

    elif task_type == TaskType.NMR_Electric_Field_Gradient:
        valid_input_set = input_sets[str(calc_type)](structure, mode="efg")
    elif task_type == TaskType.NMR_Nuclear_Shielding: #########################################################################
        valid_input_set = input_sets[str(calc_type)](structure, mode="cs")

    elif calc_type in gga_pbe_structure_opt_calc_types:
        if bandgap == 0:
            valid_input_set = MPMetalRelaxSet(structure)
        else:
            valid_input_set = input_sets[str(calc_type)](structure)
    else:
        valid_input_set = input_sets[str(calc_type)](structure)
        
    return valid_input_set



def _potcar_hash_check(task_doc, potcar_hashes):
    """
    Checks to make sure the POTCAR hash is equal to the correct value from the
    pymatgen input set.
    """
    
    ### TODO: Update potcar checks. Whether using hashing or not!

    try:
        potcar_details = task_doc.calcs_reversed[0]["input"]["potcar_spec"]

        all_match = True

        for entry in potcar_details:
            symbol = entry["titel"].split(" ")[1]
            hash = potcar_hashes[str(task_doc.calc_type)].get(symbol, None)

            if not hash or hash != entry["hash"]:
                all_match = False
                break

        return not all_match

    except KeyError:
        # Assume it is an old calculation without potcar_spec data and treat it as passing POTCAR hash check
        return False


def _check_vasp_version(reasons, vasp_version, vasp_major_version, vasp_minor_version, vasp_patch_version, parameters):
    if vasp_major_version == 6:
        pass
    elif (vasp_major_version == 5) and ("METAGGA" in parameters.keys()) and (parameters.get("ISPIN", 1) == 2):
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


def _get_task_type(orig_inputs):
    return task_type(orig_inputs)


def _get_calc_type(calcs_reversed, orig_inputs):
    inputs = (
        calcs_reversed[0].get("input", {})
        if len(calcs_reversed) > 0
        else orig_inputs
    )
    params = calcs_reversed[0].get("input", {}).get("parameters", {})
    incar = calcs_reversed[0].get("input", {}).get("incar", {})

    return calc_type(inputs, {**params, **incar})