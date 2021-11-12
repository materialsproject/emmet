import warnings
from collections import defaultdict
from itertools import chain
from typing import Dict, Iterable, Iterator, List, Optional, Set
from math import ceil

from maggma.core import Builder, Store
from maggma.utils import grouper
from monty.json import MontyDecoder
from pymatgen.analysis.phase_diagram import PhaseDiagramError
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.entries.computed_entries import ComputedStructureEntry

from emmet.builders.utils import chemsys_permutations
from emmet.core.thermo import ThermoDoc, PhaseDiagramDoc
from emmet.core.utils import jsanitize


class ThermoBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        thermo: Store,
        phase_diagram: Optional[Store] = None,
        oxidation_states: Optional[Store] = None,
        query: Optional[Dict] = None,
        compatibility=None,
        num_phase_diagram_eles: Optional[int] = None,
        **kwargs,
    ):
        """
        Calculates thermodynamic quantities for materials from phase
        diagram constructions

        Args:
            materials (Store): Store of materials documents
            thermo (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            phase_diagram (Store): Store of phase diagram data for each unique chemical system
            oxidation_states (Store): Store of oxidation state data to use in correction scheme application
            query (dict): dictionary to limit materials to be analyzed
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible
            num_phase_diagram_eles (int): Maximum number of elements to use in phase diagram construction
                for data within the separate phase_diagram collection
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query if query else {}
        self.compatibility = (
            compatibility
            if compatibility
            else MaterialsProject2020Compatibility("Advanced")
        )
        self.oxidation_states = oxidation_states
        self.phase_diagram = phase_diagram
        self.num_phase_diagram_eles = num_phase_diagram_eles
        self._completed_tasks: Set[str] = set()
        self._entries_cache: Dict[str, List[ComputedStructureEntry]] = defaultdict(list)

        sources = [materials]
        if oxidation_states is not None:
            sources.append(oxidation_states)

        targets = [thermo]
        if phase_diagram is not None:
            targets.append(phase_diagram)

        super().__init__(sources=sources, targets=targets, **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("chemsys")
        self.materials.ensure_index("last_updated")

        # Search index for thermo
        self.thermo.ensure_index("material_id")
        self.thermo.ensure_index("last_updated")

        # Search index for phase_diagram
        if self.phase_diagram:
            self.phase_diagram.ensure_index("chemsys")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        updated_chemsys = self.get_updated_chemsys()
        new_chemsys = self.get_new_chemsys()

        affected_chemsys = self.get_affected_chemsys(updated_chemsys | new_chemsys)

        # Remove overlapping chemical systems
        to_process_chemsys = set()
        for chemsys in updated_chemsys | new_chemsys | affected_chemsys:
            if chemsys not in to_process_chemsys:
                to_process_chemsys |= chemsys_permutations(chemsys)

        N = ceil(len(to_process_chemsys) / number_splits)

        for chemsys_chunk in grouper(to_process_chemsys, N):

            yield {"query": {"chemsys": {"$in": list(chemsys_chunk)}}}

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
        processed = set()
        to_process_chemsys = []
        for chemsys in sorted(
            updated_chemsys | new_chemsys | affected_chemsys,
            key=lambda x: len(x),
            reverse=True,
        ):
            if chemsys not in processed:
                processed |= chemsys_permutations(chemsys)
                to_process_chemsys.append(chemsys)

        self.logger.info(
            f"Found {len(to_process_chemsys)} chemical systems with new/updated materials to process"
        )
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(
            to_process_chemsys, key=lambda x: len(x.split("-")), reverse=False
        ):
            entries = self.get_entries(chemsys)
            yield entries

    def process_item(self, item: List[Dict]):

        if len(item) == 0:
            return []

        entries = [ComputedStructureEntry.from_dict(entry) for entry in item]
        # determine chemsys
        elements = sorted(
            set([el.symbol for e in entries for el in e.composition.elements])
        )
        chemsys = "-".join(elements)

        self.logger.debug(f"Processing {len(entries)} entries for {chemsys}")

        material_entries: Dict[str, Dict[str, ComputedStructureEntry]] = defaultdict(
            dict
        )
        pd_entries = []
        for entry in entries:
            material_entries[entry.entry_id][entry.data["run_type"]] = entry

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", message="Failed to guess oxidation states.*"
            )
            pd_entries = self.compatibility.process_entries(entries)
        self.logger.debug(f"{len(pd_entries)} remain in {chemsys} after filtering")

        try:
            docs, pd = ThermoDoc.from_entries(pd_entries, deprecated=False)
            for doc in docs:
                doc.entries = material_entries[doc.material_id]
                doc.entry_types = list(material_entries[doc.material_id].keys())

            pd_data = None

            if self.phase_diagram:
                if (
                    self.num_phase_diagram_eles is None
                    or len(elements) <= self.num_phase_diagram_eles
                ):
                    pd_doc = PhaseDiagramDoc(chemsys=chemsys, phase_diagram=pd)
                    pd_data = jsanitize(pd_doc.dict(), allow_bson=True)

            docs_pd_pair = (
                jsanitize([d.dict() for d in docs], allow_bson=True),
                [pd_data],
            )

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

        return docs_pd_pair

    def update_targets(self, items):
        """
        Inserts the thermo and phase diagram docs into the thermo collection
        Args:
            items ([[tuple(List[dict],List[dict])]]): a list of list of thermo dictionaries to update
        """

        # print(len(items))

        thermo_docs = [item[0] for item in items]
        phase_diagram_docs = [item[1] for item in items]

        # flatten out lists
        thermo_docs = list(filter(None, chain.from_iterable(thermo_docs)))
        phase_diagram_docs = list(filter(None, chain.from_iterable(phase_diagram_docs)))

        # Check if already updated this run
        thermo_docs = [
            i for i in thermo_docs if i["material_id"] not in self._completed_tasks
        ]

        self._completed_tasks |= {i["material_id"] for i in thermo_docs}

        for item in thermo_docs:
            if isinstance(item["last_updated"], dict):
                item["last_updated"] = MontyDecoder().process_decoded(
                    item["last_updated"]
                )

        if self.phase_diagram:
            self.phase_diagram.update(phase_diagram_docs)

        if len(thermo_docs) > 0:
            self.logger.info(f"Updating {len(thermo_docs)} thermo documents")
            self.thermo.update(docs=thermo_docs, key=["material_id"])
        else:
            self.logger.info("No thermo items to update")

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
                criteria=new_q, properties=["material_id", "entries", "deprecated"]
            )
        )

        # Get Oxidation state data for each material
        oxi_states_data = {}
        if self.oxidation_states:
            material_ids = [t["material_id"] for t in materials_docs]
            oxi_states_data = {
                d["material_id"]: d.get("average_oxidation_states", {})
                for d in self.oxidation_states.query(
                    properties=["material_id", "average_oxidation_states"],
                    criteria={
                        "material_id": {"$in": material_ids},
                        "state": "successful",
                    },
                )
            }

        self.logger.debug(
            f"Got {len(materials_docs)} entries from DB for {len(query_chemsys)} sub-chemsys for {chemsys}"
        )

        # Convert the entries into ComputedEntries and store
        for doc in materials_docs:
            for r_type, entry_dict in doc.get("entries", {}).items():
                entry_dict["data"]["oxidation_states"] = oxi_states_data.get(
                    entry_dict["entry_id"], {}
                )
                entry_dict["data"]["run_type"] = r_type
                elsyms = sorted(set([el for el in entry_dict["composition"]]))
                self._entries_cache["-".join(elsyms)].append(entry_dict)
                all_entries.append(entry_dict)

        self.logger.info(f"Total entries in {chemsys} : {len(all_entries)}")

        return all_entries

    def get_updated_chemsys(self,) -> Set:
        """Gets updated chemical system as defined by the updating of an existing material"""

        updated_mats = self.thermo.newer_in(self.materials, criteria=self.query)
        updated_chemsys = set(
            self.materials.distinct(
                "chemsys", {"material_id": {"$in": list(updated_mats)}, **self.query}
            )
        )
        self.logger.debug(f"Found {len(updated_chemsys)} updated chemical systems")

        return updated_chemsys

    def get_new_chemsys(self) -> Set:
        """Gets newer chemical system as defined by introduction of a new material"""

        # All materials that are not present in the thermo collection
        thermo_mat_ids = self.thermo.distinct("material_id")
        mat_ids = self.materials.distinct("material_id", self.query)
        dif_task_ids = list(set(mat_ids) - set(thermo_mat_ids))
        q = {"material_id": {"$in": dif_task_ids}}
        new_mat_chemsys = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(new_mat_chemsys)} new chemical systems")

        return new_mat_chemsys

    def get_affected_chemsys(self, chemical_systems: Set) -> Set:
        """Gets chemical systems affected by changes in the supplied chemical systems"""
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
