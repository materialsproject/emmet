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

        self.logger.info("Thermo Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        updated_chemsys = self.get_updated_chemsys()
        new_chemsys = self.get_new_chemsys()

        affected_chemsys = self.get_affected_chemsys(updated_chemsys | new_chemsys)

        # Remove overlapping chemical systems
        to_process_chemsys = {}
        for chemsys in updated_chemsys | new_chemsys | affected_chemsys:
            if chemsys not in to_process_chemsys:
                to_process_chemsys |= chemsys_permutations(chemsys)

        self.logger.inf(
            f"Found {len(to_process_chemsys)} chemical systems with new/updated materials to process"
        )
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(to_process_chemsys, key=lambda x: len(x.split("-"))):
            yield self.get_entries(chemsys)

    def get_entries(self, chemsys: str) -> List[ComputedEntry]:
        """
        Gets a entries from the tasks collection for the corresponding chemical systems
        Args:
            chemsys(str): a chemical system represented by string elements seperated by a dash (-)
        Returns:
            set(ComputedEntry): a set of entries for this system
        """

        self.logger.info(f"Getting entries for: {chemsys}")

        # First check the cache
        all_chemsys = chemsys_permutations(chemsys)
        cached_chemsys = all_chemsys & set(self._entries_cache.keys())
        query_chemsys = all_chemsys - cached_chemsys
        all_entries = list(
            chain.from_iterable(self._entries_cache[c] for c in cached_chemsys)
        )

        self.logger.debug(
            f"Getting {len(cached_chemsys)} sub-chemsys from cache for {chemsys}"
        )
        self.logger.debug(
            f"Getting {len(query_chemsys)} sub-chemsys from DB for {chemsys}"
        )

        # Second grab the materials docs
        new_q = dict(self.query)
        new_q["chemsys"] = {"$in": list(query_chemsys)}
        new_q["deprecated"] = False
        materials_docs = list(
            self.materials.query(
                criteria=new_q, properties=[self.materials.key, "entries", "sandboxes"]
            )
        )

        self.logger.debug(
            f"Got {len(materials_docs)} entries from DB for {len(query_chemsys)} sub-chemsys for {chemsys}"
        )

        # Convert the entries into ComputedEntries and store
        new_entries = [
            entry for doc in materials_docs for entry in doc.get("entries", {}).values()
        ]
        for entry in new_entries:
            entry = ComputedEntry.from_dict(entry)
            elsyms = sorted(set([el.symbol for el in entry.composition.elements]))
            self._entries_cache["-".join(elsyms)].append(entry)
            all_entries.append(entry)

        self.logger.info(f"Total entries in {chemsys} : {len(all_entries)}")

        return all_entries

    def get_updated_chemsys(
        self,
    ) -> Set:
        """ Gets updated chemical system as defined by the updating of an existing material """

        updated_mats = self.thermo.newer_in(self.materials, criteria=self.query)
        updated_chemsys = set(
            self.materials.distinct(
                "chemsys", {self.materials.key: {"$in": list(updated_mats)}}
            )
        )
        self.logger.debug(f"Found {len(updated_chemsys)} updated chemical systems")

        return updated_chemsys

    def get_new_chemsys(self) -> Set:
        """ Gets newer chemical system as defined by introduction of a new material """

        # All materials that are not present in the thermo collection
        thermo_mat_ids = self.thermo.distinct(self.thermo.key)
        mat_ids = self.materials.distinct(self.materials.key, self.query)
        dif_task_ids = list(set(mat_ids) - set(thermo_mat_ids))
        q = {"task_id": {"$in": dif_task_ids}}
        new_mat_chemsys = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(new_mat_chemsys)} new chemical systems")

        return new_mat_chemsys

    def get_affected_chemsys(self, chemical_systems: Set) -> Set:
        """ Gets chemical systems affected by changes in the supplied chemical systems """
        # First get all chemsys with any of the elements we've marked
        affected_chemsys = set()
        affected_els = list({el for c in chemical_systems for el in c.split("-")})
        possible_affected_chemsys = self.materials.distinct(
            "chemsys", {"elements": {"$in": affected_els}}
        )

        sub_chemsys = defaultdict(list)
        # Build a dictionary mapping sub_chemsys to all super_chemsys
        for chemsys in possible_affected_chemsys:
            for permutation in chemsys_permutations(chemsys):
                sub_chemsys[permutation].append(chemsys)

        # Select and merge distinct super chemsys from sub_chemsys
        for chemsys in chemical_systems:
            affected_chemsys |= set(sub_chemsys[chemsys])

        self.logger.debug(
            f"Found {len(affected_chemsys)} chemical systems affected by this build"
        )

        return affected_chemsys
