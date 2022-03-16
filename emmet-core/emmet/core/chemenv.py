from typing import Literal, List, Union
from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID
from pydantic import Field
from pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies import (
    SimplestChemenvStrategy,
    MultiWeightsChemenvStrategy,
)
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometries import (
    AllCoordinationGeometries,
)
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import (
    LocalGeometryFinder,
)
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import (
    LightStructureEnvironments,
)
from pymatgen.analysis.structure_analyzer import SpacegroupAnalyzer
from pymatgen.core.structure import Molecule
from pymatgen.core.structure import Structure
from pymatgen.util.string import unicodeify_species

AVAILABLE_METHODS = {
    "DefaultSimplestChemenvStrategy": SimplestChemenvStrategy,
    "DefaultMultiWeightChemenvStrategy": MultiWeightsChemenvStrategy.stats_article_weights_parameters(),
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
    "undefined",
]


class ChemEnvDoc(PropertyDoc):
    """Coordination environments based on cation-anion bonds computed for all unique cations in this structure."""

    property_name = "environment"

    structure: Structure = Field(
        ...,
        description="The structure used in the generation of the chemical environment data",
    )

    valences: List[int] = Field(
        description="List of valences for each site in this material to determine cations"
    )

    cationic_species: List[str] = Field(
        description="List of unique cationic species in structure."
    )

    chemenv_symbol: List[COORDINATION_GEOMETRIES] = Field(
        description="List of ChemEnv symbols for unique cationic species in structure"
    )

    chemenv_text: List[str] = Field(
        description="List of text description of coordination environment for unique cationic species in structure."
    )

    spacegroup: str = Field(
        description="Space group that was used to determine unique cations"
    )

    method: str = Field(
        None, description="Method used to compute chemical environments"
    )

    mol_from_site_environments: List[Union[Molecule, str]] = Field(
        description="List of Molecule Objects describing the detected environment."
    )

    wyckoff_positions: List[str] = Field(
        description="List of Wyckoff positions for unique cationic species in structure."
    )

    @classmethod
    def from_structure(
        cls,
        structure: Structure,
        material_id: MPID,
        preferred_methods=["DefaultSimplestChemenvStrategy"],
        **kwargs,
    ):  # type: ignore[override]
        """

        Args:
            structure: structure including oxidation states
            material_id: mpid
            preferred_methods: preferred methods to determine coordination environments
            **kwargs:

        Returns:

        """
        try:
            preferred_methods = [  # type: ignore
                AVAILABLE_METHODS[method]() if isinstance(method, str) else method
                for method in preferred_methods
            ]
            # TODO:  I assume that structures already have oxidation states
            # TODO: Can this assumption been made or should I determine those oxidation states in case they do not exist?

            valences = [getattr(site.specie, "oxi_state", None) for site in structure]
            valences = [v for v in valences if v is not None]
            if len(valences) == len(structure):
                # should I save the space group?
                sga = SpacegroupAnalyzer(structure)
                spacegroup_symbol = sga.get_space_group_symbol()
                symm_struct = sga.get_symmetrized_structure()

                # We will only focus on cations!
                inequivalent_indices_cations = [
                    indices[0]
                    for indices in symm_struct.equivalent_indices
                    if valences[indices[0]] > 0.0
                ]

                # We still need the whole list of indices
                inequivalent_indices = [
                    indices[0] for indices in symm_struct.equivalent_indices
                ]

                # wyckoff symbols for all inquivalent indices
                wyckoffs_unique = symm_struct.wyckoff_symbols

                for method in preferred_methods:
                    lgf = LocalGeometryFinder()
                    lgf.setup_structure(structure=structure)

                    # only the environments of cations will be determined!
                    # TODO: check if further speedup is possible: reduce cutoffs?
                    se = lgf.compute_structure_environments(
                        only_indices=inequivalent_indices_cations,
                        valences=valences,
                    )
                    lse = LightStructureEnvironments.from_structure_environments(
                        strategy=method, structure_environments=se
                    )

                    all_ce = AllCoordinationGeometries()

                    # TODO: what information is needed?
                    # TODO: do we want to provide molecular representations as well?
                    list_mol = []
                    list_chemenv = []
                    list_chemenv_text = []

                    list_wyckoff = []
                    list_species = []

                    # TODO: we could also add connetions of polyhedra determined with ChemEnv
                    for index, wyckoff in zip(inequivalent_indices, wyckoffs_unique):
                        # ONLY CATIONS
                        if index in inequivalent_indices_cations:
                            if not lse.neighbors_sets[index]:
                                list_chemenv.append("undefined")
                                list_chemenv_text.append("undefined")
                                list_mol.append("undefined")
                                list_wyckoff.append(wyckoff)
                                list_species.append(
                                    unicodeify_species(structure[index].species_string)
                                )

                                continue

                            # represent the local environment as a molecule
                            # This is similar to the implementation in CrystalToolkit!
                            mol = Molecule.from_sites(
                                [structure[index]]
                                + lse.neighbors_sets[index][0].neighb_sites
                            )
                            mol = mol.get_centered_molecule()

                            env = lse.coordination_environments[index]
                            co = all_ce.get_geometry_from_mp_symbol(env[0]["ce_symbol"])
                            name = co.name
                            if co.alternative_names:
                                name += f" (also known as {', '.join(co.alternative_names)})"

                            list_chemenv_text.append(name)
                            list_chemenv.append(co.ce_symbol)
                            # TODO: add iupac name as well?
                            list_mol.append(mol)
                            list_wyckoff.append(wyckoff)
                            list_species.append(
                                unicodeify_species(structure[index].species_string)
                            )

                    d = {
                        "valences": valences,
                        "cationic_species": list_species,
                        "chemenv_symbol": list_chemenv,
                        "chemenv_text": list_chemenv_text,
                        "mol_from_site_environments": list_mol,
                        "spacegroup": spacegroup_symbol,
                        "wyckoff_positions": list_wyckoff,
                        "method": str(method),
                        "state": "successful",
                    }  # type: dict
            else:
                d = {"state": "unsuccessful", "warnings": ["No oxidation states"]}
        except Exception as e:
            logging.error("ChemEnv failed with: {}".format(e))
            d = {"state": "unsuccessful", "warnings": ["ChemEnv algorithm failed"]}

        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **d,
            **kwargs,
        )
