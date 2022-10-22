import warnings
from collections import defaultdict
from itertools import chain
from typing import Dict, Iterable, Iterator, List, Optional, Set
from math import ceil

from maggma.core import Builder, Store
from maggma.utils import grouper
from monty.json import MontyDecoder
from pymatgen.analysis.phase_diagram import PhaseDiagramError
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.entries.compatibility import Compatibility

from emmet.builders.utils import chemsys_permutations, HiddenPrints
from emmet.core.thermo import ThermoDoc, PhaseDiagramDoc, ThermoType
from emmet.core.utils import jsanitize


class ThermoBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        thermo: Store,
        phase_diagram: Optional[Store] = None,
        oxidation_states: Optional[Store] = None,
        query: Optional[Dict] = None,
        compatibility: Optional[List[Compatibility]] = None,
        num_phase_diagram_eles: Optional[int] = None,
        chunk_size: int = 1000,
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
            compatibility ([Compatability]): Compatability module
                to ensure energies are compatible
            num_phase_diagram_eles (int): Maximum number of elements to use in phase diagram construction
                for data within the separate phase_diagram collection
            chunk_size (int): Size of chemsys chunks to process at any one time.
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query if query else {}
        self.compatibility = compatibility or [None]
        self.oxidation_states = oxidation_states
        self.phase_diagram = phase_diagram
        self.num_phase_diagram_eles = num_phase_diagram_eles
        self.chunk_size = chunk_size
        self._completed_tasks: Set[str] = set()
        self._entries_cache: Dict[str, List[ComputedStructureEntry]] = defaultdict(list)

        if self.thermo.key != "thermo_id":
            warnings.warn(
                f"Key for the thermo store is incorrect and has been changed from {self.thermo.key} to thermo_id!"
            )
            self.thermo.key = "thermo_id"

        if self.materials.key != "material_id":
            warnings.warn(
                f"Key for the materials store is incorrect and has been changed from {self.materials.key} to material_id!"  # noqa: E501
            )
            self.materials.key = "material_id"

        sources = [materials]

        if self.oxidation_states is not None:

            if self.oxidation_states.key != "material_id":
                warnings.warn(
                    f"Key for the oxidation states store is incorrect and has been changed from {self.oxidation_states.key} to material_id!"  # noqa:E501
                )
                self.oxidation_states.key = "material_id"

            sources.append(oxidation_states)  # type: ignore

        targets = [thermo]

        if self.phase_diagram is not None:

            if self.phase_diagram.key != "phase_diagram_id":
                warnings.warn(
                    f"Key for the phase diagram store is incorrect and has been changed from {self.thphase_diagramermo.key} to phase_diagram_id!"  # noqa: E501
                )
                self.phase_diagram.key = "phase_diagram_id"

            targets.append(phase_diagram)  # type: ignore

        super().__init__(sources=sources, targets=targets, chunk_size=chunk_size, **kwargs)

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
        self.thermo.ensure_index("thermo_id")
        self.thermo.ensure_index("thermo_type")
        self.thermo.ensure_index("last_updated")

        # Search index for phase_diagram
        if self.phase_diagram:
            self.phase_diagram.index.ensure_index("chemsys")
            self.phase_diagram.index.ensure_index("phase_diagram_id")

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
        for chemsys in sorted(updated_chemsys | new_chemsys | affected_chemsys, key=lambda x: len(x), reverse=True,):
            if chemsys not in processed:
                processed |= chemsys_permutations(chemsys)
                to_process_chemsys.append(chemsys)

        self.logger.info(f"Found {len(to_process_chemsys)} chemical systems with new/updated materials to process")
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(to_process_chemsys, key=lambda x: len(x.split("-")), reverse=False):
            entries = self.get_entries(chemsys)
            yield entries

    def process_item(self, item: List[Dict]):

        if len(item) == 0:
            return []

        entries = [ComputedStructureEntry.from_dict(entry) for entry in item]
        # determine chemsys
        elements = sorted(set([el.symbol for e in entries for el in e.composition.elements]))
        chemsys = "-".join(elements)

        self.logger.debug(f"Processing {len(entries)} entries for {chemsys}")

        all_entry_types = {str(e.data["run_type"]) for e in entries}

        docs_pd_pair_list = []

        for compatability in self.compatibility:

            pd_entries = []

            if compatability:
                if compatability.name == "MP DFT mixing scheme":
                    thermo_type = ThermoType.GGA_GGA_U_R2SCAN
                elif compatability.name == "MP2020":
                    thermo_type = ThermoType.GGA_GGA_U
                else:
                    thermo_type = ThermoType.UNKNOWN

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with HiddenPrints():
                        if "R2SCAN" in all_entry_types:
                            combined_pd_entries = compatability.process_entries(entries)
                            only_scan_pd_entries = [e for e in entries if str(e.data["run_type"]) == "R2SCAN"]

                            combined_pair = self._produce_pair(combined_pd_entries, thermo_type, elements)
                            scan_only_pair = self._produce_pair(only_scan_pd_entries, ThermoType.R2SCAN, elements)

                            docs_pd_pair_list.append(combined_pair)
                            docs_pd_pair_list.append(scan_only_pair)

                        else:
                            pd_entries = compatability.process_entries(entries)
                            pd_pair = self._produce_pair(pd_entries, thermo_type, elements)

                            docs_pd_pair_list.append(pd_pair)

            else:
                if len(all_entry_types) > 1:
                    raise ValueError("More than one functional type has been provided without a mixing scheme!")
                else:
                    thermo_type = all_entry_types.pop()

                pd_pair = self._produce_pair(entries, thermo_type, elements)

                docs_pd_pair_list.append(pd_pair)

        return docs_pd_pair_list

    def _produce_pair(self, pd_entries, thermo_type, elements):
        # Produce thermo and phase diagram pair

        try:
            docs, pds = ThermoDoc.from_entries(pd_entries, thermo_type, deprecated=False)

            pd_docs = [None]

            if self.phase_diagram:
                if self.num_phase_diagram_eles is None or len(elements) <= self.num_phase_diagram_eles:
                    pd_docs = []

                    for pd in pds:
                        chemsys = "-".join(sorted(set([e.symbol for e in pd.elements])))
                        pd_id = "{}_{}".format(chemsys, str(thermo_type))
                        pd_doc = PhaseDiagramDoc(
                            phase_diagram_id=pd_id, chemsys=chemsys, phase_diagram=pd, thermo_type=thermo_type,
                        )

                        pd_data = jsanitize(pd_doc.dict(), allow_bson=True)

                        pd_docs.append(pd_data)

            docs_pd_pair = (
                jsanitize([d.dict() for d in docs], allow_bson=True),
                pd_docs,
            )

            return docs_pd_pair

        except PhaseDiagramError as p:
            elsyms = []
            for e in pd_entries:
                elsyms.extend([el.symbol for el in e.composition.elements])

            self.logger.error(f"Phase diagram error in chemsys {'-'.join(sorted(set(elsyms)))}: {p}")
            return (None, None)

    def update_targets(self, items):
        """
        Inserts the thermo and phase diagram docs into the thermo collection
        Args:
            items ([[tuple(List[dict],List[dict])]]): a list of list of thermo dictionaries to update
        """

        thermo_docs = [item[0] for pair_list in items for item in pair_list]
        phase_diagram_docs = [item[1] for pair_list in items for item in pair_list]

        # flatten out lists
        thermo_docs = list(filter(None, chain.from_iterable(thermo_docs)))
        phase_diagram_docs = list(filter(None, chain.from_iterable(phase_diagram_docs)))

        # Check if already updated this run
        thermo_docs = [i for i in thermo_docs if i["thermo_id"] not in self._completed_tasks]

        self._completed_tasks |= {i["thermo_id"] for i in thermo_docs}

        for item in thermo_docs:
            if isinstance(item["last_updated"], dict):
                item["last_updated"] = MontyDecoder().process_decoded(item["last_updated"])

        if self.phase_diagram:
            self.phase_diagram.update(phase_diagram_docs)

        if len(thermo_docs) > 0:
            self.logger.info(f"Updating {len(thermo_docs)} thermo documents")
            self.thermo.update(docs=thermo_docs, key=["thermo_id"])
        else:
            self.logger.info("No thermo items to update")

    def get_entries(self, chemsys: str) -> List[Dict]:
        """
        Gets entries from the materials collection for the corresponding chemical systems
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
        all_entries = list(chain.from_iterable(self._entries_cache[c] for c in cached_chemsys))

        self.logger.debug(f"Getting {len(cached_chemsys)} sub-chemsys from cache for {chemsys}")
        self.logger.debug(f"Getting {len(query_chemsys)} sub-chemsys from DB for {chemsys}")

        # Second grab the materials docs
        new_q = dict(self.query)
        new_q["chemsys"] = {"$in": list(query_chemsys)}
        new_q["deprecated"] = False

        materials_docs = list(self.materials.query(criteria=new_q, properties=["material_id", "entries", "deprecated"]))

        # Get Oxidation state data for each material
        oxi_states_data = {}
        if self.oxidation_states:
            material_ids = [t["material_id"] for t in materials_docs]
            oxi_states_data = {
                d["material_id"]: d.get("average_oxidation_states", {})
                for d in self.oxidation_states.query(
                    properties=["material_id", "average_oxidation_states"],
                    criteria={"material_id": {"$in": material_ids}, "state": "successful"},
                )
            }

        self.logger.debug(
            f"Got {len(materials_docs)} entries from DB for {len(query_chemsys)} sub-chemsys for {chemsys}"
        )

        # Convert entries into ComputedEntries and store
        for doc in materials_docs:
            for r_type, entry_dict in doc.get("entries", {}).items():
                entry_dict["data"]["oxidation_states"] = oxi_states_data.get(entry_dict["data"]["material_id"], {})
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
            self.materials.distinct("chemsys", {"material_id": {"$in": list(updated_mats)}, **self.query})
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
        possible_affected_chemsys = self.materials.distinct("chemsys", {"elements": {"$in": affected_els}})

        sub_chemsys = defaultdict(list)
        # Build a dictionary mapping sub_chemsys to all super_chemsys
        for chemsys in possible_affected_chemsys:
            for permutation in chemsys_permutations(chemsys):
                sub_chemsys[permutation].append(chemsys)

        # Select and merge distinct super chemsys from sub_chemsys
        for chemsys in chemical_systems:
            affected_chemsys |= set(sub_chemsys[chemsys])

        self.logger.debug(f"Found {len(affected_chemsys)} chemical systems affected by this build")

        return affected_chemsys
