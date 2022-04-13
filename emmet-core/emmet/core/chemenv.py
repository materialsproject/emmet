from typing import Literal, List, Union

from pydantic import Field
from pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies import (
    SimplestChemenvStrategy,
)
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometries import (
    AllCoordinationGeometries,
)
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import (
    LocalGeometryFinder,
)
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import (
    LightStructureEnvironments,
    StructureEnvironments,
)
from pymatgen.analysis.structure_analyzer import SpacegroupAnalyzer
from pymatgen.core.structure import Molecule
from pymatgen.core.structure import Structure

from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID

AVAILABLE_METHODS = {
    "DefaultSimplestChemenvStrategy": SimplestChemenvStrategy(),
    "DefaultSimplestChemenvStrategy_all_bonds": SimplestChemenvStrategy(
        additional_condition=0
    ),
}


DEFAULTSIMPLESTCHEMENVSTRATEGY = "Simplest ChemenvStrategy using fixed angle and distance parameters for the definition of neighbors in the Voronoi approach. The coordination environment is then given as the one with the lowest continuous symmetry measure. Options: distance_cutoff=1.4 angle_cutoff=0.3 additional_condition=1 continuous_symmetry_measure_cutoff=10.0"
SIMPLESTCHEMENVSTRATEGY_ALL_BONDS = "Simplest ChemenvStrategy using fixed angle and distance parameters for the definition of neighbors in the Voronoi approach. The coordination environment is then given as the one with the lowest continuous symmetry measure. Options: distance_cutoff=1.4 angle_cutoff=0.3 additional_condition=0 continuous_symmetry_measure_cutoff=10.0"


METHODS_DESCRIPTION = {
    "DefaultSimplestChemenvStrategy": DEFAULTSIMPLESTCHEMENVSTRATEGY,
    "DefaultSimplestChemenvStrategy_all_bonds": SIMPLESTCHEMENVSTRATEGY_ALL_BONDS,
}


COORDINATION_GEOMETRIES = Literal[
    "S:1",
    "L:2",
    "A:2",
    "TL:3",
    "TY:3",
    "TS:3",
    "T:4",
    "S:4",
    "SY:4",
    "SS:4",
    "PP:5",
    "S:5",
    "T:5",
    "O:6",
    "T:6",
    "PP:6",
    "PB:7",
    "ST:7",
    "ET:7",
    "FO:7",
    "C:8",
    "SA:8",
    "SBT:8",
    "TBT:8",
    "DD:8",
    "DDPN:8",
    "HB:8",
    "BO_1:8",
    "BO_2:8",
    "BO_3:8",
    "TC:9",
    "TT_1:9",
    "TT_2:9",
    "TT_3:9",
    "HD:9",
    "TI:9",
    "SMA:9",
    "SS:9",
    "TO_1:9",
    "TO_2:9",
    "TO_3:9",
    "PP:10",
    "PA:10",
    "SBSA:10",
    "MI:10",
    "BS_1:10",
    "BS_2:10",
    "TBSA:10",
    "PCPA:11",
    "H:11",
    "DI:11",
    "I:12",
    "PBP:12",
    "TT:12",
    "C:12",
    "AC:12",
    "SC:12",
    "HP:12",
    "HA:12",
    "SH:13",
    "DD:20",
    "None",
]

COORDINATION_GEOMETRIES_IUPAC = Literal[
    "TOCT-9",
    "CUS-10",
    "PPR-10",
    "PPRP-11",
    "OCF-7",
    "SAPRT-10",
    "T-4",
    "PAPR-10",
    "DD-20",
    "TPR-6",
    "OCT-8",
    "PP-5",
    "SPY-4",
    "HBPY-9",
    "A-2",
    "TPRT-8",
    "TS-3",
    "SS-4",
    "None",
    "SAPR-8",
    "SPY-5",
    "SAPRS-10",
    "HPR-12",
    "L-2",
    "PPY-6",
    "SP-4",
    "IC-12",
    "HBPY-8",
    "TPY-3",
    "CUS-9",
    "TPRS-8",
    "DD-8",
    "TBPY-5",
    "TP-3",
    "TCA-9",
    "PPRP-12",
    "SAPRS-9",
    "OC-6",
    "PBPY-7",
    "TPRS-7",
    "TPRS-9",
    "CU-8",
    "HAPR-12",
    "TPRT-7",
]

