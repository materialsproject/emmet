from datetime import datetime

from pydantic import BaseModel, Field

from emmet.core.openmm.tasks import Calculation


class CalculationsDoc(BaseModel):
    """
    A document for storing metadata from a list of OpenMM calculations.

    In each field, calculations are listed sequentially, in the order they were run.
    """

    task_names: list[str] | None = Field(None, description="Names of tasks.")

    calc_types: list[str] | None = Field(None, description="Types of calculations.")

    elapsed_times: list[float | None] | None = Field(
        None, description="Elapsed time for calculations."
    )

    steps: list[float | None] | None = Field(
        None, description="n_steps for calculations."
    )

    step_sizes: list[float | None] | None = Field(
        None, description="Step sizes for each calculations."
    )

    temperatures: list[float | None] | None = Field(
        None, description="Temperature for each calculations."
    )

    pressures: list[float | None] | None = Field(
        None, description="Pressure for each calculations."
    )

    friction_coefficients: list[float | None] | None = Field(
        None,
        description="Friction coefficients for each calculations.",
    )

    completed_at: datetime | None = Field(
        None,
        description="Timestamp for when the final calculation completed.",
    )

    job_uuid: str | None = Field(
        None, description="The UUID of the flow that generated this data."
    )

    flow_uuid: str | None = Field(
        None, description="The UUID of the top level host from that job."
    )

    @classmethod
    def from_calcs_reversed(
        cls,
        calcs_reversed: list[Calculation],
        job_uuid: str | None = None,
        flow_uuid: str | None = None,
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
