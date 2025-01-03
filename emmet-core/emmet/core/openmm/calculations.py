from typing import List, Optional, Union
from datetime import datetime

from pydantic import BaseModel, Field

from emmet.core.openmm.tasks import Calculation


class CalculationsDoc(BaseModel):
    """
    A document for storing metadata from a list of OpenMM calculations.

    In each field, calculations are listed sequentially, in the order they were run.
    """

    task_names: Optional[List[str]] = Field(None, description="Names of tasks.")

    calc_types: Optional[List[str]] = Field(None, description="Types of calculations.")

    elapsed_times: Optional[List[Union[float, None]]] = Field(
        None, description="Elapsed time for calculations."
    )

    steps: Optional[List[Union[float, None]]] = Field(
        None, description="n_steps for calculations."
    )

    step_sizes: Optional[List[Union[float, None]]] = Field(
        None, description="Step sizes for each calculations."
    )

    temperatures: Optional[List[Union[float, None]]] = Field(
        None, description="Temperature for each calculations."
    )

    pressures: Optional[List[Union[float, None]]] = Field(
        None, description="Pressure for each calculations."
    )

    friction_coefficients: Optional[List[Union[float, None]]] = Field(
        None,
        description="Friction coefficients for each calculations.",
    )

    completed_at: Optional[datetime] = Field(
        None,
        description="Timestamp for when the final calculation completed.",
    )

    job_uuid: Optional[str] = Field(
        None, description="The UUID of the flow that generated this data."
    )

    flow_uuid: Optional[str] = Field(
        None, description="The UUID of the top level host from that job."
    )

    @classmethod
    def from_calcs_reversed(
        cls,
        calcs_reversed: List[Calculation],
        job_uuid: Optional[str] = None,
        flow_uuid: Optional[str] = None,
    ) -> "CalculationsDoc":
        calcs = calcs_reversed[::-1]
        return CalculationsDoc(
            task_names=[calc.task_name for calc in calcs],
            calc_types=[calc.calc_type for calc in calcs],
            elapsed_times=[calc.output.elapsed_time for calc in calcs],
            steps=[calc.input.n_steps for calc in calcs],
            step_sizes=[calc.input.step_size for calc in calcs],
            temperatures=[calc.input.temperature for calc in calcs],
            pressures=[calc.input.pressure for calc in calcs],
            friction_coefficients=[calc.input.friction_coefficient for calc in calcs],
            completed_at=calcs[-1].completed_at,
            job_uuid=job_uuid,
            flow_uuid=flow_uuid,
        )
