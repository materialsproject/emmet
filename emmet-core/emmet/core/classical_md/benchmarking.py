from pydantic import BaseModel, Field
from typing import Optional

import warnings

from MDAnalysis import Universe
from MDAnalysis.analysis.dielectric import DielectricConstant

from transport_analysis.viscosity import ViscosityHelfand


class SolventBenchmarkingDoc(BaseModel, arbitrary_types_allowed=True):
    density: Optional[float] = Field(None, description="Density of the solvent")

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

    @classmethod
    def from_universe(
        cls,
        u: Universe,
        temperature: float,
        density: Optional[float] = None,
        job_uuid: Optional[str] = None,
        flow_uuid: Optional[str] = None,
    ) -> "SolventBenchmarkingDoc":
        if temperature is not None:
            dielectric = DielectricConstant(
                u.atoms, temperature=temperature, make_whole=False
            )
            dielectric.run()
            eps = dielectric.results.eps_mean
        else:
            warnings.warn(
                "Temperature is not provided, dielectric constant will not be calculated"
            )
            eps = None

        if u.atoms.ts.has_velocities:
            viscosity_helfand = ViscosityHelfand(u.atoms, temp_avg=temperature)
            viscosity_helfand.run()
            viscosity = viscosity_helfand.results.visc_by_particle.mean()

        else:
            viscosity = None

        return cls(
            density=density,
            viscosity=viscosity,
            dielectric=eps,
            job_uuid=job_uuid,
            flow_uuid=flow_uuid,
        )
