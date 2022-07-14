from datetime import datetime
from email.mime import base
from tarfile import FIFOTYPE
from typing import List, Union, Dict, Tuple
from attr import fields_dict
from pandas import describe_option

from pydantic import BaseModel, Field, validator
from emmet.core.base import EmmetBaseModel
from pymatgen.core import Structure
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from pymatgen.analysis.diffusion.utils.supercells import get_sc_fromstruct
from pyparsing import unicode_set


class MigrationGraphDoc(EmmetBaseModel):
    """
    MigrationGraph Doc.
    Stores MigrationGraph and info such as ComputedStructureEntries (ComputedEntry can be used for working ion) and cutoff distance that are used to generated the object.
    Note: this doc is not self-contained within pymatgen, as it has dependence on pymatgen.analysis.diffusion, a namespace package aka pymatgen-diffusion.
    """

    battery_id: str = Field(None, description="The battery id for this MigrationGraphDoc")

    last_updated: datetime = Field(
        None,
        description="Timestamp for the most recent calculation for this MigrationGraph document.",
    )

    hop_cutoff: float = Field(
        None,
        description="The numerical value in angstroms used to cap the maximum length of a hop."
    )

    entries_for_generation: List[ComputedStructureEntry] = Field(
        None,
        description="A list of ComputedStructureEntries used to generate the structure with all working ion sites."
    )

    working_ion_entry: Union[ComputedEntry, ComputedStructureEntry] = Field(
        None,
        description="The ComputedStructureEntry of the working ion."
    )

    migration_graph: MigrationGraph = Field(
        None,
        description="The MigrationGraph object as defined in pymatgen.analysis.diffusion."
    )

    matrix_supercell_structure: Structure = Field(
        None,
        description="The matrix suprcell structure that does not contain the mobile ions for the purpose of migration analysis."
    )

    conversion_matrix: List = Field(
        None,
        description="The conversion matrix used to convert unit cell to supercell."
    )

    min_length_sc: float = Field(
        None,
        description="The minimum length used to generate supercell using pymatgen."
    )

    min_max_num_atoms: Tuple[int] = Field(
        None,
        description="The min/max number of atoms used to genreate supercell using pymatgen."
    )

    inserted_ion_coords: Dict = Field(
        None,
        description="A dictionary containing all mobile ion fractional coordinates in terms of supercell."
    )

    insert_coords_combo: List[str] = Field(
        None,
        description="A list of combinations 'a+b' to designate hops in the supercell. Each combo should correspond to one unique hop in MigrationGraph."
    )

    @classmethod
    def from_entries_and_distance(
        cls,
        battery_id: str,
        grouped_entries: List[ComputedStructureEntry],
        working_ion_entry: Union[ComputedEntry, ComputedStructureEntry],
        hop_cutoff: float
    ) -> Union["MigrationGraphDoc", None]:
        """
        This classmethod takes a group of ComputedStructureEntries (can also use ComputedEntry for wi) and generates a full sites structure.
        Then a MigrationGraph object is generated with with_distance() method with a designated cutoff.
        """

        ranked_structures = MigrationGraph.get_structure_from_entries(
            entries=grouped_entries,
            migrating_ion_entry=working_ion_entry
        )
        max_sites_struct = ranked_structures[0]

        migration_graph = MigrationGraph.with_distance(
            structure=max_sites_struct,
            migrating_specie=working_ion_entry.composition.chemical_system,
            max_distance=hop_cutoff
        )

        return cls(
            battery_id=battery_id,
            hop_cutoff=hop_cutoff,
            entries_for_generation=grouped_entries,
            working_ion_entry=working_ion_entry,
            migration_graph=migration_graph
        )

    @staticmethod
    def generate_sc_fields(
        uc_struct: Structure,
        entries: List[ComputedStructureEntry],
        min_length: float,
        min_max_num_atoms: Tuple[int]
    )

    min_length = min_length,
    min_max_num_atoms = min_max_num_atoms

    host_sc = get_sc_fromstruct(
        base_struct=uc_struct,
        min_atoms=min_max_num_atoms[0],
        max_atoms=min_max_num_atoms[1],
        min_length=min_length
    )

    coords = []

    combo = []

    return host_sc, conversion_matrix, min_length, min_max_num_atoms, coords, combo