COORDINATION_GEOMETRIES_IUCR = Literal[
    "[8do]",
    "[3n]",
    "[6p]",
    "[8cb]",
    "[5by]",
    "[12p]",
    "[6p2c]",
    "[8acb]",
    "[7by]",
    "[3l]",
    "[6p1c]",
    "[12aco]",
    "[2l]",
    "None",
    "[12i]",
    "[6o]",
    "[6p3c]",
    "[4n]",
    "[12co]",
    "[1l]",
    "[5y]",
    "[5l]",
    "[4l]",
    "[2n]",
    "[8by]",
    "[4t]",
    "[12tt]",
]
COORDINATION_GEOMETRIES_NAMES = Literal[
    "Pentagonal pyramid",
    "Metabidiminished icosahedron",
    "Square-face bicapped trigonal prism",
    "Pentagonal plane",
    "Cube",
    "Triangular cupola",
    "Heptagonal dipyramid",
    "Pentagonal prism",
    "T-shaped",
    "Square-face capped trigonal prism",
    "Single neighbor",
    "Triangular-face bicapped trigonal prism",
    "Pentagonal-face capped pentagonal antiprism",
    "Trigonal prism",
    "Square cupola",
    "See-saw",
    "Square non-coplanar",
    "Hexagonal bipyramid",
    "Triangular non-coplanar",
    "Tetrahedron",
    "Tricapped triangular prism (one square-face cap and two triangular-face caps)",
    "Square-face monocapped antiprism",
    "Hexagonal antiprism",
    "Linear",
    "Octahedron",
    "Truncated tetrahedron",
    "Square-face capped hexagonal prism",
    "Tricapped octahedron (all 3 cap faces share one atom)",
    "Bicapped square prism (opposite faces)",
    "Bicapped octahedron (cap faces with one edge in common)",
    "Tridiminished icosahedron",
    "Cuboctahedron",
    "Dodecahedron",
    "Dodecahedron with triangular faces - p2345 plane normalized",
    "Square-face capped square prism",
    "Icosahedron",
    "Dodecahedron with triangular faces",
    "Pentagonal bipyramid",
    "Tricapped octahedron (cap faces are aligned)",
    "Square pyramid",
    "Tricapped triangular prism (three square-face caps)",
    "Trigonal bipyramid",
    "Tricapped triangular prism (two square-face caps and one triangular-face cap)",
    "Pentagonal antiprism",
    "Diminished icosahedron",
    "Anticuboctahedron",
    "Trigonal-face bicapped square antiprism",
    "Bicapped octahedron (cap faces with one atom in common)",
    "Hexagonal prism",
    "Angular",
    "Trigonal plane",
    "Square plane",
    "Bicapped octahedron (opposed cap faces)",
    "Bicapped square prism (adjacent faces)",
    "Square antiprism",
    "Pentagonal-face bicapped pentagonal prism",
    "Square-face bicapped square antiprism",
    "Hendecahedron",
    "End-trigonal-face capped trigonal prism",
    "Face-capped octahedron",
    "Tricapped octahedron (all 3 cap faces are sharingone edge of a face)",
]

