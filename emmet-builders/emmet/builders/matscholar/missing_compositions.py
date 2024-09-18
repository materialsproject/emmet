from itertools import combinations
import itertools
from math import ceil
from typing import Dict, List, Iterator, Optional

from maggma.core import Builder
from maggma.stores import S3Store, MongoURIStore, MongoStore
from maggma.utils import grouper
from pymatgen.core import Composition, Element


class MissingCompositionsBuilder(Builder):
    """
    Builder that finds compositions not found in the
    Materials Project for each chemical system.
    Based on the Text Mining project in MPContribs.
    """

    def __init__(
        self,
        phase_diagram: S3Store,
        mpcontribs: MongoURIStore,
        missing_compositions: MongoStore,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Arguments:
            phase_diagram: source store for chemsys data
            matsholar_store: source store for matscholar data
            missing_compositions: Target store to save the missing compositions
            query: dictionary to query the phase diagram store
            **kwargs: Additional keyword arguments
        """
        self.phase_diagram = phase_diagram
        self.mpcontribs = mpcontribs
        self.missing_compositions = missing_compositions
        self.query = query
        self.kwargs = kwargs
        # TODO: make sure the two lines below are needed?
        self.phase_diagram.key = "phase_diagram_id"
        self.missing_compositions.key = "chemical_system"

        super().__init__(
            sources=[phase_diagram, mpcontribs],
            targets=[missing_compositions],
            **kwargs,
        )

    def prechunk(self, number_splits: int) -> Iterator[Dict]:  # pragma: no cover
        """
        Prechunk method to perform chunking by the key field
        """
        q = self.query or {}  # type: ignore

        keys = self.missing_compositions.newer_in(
            self.phase_diagram, criteria=q, exhaustive=True
        )

        N = ceil(len(keys) / number_splits)
        for split in grouper(keys, N):
            yield {"query": {self.phase_diagram.key: {"$in": list(split)}}}

    def get_items(self) -> Iterator[Dict]:
        """
        Returns all chemical systems (combinations of elements)
        to process.
        Enumarates all chemical systems and queries the
        phase diagram for each system, in the case where
        the chemical system is not found in the phase diagram,
        it returns a dictionary with the chemical system
        and an empty list for the missing compositions
        """
        self.logger.info("Missing Composition Builder Started")
        self.logger.info("Setting up chemical systems to process")
        elements = set()
        # get all elements
        elements = set([e.symbol for e in Element])

        # Generate all unique combinations of elements to form chemical systems
        chemical_systems = []
        for r in range(2, 5):
            for combination in combinations(elements, r):
                system = "-".join(sorted([str(element) for element in combination]))
                chemical_systems.append(system)
        q = self.query or {}
        projection = {
            "chemsys": 1,
            "phase_diagram.all_entries.composition": 1,
        }
        for sys in chemical_systems:
            q.update({"chemsys": sys})
            self.logger.info(f"Querying phase diagram for {sys}")
            try:
                items = self.phase_diagram.query(criteria=q, properties=projection)
                # combine all entries from all phase diagrams
                all_entries = []
                for item in items:
                    all_entries = [
                        i["composition"] for i in item["phase_diagram"]["all_entries"]
                    ]

                # Find missing compositions
                matscholar_entries = self._get_entries_in_chemsys(sys)
                doc = {
                    "chemsys": sys,
                    "all_compositions": all_entries,
                    "matscholar_entries": matscholar_entries,
                }
                yield doc
            except Exception as ex:
                self.logger.error(f"Erro looking for phase diagram for {sys}: {ex}")
                continue

    def process_item(self, item: Dict) -> Dict:
        """
        Processes a chemical system and finds missing c
        ompositions for that system.
        Note that it returns a missing_compositions dict
        regardless of whether there is a missing composition,
        in which case, it contains an empty dictionary for
        the missing_composition_entries field.
        """
        compositions = set()
        chemsys = item["chemsys"]
        matscholar_entries = item["matscholar_entries"]
        self.logger.info(
            "Querying entries in MPContribs matscholar"
            f"project for the chemical system {chemsys}"
        )
        missing_compositions = {
            "chemical_system": chemsys,
            "missing_composition_entries": {},
        }

        if len(item["all_compositions"]) > 0:
            # Get the compositions from retrieved entries,
            # and use its reduced_formula
            for entry in item["all_compositions"]:
                composition = Composition.from_dict(entry)
                # Note the reduced formula is a string
                # instead of a Composition object
                compositions.add(composition.reduced_formula)

            if len(matscholar_entries) == 0:
                self.logger.info(
                    "No entries found in MPContribs" "for the chemical system"
                )

            else:
                self.logger.info(
                    f"Found {len(matscholar_entries)}"
                    "entries in MPContribs for the chemical system"
                )

                for entry in matscholar_entries:
                    # Comparing reduced formulae from MPContribs
                    # and Phase Diagram
                    if (
                        Composition(entry["formula"]).reduced_formula
                        not in compositions
                    ):
                        # this formula doesn't exist in the dictionary,
                        # make an entry in the missing_compositions dict
                        if (
                            entry["formula"]
                            not in missing_compositions[
                                "missing_composition_entries"
                            ].keys()
                        ):
                            missing_compositions["missing_composition_entries"].update(
                                {
                                    entry["formula"]: [
                                        {"link": entry["link"], "doi": entry["doi"]}
                                    ]
                                }
                            )
                        # formula already exists in the dictionary, append the new entry
                        else:
                            missing_compositions["missing_composition_entries"][
                                entry["formula"]
                            ].append({"link": entry["link"], "doi": entry["doi"]})

        return missing_compositions

    def update_targets(self, items):
        """
        Updates the target store with the missing compositions
        """
        docs = list(filter(None, items))

        if len(docs) > 0:
            self.logger.info(f"Found {len(docs)} chemical-system docs to update")
            self.missing_compositions.update(items)
        else:
            self.logger.info("No items to update")

    def _get_entries_in_chemsys(self, chemsys) -> List:
        """Queries the MPContribs Store for entries in a chemical system."""
        # get sub-systems
        chemsys_subsystems = []
        elements = chemsys.split("-")
        # get all possible combinations
        for i in range(2, len(elements) + 1):
            chemsys_subsystems += [
                "-".join(sorted(c)) for c in itertools.combinations(elements, i)
            ]

        results = []
        for subsystem in chemsys_subsystems:
            try:
                query = {"project": "matscholar", "data.chemsys": subsystem}
                fields = ["formula", "data"]
                entries = self.mpcontribs.query(criteria=query, properties=fields)
                for entry in entries:
                    results.append({"formula": entry["formula"], **entry["data"]})
            except Exception as ex:
                self.logger.error(f"Error querying MPContribs for {subsystem}: {ex}")
        return results
