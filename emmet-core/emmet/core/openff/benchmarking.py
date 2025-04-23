from typing import Optional

from MDAnalysis import Universe
from MDAnalysis.analysis.dielectric import DielectricConstant
from pydantic import BaseModel, Field
from transport_analysis.viscosity import ViscosityHelfand

from emmet.core.utils import arrow_incompatible


@arrow_incompatible
class SolventBenchmarkingDoc(BaseModel, arbitrary_types_allowed=True):
    density: Optional[float] = Field(None, description="Density of the solvent")

    viscosity_function_values: Optional[list[float]] = Field(
        None, description="Viscosity function over time"
    )

    viscosity: Optional[float] = Field(None, description="Viscosity of the solvent")

    dielectric: Optional[float] = Field(
        None, description="Dielectric constant of the solvent"
    )

    job_uuid: Optional[str] = Field(
        None, description="The UUID of the flow that generated this data."
    )

    flow_uuid: Optional[str] = Field(
        None, description="The UUID of the top level host from that job."
    )

    dielectric_run_kwargs: Optional[dict] = Field(
        None, description="kwargs passed to the DielectricConstant.run method"
    )

    viscosity_run_kwargs: Optional[dict] = Field(
        None, description="kwargs passed to the ViscosityHelfand.run method"
    )

    tags: Optional[list[str]] = Field(
        [], title="tag", description="Metadata tagged to the parent job."
    )

    @classmethod
    def from_universe(
        cls,
        u: Universe,
        temperature: Optional[float] = None,
        density: Optional[float] = None,
        job_uuid: Optional[str] = None,
        flow_uuid: Optional[str] = None,
        dielectric_run_kwargs: Optional[dict] = None,
        viscosity_run_kwargs: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> "SolventBenchmarkingDoc":
        if temperature is not None:
            dielectric = DielectricConstant(
                u.atoms, temperature=temperature, make_whole=False
            )
            dielectric_run_kwargs = dielectric_run_kwargs or {}
            dielectric.run(**dielectric_run_kwargs)
            eps = dielectric.results.eps_mean
        else:
            eps = None

        if u.atoms.ts.has_velocities:
            start, stop = int(0.2 * len(u.trajectory)), int(0.8 * len(u.trajectory))
            viscosity_helfand = ViscosityHelfand(
                u.atoms,
                temp_avg=temperature,
                linear_fit_window=(start, stop),
            )
            viscosity_run_kwargs = viscosity_run_kwargs or {}
            viscosity_helfand.run(**viscosity_run_kwargs)
            viscosity_function_values = viscosity_helfand.results.timeseries.tolist()
            viscosity = viscosity_helfand.results.viscosity

        else:
            viscosity_function_values = None
            viscosity = None

        return cls(
            density=density,
            viscosity_function_values=viscosity_function_values,
            viscosity=viscosity,
            dielectric=eps,
            job_uuid=job_uuid,
            flow_uuid=flow_uuid,
            dielectric_run_kwargs=dielectric_run_kwargs,
            viscosity_run_kwargs=viscosity_run_kwargs,
            tags=tags,
        )
