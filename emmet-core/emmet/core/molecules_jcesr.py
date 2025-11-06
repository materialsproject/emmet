from pydantic import BaseModel, Field
from pymatgen.core.periodic_table import Element

from emmet.core.types.pymatgen_types.structure_adapter import MoleculeType


class MoleculesDoc(BaseModel):
    """
    Molecules relevant to battery electrolytes.
    """

    elements: list[Element] | None = Field(
        None,
        description="List of elements in the molecule.",
    )

    nelements: int | None = Field(
        None,
        description="Number of elements in the molecule.",
    )

    EA: float | None = Field(
        None,
        description="Electron affinity of the molecule in eV.",
    )

    IE: float | None = Field(
        None,
        description="Ionization energy of the molecule in eV.",
    )

    charge: int | None = Field(
        None,
        description="Charge of the molecule in +e.",
    )

    pointgroup: str | None = Field(
        None,
        description="Point group of the molecule in Schoenflies notation.",
    )

    smiles: str | None = Field(
        None,
        description="The simplified molecular input line-entry system (SMILES) \
            representation of the molecule.",
    )

    task_id: str | None = Field(
        None,
        description="Materials Project molecule ID. This takes the form mol-*****.",
    )

    molecule: MoleculeType | None = Field(
        None,
        description="Pymatgen molecule object.",
    )

    formula_pretty: str | None = Field(
        None,
        description="Chemical formula of the molecule.",
    )

    svg: str | None = Field(
        None,
        description="String representation of the SVG image of the molecule.",
    )
