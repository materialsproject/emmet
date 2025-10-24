"""Annotate Bader charge/spin analysis output types from pymatgen."""

from pydantic import BaseModel


class BaderAnalysis(BaseModel):
    """Output of pymatgen.command_line.bader_caller.bader_analysis_from_objects

    We omit the `charge_densities` field, since these are too large
    to justify storing in the document model.

    Charge densities can already be stored in TaskDoc.vasp_objects
    """

    min_dist: list[float]
    charge: list[float]
    atomic_volume: list[float]
    vacuum_charge: float
    vacuum_volume: float
    reference_used: bool
    bader_version: float
    charge_transfer: list[float] | None = None
    magmom: list[float] | None = None
