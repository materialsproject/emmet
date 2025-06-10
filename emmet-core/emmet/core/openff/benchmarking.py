from MDAnalysis import Universe
from MDAnalysis.analysis.dielectric import DielectricConstant
from pydantic import BaseModel, Field
from transport_analysis.viscosity import ViscosityHelfand


class SolventBenchmarkingDoc(BaseModel, arbitrary_types_allowed=True):
    density: float | None = Field(None, description="Density of the solvent")

    viscosity_function_values: list[float] | None = Field(
        None, description="Viscosity function over time"
    )

    viscosity: float | None = Field(None, description="Viscosity of the solvent")

    dielectric: float | None = Field(
        None, description="Dielectric constant of the solvent"
    )

    job_uuid: str | None = Field(
        None, description="The UUID of the flow that generated this data."
    )

    flow_uuid: str | None = Field(
        None, description="The UUID of the top level host from that job."
    )

    dielectric_run_kwargs: dict | None = Field(
        None, description="kwargs passed to the DielectricConstant.run method"
    )

    viscosity_run_kwargs: dict | None = Field(
        None, description="kwargs passed to the ViscosityHelfand.run method"
    )

    tags: list[str] | None = Field(
        [], title="tag", description="Metadata tagged to the parent job."
    )

    @classmethod
    def from_universe(
        cls,
        u: Universe,
        temperature: float | None = None,
        density: float | None = None,
        job_uuid: str | None = None,
        flow_uuid: str | None = None,
        dielectric_run_kwargs: dict | None = None,
        viscosity_run_kwargs: dict | None = None,
        tags: list[str] | None = None,
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
