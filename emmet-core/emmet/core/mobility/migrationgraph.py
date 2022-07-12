from datetime import datetime
from typing import List, Union, Dict

from pydantic import BaseModel, Field, validator
from emmet.core.base import EmmetBaseModel
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph


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
