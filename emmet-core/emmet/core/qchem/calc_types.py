""" Module to define various calculation types for Q-Chem """
from typing import Dict, List, Optional, TypeVar, Type

from pydantic import BaseModel, Field

from emmet.core.utils import ValueEnum
from emmet.core.qchem.solvent import SolventModel, SolventData


_TASK_TYPES = [
    "single point",
    "geometry optimization",
    "frequency analysis",
    "transition state optimization",
    "frequency flattening optimization",
    "frequency flattening transition state optimization",
    "critical point analysis"
]
TaskType = ValueEnum("TaskType", {"_".join(tt.split()): tt for tt in _TASK_TYPES})  # type: ignore
TaskType.__doc__ = "Q-Chem calculation task types"


def task_type(calc_input: Dict,
              metadata: Optional[Dict] = None) -> TaskType:
    """
    Determines the task type.

    Args:
        calc_input: Calculation input dictionary
        metadata: Dict with additional information about this task
    """

    if metadata is not None:
        special_run_type = metadata.get("special_run_type")
        if special_run_type == "frequency_flattener":
            return TaskType("frequency flattening optimization")
        elif special_run_type == "ts_frequency_flattener":
            return TaskType("frequency flattening transition state optimization")

        if metadata.get("critic2"):
            return TaskType("critical point analysis")

    # If there is only one calculation, task type defined by job_type
    job_type = calc_input.get("rem", dict()).get("job_type")
    if job_type.lower() == "sp":
        return TaskType("single point")
    if job_type.lower() == "opt":
        return TaskType("geometry optimization")
    if job_type.lower() == "freq":
        return TaskType("frequency analysis")
    if job_type.lower() == "ts":
        return TaskType("transition state optimization")

    return TaskType("single point")


S = TypeVar("S", bound="LevelOfTheory")


class LevelOfTheory(BaseModel):
    """
    Data model for calculation level of theory
    """

    functional: str = Field(..., description="Exchange-correlation density functional")

    basis: str = Field(..., description="Basis set name")

    solvent_data: SolventData = Field(None, description="Implicit solvent model")

    correction_functional: str = Field(
        None,
        description="Exchange-correlation density functional used for energy corrections"
    )

    correction_basis: str = Field(
        None,
        description="Basis set name used for energy corrections"
    )

    correction_solvent_data: SolventData = Field(
        None,
        description="Implicit solvent model used for energy corrections"
    )

    @property
    def solvent_model(self) -> SolventModel:
        if self.solvent_data is None:
            return SolventData("vacuum")
        else:
            return self.solvent_data.solvent_model

    @property
    def as_string(self) -> str:
        func = self.functional
        basis = self.basis
        if self.solvent_data is not None:
            if self.solvent_data.name is None:
                name = "Unknown"
            else:
                name = self.solvent_data.name
            solv = "{}({})".format(str(self.solvent_model), name)
        else:
            solv = "vacuum"

        main_string = "/".join([func, basis, solv])

        if self.correction_functional is not None and self.correction_basis is not None:
            func_corr = self.correction_functional
            basis_corr = self.correction_basis

            if self.correction_solvent_data is not None:
                if self.correction_solvent_data.name is None:
                    name_corr = "Unknown"
                else:
                    name_corr = self.correction_solvent_data.name
                solv_corr = "{}({})".format(
                    str(self.correction_solvent_data.model),
                    name_corr
                )
            else:
                solv_corr = "vacuum"

            corr_string = "/".join([func_corr, basis_corr, solv_corr])

            return corr_string + "//" + main_string

        return main_string

    @classmethod
    def from_inputs(cls: Type[S], calc_input: Dict, metadata: Optional[Dict] = None) -> S:
        if "rem" not in calc_input:
            raise ValueError("No rem dict provided! calc_input is invalid!")
        if "method" not in calc_input["rem"] or "basis" not in calc_input["rem"]:
            raise ValueError("Method and basis must be provided in rem dict!")

        func = calc_input["rem"]["method"]
        if calc_input["rem"].get("dft_d"):
            if "d3" in calc_input["rem"]["dft_d"]:
                func += "-D3"
            elif calc_input["rem"]["dft_d"].lower() == "empirical_grimme":
                func += "-D2"

        basis = calc_input["rem"]["basis"]

        solvent = SolventData.from_input_dict(calc_input, metadata=metadata)

        return cls(functional=func, basis=basis, solvent_data=solvent)


def calc_type(calc_inputs: List[Dict],
              metadata: Optional[Dict] = None) -> str:

    tt = task_type(calc_inputs, metadata=metadata).value
    lot = LevelOfTheory.from_inputs(calc_inputs, metadata=metadata)
    return "{} : {}".format(tt, lot.as_string)