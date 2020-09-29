from typing import Optional, Dict, Iterator, List, Set
from itertools import chain
from collections import defaultdict

from pymatgen import Structure
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.analysis.structure_analyzer import oxide_type

from maggma.core import Store, Builder
from emmet.core.vasp.calc_types import run_type
from emmet.builders.utils import (
    maximal_spanning_non_intersecting_subsets,
    chemsys_permutations,
)


class Thermo(Builder):
    def __init__(
        self,
        materials: Store,
        tasks: Store,
        thermo: Store,
        query: Optional[Dict] = None,
        use_statics: bool = False,
        compatibility=None,
        **kwargs,
    ):
        """
        Calculates thermodynamic quantities for materials from phase
        diagram constructions

        Args:
            materials (Store): Store of materials documents
            thermo (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
            use_statics: Use the statics to compute thermodynamic information
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
        """

        self.materials = materials
        self.tasks = tasks
        self.thermo = thermo
        self.query = query if query else {}
        self.compatibility = (
            compatibility
            if compatibility
            else MaterialsProjectCompatibility("Advanced")
        )
        self._entries_cache = defaultdict(list)
        super().__init__(sources=[materials, tasks], targets=[thermo], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Basic search index for tasks
        self.tasks.ensure_index(self.tasks.key)

        # Search index for materials
        self.materials.ensure_index(self.materials.key)
        self.materials.ensure_index("sandboxes")
        self.materials.ensure_index(self.materials.last_updated_field)

        # Search index for thermo
        self.thermo.ensure_index(self.thermo.key)
        self.thermo.ensure_index(self.thermo.last_updated_field)

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets whole chemical systems of entries to process
        """

    def get_entries(self, chemsys: str) -> List[ComputedEntry]:
        """
        Gets a entries from the tasks collection for the corresponding chemical systems
        Args:
            chemsys(str): a chemical system represented by string elements seperated by a dash (-)
        Returns:
            set(ComputedEntry): a set of entries for this system
        """

    def get_updated_chemsys(
        self,
    ) -> Set:
        """ Gets updated chemical system as defined by the updating of an existing material """

    def get_new_chemsys(self) -> Set:
        """ Gets newer chemical system as defined by introduction of a new material """

    def get_affected_chemsys(self, chemical_systems: Set) -> Set:
        """ Gets chemical systems affected by changes in the supplied chemical systems """