COORDINATION_GEOMETRIES_NAMES_WITH_ALTERNATIVES = Literal[
    "Anticuboctahedron (also known as Triangular bicupola)",
    "Trigonal bipyramid (also known as Trigonal dipyramid, Triangular dipyramid)",
    "Octahedron (also known as Square dipyramid, Square bipyramid, Triangular antiprism, Trigonal antiprism)",
    "Diminished icosahedron",
    "Square antiprism (also known as Tetragonal antiprism, Anticube)",
    "Square cupola",
    "Hexagonal bipyramid (also known as Hexagonal dipyramid)",
    "Square-face capped hexagonal prism",
    "Bicapped square prism (opposite faces) (also known as Bicapped cube)",
    "Square-face bicapped trigonal prism",
    "Square non-coplanar",
    "Triangular-face bicapped trigonal prism",
    "Square plane",
    "Trigonal prism (also known as Triangular prism)",
    "Bicapped octahedron (opposed cap faces)",
    "Tricapped octahedron (all 3 cap faces share one atom)",
    "Pentagonal prism",
    "Triangular cupola",
    "Bicapped square prism (adjacent faces) (also known as Bicapped cube)",
    "Cuboctahedron",
    "Tricapped triangular prism (two square-face caps and one triangular-face cap) (also known as Triaugmented trigonal prism)",
    "Square-face capped trigonal prism (also known as Augmented triangular prism)",
    "Tetrahedron (also known as Triangular pyramid, Trigonal pyramid)",
    "Cube (also known as Square prism, Tetragonal prism)",
    "Bicapped octahedron (cap faces with one edge in common)",
    "Bicapped octahedron (cap faces with one atom in common)",
    "Pentagonal pyramid",
    "Dodecahedron with triangular faces (also known as Snub disphenoid, Siamese dodecahedron)",
    "Pentagonal antiprism (also known as Paradiminished icosahedron)",
    "Tricapped octahedron (cap faces are aligned)",
    "Icosahedron",
    "Dodecahedron",
    "Face-capped octahedron (also known as Monocapped octahedron)",
    "Angular",
    "Hendecahedron (also known as Bisymmetric hendecahedron)",
    "Trigonal-face bicapped square antiprism",
    "Pentagonal-face capped pentagonal antiprism (also known as Gyroelongated pentagonal pyramid, Diminished icosahedron, Truncated icosahedron)",
    "Linear",
    "Pentagonal plane (also known as Pentagon)",
    "Tricapped triangular prism (three square-face caps) (also known as Triaugmented trigonal prism)",
    "Tricapped octahedron (all 3 cap faces are sharingone edge of a face)",
    "Heptagonal dipyramid (also known as Heptagonal bipyramid)",
    "T-shaped",
    "Single neighbor",
    "Trigonal plane (also known as Triangular planar)",
    "Dodecahedron with triangular faces - p2345 plane normalized (also known as Snub disphenoid - p2345 plane normalized, Siamese dodecahedron - p2345 plane normalized)",
    "Tricapped triangular prism (one square-face cap and two triangular-face caps) (also known as Triaugmented trigonal prism)",
    "Truncated tetrahedron",
    "Hexagonal prism",
    "Tridiminished icosahedron",
    "Metabidiminished icosahedron",
    "See-saw",
    "Square-face capped square prism (also known as Monocapped cube)",
    "Square pyramid",
    "Pentagonal-face bicapped pentagonal prism",
    "Hexagonal antiprism",
    "Triangular non-coplanar",
    "End-trigonal-face capped trigonal prism (also known as Augmented triangular prism)",
    "Pentagonal bipyramid (also known as Pentagonal dipyramid)",
    "Square-face monocapped antiprism (also known as Gyroelongated square pyramid)",
    "Square-face bicapped square antiprism (also known as Square-face bicapped square anticube, Bicapped anticube, Gyroelongated square dipyramid)",
]


