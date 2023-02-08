from math import ceil
import warnings
from itertools import chain
from typing import Dict, Iterator, List, Optional, Set

from maggma.core import Builder, Store
from maggma.stores import S3Store
from maggma.utils import grouper
from monty.json import MontyDecoder
from pymatgen.analysis.phase_diagram import PhaseDiagramError
from pymatgen.entries.computed_entries import ComputedStructureEntry

from emmet.builders.utils import HiddenPrints
from emmet.core.thermo import ThermoDoc, PhaseDiagramDoc
from emmet.core.utils import jsanitize


class ThermoBuilder(Builder):
    def __init__(
        self,
        thermo: Store,
        corrected_entries: Store,
        phase_diagram: Optional[Store] = None,
        query: Optional[Dict] = None,
        num_phase_diagram_eles: Optional[int] = None,
        chunk_size: int = 1000,
        **kwargs,
    ):
        """
        Calculates thermodynamic quantities for materials from phase
        diagram constructions

        Args:
            thermo (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            corrected_entries (Store): Store of corrected entry data to use in thermo data and phase diagram
                construction. This is required and should be built with the CorrectedEntriesBuilder.
            phase_diagram (Store): Store of phase diagram data for each unique chemical system
            query (dict): dictionary to limit materials to be analyzed
            num_phase_diagram_eles (int): Maximum number of elements to use in phase diagram construction
                for data within the separate phase_diagram collection
            chunk_size (int): Size of chemsys chunks to process at any one time.
        """

        self.thermo = thermo
        self.query = query if query else {}
        self.corrected_entries = corrected_entries
        self.phase_diagram = phase_diagram
        self.num_phase_diagram_eles = num_phase_diagram_eles
        self.chunk_size = chunk_size
        self._completed_tasks: Set[str] = set()

        if self.thermo.key != "thermo_id":
            warnings.warn(
                f"Key for the thermo store is incorrect and has been changed from {self.thermo.key} to thermo_id!"
            )
            self.thermo.key = "thermo_id"

        if self.corrected_entries.key != "chemsys":
            warnings.warn(
                "Key for the corrected entries store is incorrect and has been changed "
                f"from {self.corrected_entries.key} to chemsys!"
            )
            self.corrected_entries.key = "chemsys"

        sources = [corrected_entries]
        targets = [thermo]

        if self.phase_diagram is not None:

            if self.phase_diagram.key != "phase_diagram_id":
                warnings.warn(
                    f"Key for the phase diagram store is incorrect and has been changed from {self.phase_diagram.key} to phase_diagram_id!"  # noqa: E501
                )
                self.phase_diagram.key = "phase_diagram_id"

            targets.append(phase_diagram)  # type: ignore

        super().__init__(sources=sources, targets=targets, chunk_size=chunk_size, **kwargs)

    def ensure_indexes(self):
        """
        Ensures indicies on the tasks and materials collections
        """

        # Search index for corrected_entries
        self.corrected_entries.ensure_index("chemsys")
        self.corrected_entries.ensure_index("last_updated")

        # Search index for thermo
        self.thermo.ensure_index("material_id")
        self.thermo.ensure_index("thermo_id")
        self.thermo.ensure_index("thermo_type")
        self.thermo.ensure_index("last_updated")

        # Search index for thermo
        self.thermo.ensure_index("material_id")
        self.thermo.ensure_index("thermo_id")
        self.thermo.ensure_index("thermo_type")
        self.thermo.ensure_index("last_updated")

        # Search index for phase_diagram
        if self.phase_diagram:
            coll = self.phase_diagram

            if isinstance(self.phase_diagram, S3Store):
                coll = self.phase_diagram.index

            coll.ensure_index("chemsys")
            coll.ensure_index("phase_diagram_id")

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        to_process_chemsys = self._get_chemsys_to_process()

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

        to_process_chemsys = self._get_chemsys_to_process()

        self.logger.info(f"Found {len(to_process_chemsys)} chemical systems with new/updated materials to process")
        self.total = len(to_process_chemsys)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(to_process_chemsys, key=lambda x: len(x.split("-")), reverse=False):
            corrected_entries = self.corrected_entries.query_one({"chemsys": chemsys})
            yield corrected_entries

    def process_item(self, item):

        if not item:
            return None

        pd_thermo_doc_pair_list = []

        for thermo_type, entry_list in item["entries"].items():

            if entry_list:
                entries = [ComputedStructureEntry.from_dict(entry) for entry in entry_list]
                chemsys = item["chemsys"]
                elements = chemsys.split("-")

                self.logger.debug(f"Processing {len(entries)} entries for {chemsys} and thermo type {thermo_type}")

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with HiddenPrints():

                        pd_thermo_doc_pair_list.append(self._produce_pair(entries, thermo_type, elements))

        return pd_thermo_doc_pair_list

    def _produce_pair(self, pd_entries, thermo_type, elements):
        # Produce thermo and phase diagram pair

        try:
            # Obtain phase diagram
            pd = ThermoDoc.construct_phase_diagram(pd_entries)

            # Iterate through entry material IDs and construct list of thermo docs to update
            docs = ThermoDoc.from_entries(pd_entries, thermo_type, pd, use_max_chemsys=True, deprecated=False)

            pd_docs = [None]

            if self.phase_diagram:
                if self.num_phase_diagram_eles is None or len(elements) <= self.num_phase_diagram_eles:
                    chemsys = "-".join(sorted(set([e.symbol for e in pd.elements])))
                    pd_id = "{}_{}".format(chemsys, str(thermo_type))
                    pd_doc = PhaseDiagramDoc(
                        phase_diagram_id=pd_id, chemsys=chemsys, phase_diagram=pd, thermo_type=thermo_type,
                    )

                    pd_data = jsanitize(pd_doc.dict(), allow_bson=True)

                    pd_docs = [pd_data]

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
            items ([[tuple(List[dict],List[dict])]]): a list of a list of thermo and phase diagram dict pairs to update
        """

        thermo_docs = [pair[0] for pair_list in items for pair in pair_list]
        phase_diagram_docs = [pair[1] for pair_list in items for pair in pair_list]

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

    def _get_chemsys_to_process(self):
        # Use last-updated to find new chemsys
        corrected_entries_chemsys_dates = {
            d[self.corrected_entries.key]: d[self.corrected_entries.last_updated_field]
            for d in self.corrected_entries.query(
                self.query, properties=[self.corrected_entries.key, self.corrected_entries.last_updated_field]
            )
        }

        thermo_chemsys_dates = {}
        for d in self.thermo.query(
            {"deprecated": False}, properties=[self.corrected_entries.key, self.thermo.last_updated_field]
        ):

            entry = thermo_chemsys_dates.get(d[self.corrected_entries.key], None)
            if entry is None or d[self.thermo.last_updated_field] < entry:
                thermo_chemsys_dates[d[self.corrected_entries.key]] = d[self.thermo.last_updated_field]

        to_process_chemsys = [
            chemsys
            for chemsys in corrected_entries_chemsys_dates
            if (chemsys not in thermo_chemsys_dates)
            or (thermo_chemsys_dates[chemsys] < corrected_entries_chemsys_dates[chemsys])
        ]

        return to_process_chemsys
