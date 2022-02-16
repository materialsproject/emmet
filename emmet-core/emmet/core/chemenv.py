from typing import Union
from pymatgen.core.structure import Molecule
from pydantic import BaseModel, Field
from pymatgen.core.structure import Structure
from pymatgen.core.sites import PeriodicSite
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometries import AllCoordinationGeometries
from pymatgen.util.string import unicodeify_species
from pymatgen.analysis.structure_analyzer import SpacegroupAnalyzer
from typing import Dict, List, Any, Union

from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import LocalGeometryFinder
import logging
from pymatgen.ext.matproj import MPRester
from pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies import SimplestChemenvStrategy, MultiWeightsChemenvStrategy
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import LightStructureEnvironments
from emmet.core.material_property import PropertyDoc
from emmet.core.mpid import MPID

#TODO: look at another example and try to make sense out of it

class ChemEnvDoc(PropertyDoc):
    """Coordination environments computed for all unique cations in this structure. """

    property_name = "environment"

    structure: Structure = Field(
        ...,
        description="The structure used in the generation of the chemical environment data",
    )
    valences: List[int] = Field(
        description="List of valences for each site in this material to determine cations"
    )
    cationic_species: List[str] = Field(description="List of unique cationic species in structure.")

    chemenv_symbol: List[str] = Field(description="List of ChemEnv symbols for unique cationic species in structure")

    chemenv_iupac: List[str] = Field(description="List of Iupac names corresponding to ChemEnv symbols for unique cationic species in structure.")

    mol_from_site_environments: List[Union[Molecule,str]]=  Field(description="List of Molecule Objects describing the detected environment.")

    wyckoff_positions: List[str] = Field(description="List of Wyckoff positions for unique cationic species in structure.")

    method: str = Field(None, description="Method used to compute chemical environments")

    @classmethod
    def from_structure(cls, structure: Structure, material_id: MPID, **kwargs):  # type: ignore[override]
        """

        Args:
            structure: structure including oxidation states
            material_id: mpid
            **kwargs:

        Returns:

        """
        #standard settings
        distance_cutoff=1.4
        angle_cutoff=0.3

        # get valences from the structure, otherwise analysis will not be performed!
        valences = [getattr(site.specie, "oxi_state", None) for site in structure]
        valences = [v for v in valences if v is not None]
        if len(valences) == len(structure):


            # space group should be saved!

            sga = SpacegroupAnalyzer(structure)
            symm_struct = sga.get_symmetrized_structure()

            # We will only focus on cations!
            inequivalent_indices_cations = [
                indices[0]  for indices in symm_struct.equivalent_indices if valences[indices[0]]>0.0
            ]
            inequivalent_indices = [
                indices[0] for indices in symm_struct.equivalent_indices
            ]

            # list of wyckoffs should be saved!
            wyckoffs_unique = symm_struct.wyckoff_symbols
            # We will now use ChemEnv with it's simplest strategy and only look at cation-anion bonds
            lgf = LocalGeometryFinder()
            lgf.setup_structure(structure=structure)

            se = lgf.compute_structure_environments(
                maximum_distance_factor=distance_cutoff + 0.01,
                only_indices=inequivalent_indices,
                valences=valences,
            )

            # might want to save the strategy?
            strategy = SimplestChemenvStrategy(
                distance_cutoff=distance_cutoff, angle_cutoff=angle_cutoff
            )

            lse = LightStructureEnvironments.from_structure_environments(
                strategy=strategy, structure_environments=se
            )

            all_ce = AllCoordinationGeometries()

            # save the environments
            envs = []
            unknown_sites = []

            list_mol=[]
            list_chemenv=[]
            list_chemenv_iupac=[]
            list_sites_env=[]
            list_wyckoff=[]
            list_species=[]
            for index, wyckoff in zip(inequivalent_indices, wyckoffs_unique):
                if index in inequivalent_indices_cations:
                    if not lse.neighbors_sets[index]:
                        list_chemenv.append('undefined')
                        list_chemenv_iupac.append('undefined')
                        list_mol.append('undefined')
                        list_wyckoff.append(wyckoff)
                        list_species.append(unicodeify_species(structure[index].species_string))

                        continue

                    # represent the local environment as a molecule
                    mol = Molecule.from_sites(
                        [structure[index]] + lse.neighbors_sets[index][0].neighb_sites
                    )
                    mol = mol.get_centered_molecule()

                    env = lse.coordination_environments[index]
                    co = all_ce.get_geometry_from_mp_symbol(env[0]["ce_symbol"])
                    name = co.name
                    if co.alternative_names:
                        name += f" (also known as {', '.join(co.alternative_names)})"

                    list_chemenv.append(name)
                    list_chemenv_iupac.append(co.IUPAC_symbol_str)
                    list_mol.append(mol)
                    list_wyckoff.append(wyckoff)
                    list_species.append(unicodeify_species(structure[index].species_string))


            d = {
                "valences": valences,
                "cationic_species": list_species,
                "chemenv_symbol": list_chemenv,
                "chemenv_iupac": list_chemenv_iupac,
                "mol_from_site_environments": list_mol,
                "wyckoff_positions": list_wyckoff,
                "method": "ChemEnv with SimplestChemEnvStrategy (distance-cutoff 1.4, angle-cutoff 0.3) was used for all unique cations in the structure.",
                "state": "successful"
            }  # type: dict
        else:
            d={}



        return super().from_structure(
            meta_structure=structure,
            material_id=material_id,
            structure=structure,
            **d,
            **kwargs
        )
