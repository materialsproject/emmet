"""Common models and types needed in VASP."""

from pydantic import BaseModel, Field


class ElectronicStep(BaseModel):
    """Document defining the information at each electronic step.

    Note, not all the information will be available at every step.
    """

    alphaZ: float | None = Field(None, description="The alpha Z term.")
    ewald: float | None = Field(None, description="The ewald energy.")
    hartreedc: float | None = Field(None, description="Negative Hartree energy.")
    XCdc: float | None = Field(None, description="Negative exchange energy.")
    pawpsdc: float | None = Field(
        None, description="Negative potential energy with exchange-correlation energy."
    )
    pawaedc: float | None = Field(None, description="The PAW double counting term.")
    eentropy: float | None = Field(None, description="The entropy (T * S).")
    bandstr: float | None = Field(
        None, description="The band energy (from eigenvalues)."
    )
    atom: float | None = Field(None, description="The atomic energy.")
    e_fr_energy: float | None = Field(None, description="The free energy.")
    e_wo_entrp: float | None = Field(None, description="The energy without entropy.")
    e_0_energy: float | None = Field(None, description="The internal energy.")
