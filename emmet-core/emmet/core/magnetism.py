from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen.core import Structure

from emmet.core.material_property import PropertyDoc

if TYPE_CHECKING:
    from emmet.core.types.typing import IdentifierType


class MagnetismDoc(PropertyDoc):
    """
    Magnetic data obtain from the calculated structure
    """

    property_name: str = "magnetism"

    ordering: str | None = Field(
        None,
        description="Magnetic ordering.",
    )

    is_magnetic: bool | None = Field(
        None,
        description="Whether the material is magnetic.",
    )

    exchange_symmetry: int | None = Field(
        None,
        description="Exchange symmetry.",
    )

    num_magnetic_sites: int | None = Field(
        None,
        description="The number of magnetic sites.",
    )

    num_unique_magnetic_sites: int | None = Field(
        None,
        description="The number of unique magnetic sites.",
    )

    types_of_magnetic_species: list[str] | None = Field(
        None,
        description="Magnetic specie elements.",
    )

    magmoms: list[float] | None = Field(
        None,
        description="Magnetic moments for each site.",
    )

    total_magnetization: float | None = Field(
        None,
        description="Total magnetization in μB.",
    )

    total_magnetization_normalized_vol: float | None = Field(
        None,
        description="Total magnetization normalized by volume in μB/Å³.",
    )

    total_magnetization_normalized_formula_units: float | None = Field(
        None,
        description="Total magnetization normalized by formula unit in μB/f.u. .",
    )

    @classmethod
    def from_structure(
        cls,
        structure: Structure,
        total_magnetization: float,
        material_id: IdentifierType | None = None,
        **kwargs,
    ):  # noqa: E501
        struct_has_magmoms = "magmom" in structure.site_properties
        total_magnetization = abs(
            total_magnetization
        )  # not necessarily == sum(magmoms)
        msa = CollinearMagneticStructureAnalyzer(
            structure, round_magmoms=True, threshold_nonmag=0.2, threshold=0
        )

        magmoms = msa.magmoms.tolist()

        d = {
            "ordering": msa.ordering.value if struct_has_magmoms else "Unknown",
            "is_magnetic": msa.is_magnetic,
            "exchange_symmetry": msa.get_exchange_group_info()[1],
            "num_magnetic_sites": msa.number_of_magnetic_sites,
            "num_unique_magnetic_sites": msa.number_of_unique_magnetic_sites(),
            "types_of_magnetic_species": [str(t) for t in msa.types_of_magnetic_specie],
            "magmoms": magmoms,
            "total_magnetization": total_magnetization,
            "total_magnetization_normalized_vol": total_magnetization
            / structure.volume,
            "total_magnetization_normalized_formula_units": total_magnetization
            / (structure.composition.get_reduced_composition_and_factor()[1]),
        }

        return super().from_structure(
            meta_structure=structure, material_id=material_id, **d, **kwargs
        )
