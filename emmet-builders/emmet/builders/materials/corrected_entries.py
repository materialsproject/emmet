import warnings
from collections import defaultdict
from itertools import chain
from typing import Dict, Iterable, Iterator, List, Optional
from math import ceil
import copy

from maggma.core import Builder, Store
from maggma.utils import grouper
from pymatgen.entries.computed_entries import ComputedStructureEntry
from pymatgen.entries.compatibility import Compatibility

from emmet.core.utils import jsanitize
from emmet.builders.utils import chemsys_permutations, HiddenPrints
from emmet.core.thermo import ThermoType
from emmet.core.corrected_entries import CorrectedEntriesDoc


class CorrectedEntriesBuilder(Builder):
    def __init__(
        self,
        materials: Store,
        corrected_entries: Store,
        oxidation_states: Optional[Store] = None,
        query: Optional[Dict] = None,
        compatibility: Optional[List[Compatibility]] = None,
        chunk_size: int = 1000,
        **kwargs,
    ):
        """
        Produces corrected thermo entry data from uncorrected materials entries.
        This is meant to be an intermediate builder for the main thermo builder.

        Args:
            materials (Store): Store of materials documents
            corrected_entries (Store): Store to output corrected entry data
            oxidation_states (Store): Store of oxidation state data to use in correction scheme application
            query (dict): dictionary to limit materials to be analyzed
            compatibility ([Compatibility]): Compatibility module
                to ensure energies are compatible
            chunk_size (int): Size of chemsys chunks to process at any one time.
        """

        self.materials = materials
        self.query = query if query else {}
        self.corrected_entries = corrected_entries
        self.compatibility = compatibility or [None]
        self.oxidation_states = oxidation_states
        self.chunk_size = chunk_size
        self._entries_cache: Dict[str, List[ComputedStructureEntry]] = defaultdict(list)

        if self.corrected_entries.key != "chemsys":
            warnings.warn(
                "Key for the corrected_entries store is incorrect and has been changed "
                f"from {self.corrected_entries.key} to thermo_id!"
            )
            self.corrected_entries.key = "chemsys"

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

        targets = [corrected_entries]

        super().__init__(
            sources=sources, targets=targets, chunk_size=chunk_size, **kwargs
        )

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Search index for materials
        self.materials.ensure_index("material_id")
        self.materials.ensure_index("chemsys")
        self.materials.ensure_index("last_updated")

        # Search index for corrected_entries
        self.corrected_entries.ensure_index("chemsys")

    def prechunk(self, number_splits: int) -> Iterable[Dict]:  # pragma: no cover
        to_process_chemsys = self._get_chemsys_to_process()

        N = ceil(len(to_process_chemsys) / number_splits)

        for chemsys_chunk in grouper(to_process_chemsys, N):
            yield {"query": {"chemsys": {"$in": list(chemsys_chunk)}}}

    def get_items(self) -> Iterator[List[Dict]]:
        """
        Gets whole chemical systems of entries to process
        """

        self.logger.info("Corrected Entries Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indexes()

        to_process_chemsys = self._get_chemsys_to_process()

        self.logger.info(
            f"Processing entries in {len(to_process_chemsys)} chemical systems"
        )
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        for chemsys in sorted(
            to_process_chemsys, key=lambda x: len(x.split("-")), reverse=False
        ):
            entries = self.get_entries(chemsys)
            yield entries

    def process_item(self, item):
        """
        Applies correction schemes to entries and constructs CorrectedEntriesDoc objects
        """

        if not item:
            return None

        entries = [ComputedStructureEntry.from_dict(entry) for entry in item]
        # determine chemsys
        elements = sorted(
            set([el.symbol for e in entries for el in e.composition.elements])
        )
        chemsys = "-".join(elements)

        self.logger.debug(f"Processing {len(entries)} entries for {chemsys}")

        all_entry_types = {str(e.data["run_type"]) for e in entries}

        corrected_entries = {}

        for compatibility in self.compatibility:
            if compatibility is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with HiddenPrints():
                        if compatibility.name == "MP DFT mixing scheme":
                            thermo_type = ThermoType.GGA_GGA_U_R2SCAN

                            if "R2SCAN" in all_entry_types:
                                only_scan_pd_entries = [
                                    e
                                    for e in entries
                                    if str(e.data["run_type"]) == "R2SCAN"
                                ]
                                corrected_entries["R2SCAN"] = only_scan_pd_entries

                                pd_entries = compatibility.process_entries(
                                    copy.deepcopy(entries)
                                )

                            else:
                                corrected_entries["R2SCAN"] = None
                                pd_entries = None

                        elif compatibility.name == "MP2020":
                            thermo_type = ThermoType.GGA_GGA_U
                            pd_entries = compatibility.process_entries(
                                copy.deepcopy(entries)
                            )
                        else:
                            thermo_type = ThermoType.UNKNOWN
                            pd_entries = compatibility.process_entries(
                                copy.deepcopy(entries)
                            )

                        corrected_entries[str(thermo_type)] = pd_entries

            else:
                if len(all_entry_types) > 1:
                    raise ValueError(
                        "More than one functional type has been provided without a mixing scheme!"
                    )
                else:
                    thermo_type = all_entry_types.pop()

                corrected_entries[str(thermo_type)] = copy.deepcopy(entries)

        doc = CorrectedEntriesDoc(chemsys=chemsys, entries=corrected_entries)

        return jsanitize(doc.model_dump(), allow_bson=True)

    def update_targets(self, items):
        """
        Inserts the new corrected entry docs into the corrected entries collection
        """

        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Updating {len(docs)} corrected entry documents")
            self.corrected_entries.update(docs=docs, key=["chemsys"])
        else:
            self.logger.info("No corrected entry items to update")

    def get_entries(self, chemsys: str) -> List[Dict]:
        """
        Gets entries from the materials collection for the corresponding chemical systems
        Args:
            chemsys (str): a chemical system represented by string elements seperated by a dash (-)
        Returns:
            set (ComputedEntry): a set of entries for this system
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

        # Convert entries into ComputedEntries and store
        for doc in materials_docs:
            for r_type, entry_dict in doc.get("entries", {}).items():
                entry_dict["data"]["oxidation_states"] = oxi_states_data.get(
                    entry_dict["data"]["material_id"], {}
                )
                entry_dict["data"]["run_type"] = r_type
                elsyms = sorted(set([el for el in entry_dict["composition"]]))
                self._entries_cache["-".join(elsyms)].append(entry_dict)
                all_entries.append(entry_dict)

        self.logger.info(f"Total entries in {chemsys} : {len(all_entries)}")

        return all_entries

    def _get_chemsys_to_process(self):
        # Use last-updated to find new chemsys
        materials_chemsys_dates = {}
        for d in self.materials.query(
            {"deprecated": False, **self.query},
            properties=[self.corrected_entries.key, self.materials.last_updated_field],
        ):
            entry = materials_chemsys_dates.get(d[self.corrected_entries.key], None)
            if entry is None or d[self.materials.last_updated_field] > entry:
                materials_chemsys_dates[d[self.corrected_entries.key]] = d[
                    self.materials.last_updated_field
                ]

        corrected_entries_chemsys_dates = {
            d[self.corrected_entries.key]: d[self.corrected_entries.last_updated_field]
            for d in self.corrected_entries.query(
                {},
                properties=[
                    self.corrected_entries.key,
                    self.corrected_entries.last_updated_field,
                ],
            )
        }

        to_process_chemsys = [
            chemsys
            for chemsys in materials_chemsys_dates
            if (chemsys not in corrected_entries_chemsys_dates)
            or (
                materials_chemsys_dates[chemsys]
                > corrected_entries_chemsys_dates[chemsys]
            )
        ]

        return to_process_chemsys
