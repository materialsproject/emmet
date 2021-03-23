from collections import defaultdict
from datetime import datetime
from itertools import chain
from typing import Dict, Iterator, List, Optional, Set, Tuple

from maggma.core import Builder, Store
from monty.json import MontyDecoder
from pymatgen.core import Structure
from pymatgen.analysis.phase_diagram import PhaseDiagramError
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.utils import jsanitize
from emmet.builders.utils import (
    chemsys_permutations,
    maximal_spanning_non_intersecting_subsets,
)
from emmet.core.thermo import ThermoDoc
from emmet.core.vasp.calc_types import run_type


class Thermo(Builder):
    def __init__(
        self,
        materials: Store,
        thermo: Store,
        query: Optional[Dict] = None,
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
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query if query else {}
        self.compatibility = (
            compatibility
            if compatibility
            else MaterialsProjectCompatibility("Advanced")
        )
        self._completed_tasks = set()
        self._entries_cache = defaultdict(list)
        super().__init__(sources=[materials], targets=[thermo], **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("last_updated")

        # Search index for thermo
        self.thermo.ensure_index("material_id")
        self.thermo.ensure_index("last_updated")

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
        to_process_chemsys = set()
        for chemsys in updated_chemsys | new_chemsys | affected_chemsys:
            if chemsys not in to_process_chemsys:
                to_process_chemsys |= chemsys_permutations(chemsys)

        self.logger.info(
            f"Found {len(to_process_chemsys)} chemical systems with new/updated materials to process"
        )
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(to_process_chemsys, key=lambda x: len(x.split("-"))):
            entries = self.get_entries(chemsys)
            yield entries

    def process_item(self, item: Tuple[List[str], List[ComputedEntry]]):

        entries = item
        if len(entries) == 0:
            return []

        entries = [ComputedStructureEntry.from_dict(entry) for entry in entries]
        # determine chemsys
        elements = sorted(
            set([el.symbol for e in entries for el in e.composition.elements])
        )
        chemsys = "-".join(elements)

        self.logger.debug(f"Processing {len(entries)} entries for {chemsys}")

        material_entries = defaultdict(dict)
        pd_entries = []
        for entry in entries:
            material_entries[entry.entry_id][entry.data["run_type"]] = entry

        # TODO: How to make this general and controllable via SETTINGS?
        for material_id in material_entries:
            if "GGA+U" in material_entries[material_id]:
                pd_entries.append(material_entries[material_id]["GGA+U"])
            elif "GGA" in material_entries[material_id]:
                pd_entries.append(material_entries[material_id]["GGA"])
        pd_entries = self.compatibility.process_entries(pd_entries)
        self.logger.debug(f"{len(pd_entries)} remain in {chemsys} after filtering")

        try:
            docs = ThermoDoc.from_entries(pd_entries)
            for doc in docs:
                doc.entries = material_entries[doc.material_id]
                doc.entry_types = list(material_entries[doc.material_id].keys())

        except PhaseDiagramError as p:
            elsyms = []
            for e in entries:
                elsyms.extend([el.symbol for el in e.composition.elements])

            self.logger.warning(
                f"Phase diagram error in chemsys {'-'.join(sorted(set(elsyms)))}: {p}"
            )
            return []
        except Exception as e:
            self.logger.error(
                f"Got unexpected error while processing {[ent_.entry_id for ent_ in entries]}: {e}"
            )
            return []

        return [d.dict() for d in docs]

    def update_targets(self, items):
        """
        Inserts the thermo docs into the thermo collection
        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        # flatten out lists
        items = list(filter(None, chain.from_iterable(items)))
        # Check if already updated this run
        items = [i for i in items if i[self.thermo.key] not in self._completed_tasks]

        self._completed_tasks |= {i[self.thermo.key] for i in items}

        for item in items:
            if isinstance(item["last_updated"], dict):
                item["last_updated"] = MontyDecoder().process_decoded(
                    item["last_updated"]
                )

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} thermo documents")
            self.thermo.update(docs=jsanitize(items), key=[self.thermo.key])
        else:
            self.logger.info("No items to update")

    def get_entries(self, chemsys: str) -> List[Dict]:
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
                criteria=new_q, properties=[self.materials.key, "entries"]
            )
        )

        self.logger.debug(
            f"Got {len(materials_docs)} entries from DB for {len(query_chemsys)} sub-chemsys for {chemsys}"
        )

        # Convert the entries into ComputedEntries and store
        for doc in materials_docs:
            for r_type, entry_dict in doc.get("entries", {}).items():
                entry_dict["data"]["run_type"] = r_type
                elsyms = sorted(set([el for el in entry_dict["composition"]]))
                self._entries_cache["-".join(elsyms)].append(entry_dict)
                all_entries.append(entry_dict)

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
        q = {"material_id": {"$in": dif_task_ids}}
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
