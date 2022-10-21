from typing import List

from pydantic import Field
from pymatgen.core import Structure
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID


class MagnetismDoc(PropertyDoc):
    """
    Magnetic data obtain from the calculated structure
    """

    property_name = "magnetism"

    ordering: str = Field(
        None,
        description="Magnetic ordering.",
    )

    is_magnetic: bool = Field(
        None,
        description="Whether the material is magnetic.",
    )

    exchange_symmetry: int = Field(
        None,
        description="Exchange symmetry.",
    )

    num_magnetic_sites: int = Field(
        None,
        description="The number of magnetic sites.",
    )

    num_unique_magnetic_sites: int = Field(
        None,
        description="The number of unique magnetic sites.",
    )

    types_of_magnetic_species: List[str] = Field(
        None,
        description="Magnetic specie elements.",
    )

    magmoms: List[float] = Field(
        None,
        description="Magnetic moments for each site.",
    )

    total_magnetization: float = Field(
        None,
        description="Total magnetization in μB.",
    )

    total_magnetization_normalized_vol: float = Field(
        None,
        description="Total magnetization normalized by volume in μB/Å³.",
    )

    total_magnetization_normalized_formula_units: float = Field(
        None,
        description="Total magnetization normalized by formula unit in μB/f.u. .",
    )

    @classmethod
    def from_structure(
        cls, structure: Structure, total_magnetization: float, material_id: MPID, **kwargs
    ):  # noqa: E501

        struct_has_magmoms = "magmom" in structure.site_properties
        total_magnetization = abs(total_magnetization)  # not necessarily == sum(magmoms)
        msa = CollinearMagneticStructureAnalyzer(structure, round_magmoms=True, threshold_nonmag=0.2, threshold=0)

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
            "total_magnetization_normalized_vol": total_magnetization / structure.volume,
            "total_magnetization_normalized_formula_units": total_magnetization
            / (structure.composition.get_reduced_composition_and_factor()[1]),
        }

        return super().from_structure(meta_structure=structure, material_id=material_id, **d, **kwargs)
