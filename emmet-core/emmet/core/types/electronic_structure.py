from pydantic import BaseModel, Field, model_validator

from emmet.core.types.pymatgen_types.bandstructure_symm_line_adapter import (
    BandStructureSymmLineType,
)
from emmet.core.types.pymatgen_types.dos_adapter import CompleteDosType
from emmet.core.types.typing import IdentifierType

lmaxmix = int


class DosShim(BaseModel):
    """Light wrapper around DOS data - useful for static analysis and runtime safety"""

    dos: tuple[str, CompleteDosType, lmaxmix] = Field(
        ...,
        description="Tuple of a calculation (task) ID, a CompleteDos object, and lmaxmix from the calculation.",
    )


class BSShim(BaseModel):
    """
    Light wrapper around bandstructure data - useful for static analysis and runtime safety

    At least one field must be populated with bandstructure data.
    """

    setyawan_curtarolo: (
        tuple[IdentifierType, BandStructureSymmLineType, lmaxmix] | None
    ) = Field(
        None,
        description="""
        Tuple of a calculation (task) ID, a BandStructureSymmLine object 
        from a calculation run using the Setyawan-Curtarolo k-path 
        convention, and lmaxmix from the calculation.
        """,
    )
    hinuma: tuple[IdentifierType, BandStructureSymmLineType, lmaxmix] | None = Field(
        None,
        description="""
        Tuple of a calculation (task) ID, a BandStructureSymmLine object 
        from a calculation run using the Hinuma et al. k-path 
        convention, and lmaxmix from the calculation.
        """,
    )
    latimer_munro: tuple[IdentifierType, BandStructureSymmLineType, lmaxmix] | None = (
        Field(
            None,
            description="""
            Tuple of a calculation (task) ID, a BandStructureSymmLine object 
            from a calculation run using the Latimer-Munro et al. k-path 
            convention, and lmaxmix from the calculation.
            """,
        )
    )

    @model_validator(mode="after")
    def _has_at_least_one_bandstructure(self):
        has_setyawan_curtarolo = self.setyawan_curtarolo is not None
        has_hinuma = self.hinuma is not None
        has_latimer_munro = self.latimer_munro is not None

        if not (has_setyawan_curtarolo or has_hinuma or has_latimer_munro):
            raise ValueError()(
                "At least one bandstructure type ('setyawan_curtarolo', 'hinuma', or 'latimer_munro') must be populated"
            )

        return self