class ChemEnvDoc(PropertyDoc):
    """Coordination environments based on cation-anion bonds computed for all unique cations in this structure. If no oxidation states are available, all bonds will be considered as a fall-back."""

    property_name = "coord_environment"

    structure: Structure = Field(
        ...,
        description="The structure used in the generation of the chemical environment data",
    )

    valences: List[int] = Field(
        description="List of valences for each site in this material to determine cations"
    )

    species: List[str] = Field(
        description="List of unique (cationic) species in structure."
    )

    chemenv_symbol: List[COORDINATION_GEOMETRIES] = Field(
        description="List of ChemEnv symbols for unique (cationic) species in structure"
    )

    chemenv_iupac: List[COORDINATION_GEOMETRIES_IUPAC] = Field(
        description="List of symbols for unique (cationic) species in structure in IUPAC format"
    )

    chemenv_iucr: List[COORDINATION_GEOMETRIES_IUCR] = Field(
        description="List of symbols for unique (cationic) species in structure in IUPAC format"
    )

    chemenv_name: List[COORDINATION_GEOMETRIES_NAMES] = Field(
        description="List of text description of coordination environment for unique (cationic) species in structure."
    )
    chemenv_name_with_alternatives: List[
        COORDINATION_GEOMETRIES_NAMES_WITH_ALTERNATIVES
    ] = Field(
        description="List of text description of coordination environment including alternative descriptions for unique (cationic) species in structure."
    )

    csm: List[Union[float, None]] = Field(
        description="Saves the continous symmetry measures for unique (cationic) species in structure"
    )

    method: Union[str, None] = Field(
        description="Method used to compute chemical environments"
    )

    mol_from_site_environments: List[Union[Molecule, None]] = Field(
        description="List of Molecule Objects describing the detected environment."
    )

    # structure_environment: Union[StructureEnvironments, None] = Field(
    #     description="Structure environment object"
    # )

    wyckoff_positions: List[str] = Field(
        description="List of Wyckoff positions for unique (cationic) species in structure."
    )

    warnings: Union[str, None] = Field(None, description="Warning")

    @classmethod
    def from_structure(
        cls,
        structure: Structure,
        material_id: MPID,
        **kwargs,
    ):  # type: ignore[override]
        """

        Args:
            structure: structure including oxidation states
            material_id: mpid
            **kwargs:

        Returns:

        """
        d = {
            "valences": [],
            "species": [],
            "chemenv_symbol": [],
            "chemenv_iupac": [],
            "chemenv_iucr": [],
            "chemenv_name": [],
            "chemenv_name_with_alternatives": [],
            "csm": [],
            "mol_from_site_environments": [],
            "wyckoff_positions": [],
            "method": None,
            "warnings": None,
            # "structure_environment": None,
        }  # type: dict

        try:
            list_mol = []
            list_chemenv = []
            list_chemenv_iupac = []
            list_chemenv_iucr = []
            list_chemenv_text = []
            list_chemenv_text_with_alternatives = []
            list_csm = []
            list_wyckoff = []
            list_species = []

            valences = [getattr(site.specie, "oxi_state", None) for site in structure]
            valences = [v for v in valences if v is not None]
            sga = SpacegroupAnalyzer(structure)
            symm_struct = sga.get_symmetrized_structure()
            # We still need the whole list of indices
            inequivalent_indices = [
                indices[0] for indices in symm_struct.equivalent_indices
            ]
            # wyckoff symbols for all inequivalent indices
            wyckoffs_unique = symm_struct.wyckoff_symbols
            # use the local geometry finder to get the important information
            lgf = LocalGeometryFinder()
            lgf.setup_structure(structure=structure)
            all_ce = AllCoordinationGeometries()
            if len(valences) == len(structure):
                # Standard alorithm will only focus on cations and cation-anion bonds!
                method_description = "DefaultSimplestChemenvStrategy"
                method = AVAILABLE_METHODS[method_description]
                # We will only focus on cations!
                inequivalent_indices_cations = [
                    indices[0]
                    for indices in symm_struct.equivalent_indices
                    if valences[indices[0]] > 0.0
                ]

                se = lgf.compute_structure_environments(
                    only_indices=inequivalent_indices_cations,
                    valences=valences,
                )
                lse = LightStructureEnvironments.from_structure_environments(
                    strategy=method, structure_environments=se
                )
                warnings = None
            else:
                method_description = "DefaultSimplestChemenvStrategy_all_bonds"
                method = AVAILABLE_METHODS[method_description]

                se = lgf.compute_structure_environments(
                    only_indices=inequivalent_indices,
                )
                lse = LightStructureEnvironments.from_structure_environments(
                    strategy=method, structure_environments=se
                )
                # Trick to get rid of duplicate code
                inequivalent_indices_cations = inequivalent_indices
                warnings = "No oxidation states. Analysis will now include all bonds"

            for index, wyckoff in zip(inequivalent_indices, wyckoffs_unique):
                # ONLY CATIONS
                if index in inequivalent_indices_cations:
                    # Coordinaton environment will be saved as a molecule!
                    mol = Molecule.from_sites(
                        [structure[index]] + lse.neighbors_sets[index][0].neighb_sites
                    )
                    mol = mol.get_centered_molecule()
                    env = lse.coordination_environments[index]
                    co = all_ce.get_geometry_from_mp_symbol(env[0]["ce_symbol"])
                    name = co.name
                    if co.alternative_names:
                        name += f" (also known as {', '.join(co.alternative_names)})"
                    # save everything in a list
                    list_chemenv_text.append(co.name)
                    list_chemenv_text_with_alternatives.append(name)
                    list_chemenv.append(co.ce_symbol)
                    list_chemenv_iucr.append(co.IUCr_symbol_str)
                    list_chemenv_iupac.append(co.IUPAC_symbol_str)
                    list_mol.append(mol)
                    list_wyckoff.append(wyckoff)
                    list_species.append(structure[index].species_string)
                    list_csm.append(env[0]["csm"])

                d.update(
                    {
                        "valences": valences,
                        "species": list_species,
                        "chemenv_symbol": list_chemenv,
                        "chemenv_iupac": list_chemenv_iupac,
                        "chemenv_iucr": list_chemenv_iucr,
                        "chemenv_name": list_chemenv_text,
                        "chemenv_name_with_alternatives": list_chemenv_text_with_alternatives,
                        "csm": list_csm,
                        "mol_from_site_environments": list_mol,
                        "wyckoff_positions": list_wyckoff,
                        # "structure_environment": se.as_dict(),
                        "method": METHODS_DESCRIPTION[method_description],
                        "warnings": warnings,
                    }
                )

        except Exception:
            d.update({"warnings": "ChemEnv algorithm failed"})

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **d,
            **kwargs,
        )
