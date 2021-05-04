import warnings

from itertools import chain, combinations
from collections import defaultdict
from datetime import datetime

from pymatgen.core import Structure, Composition
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.analysis.structure_analyzer import oxide_type

from maggma.builders import Builder
from maggma.utils import Timeout
from emmet.vasp.materials import ID_to_int

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ThermoBuilder(Builder):
    def __init__(self, materials, thermo, query=None, compatibility=None, **kwargs):
        """
        Calculates thermodynamic quantities for materials from phase
        diagram constructions

        Args:
            materials (Store): Store of materials documents
            thermo (Store): Store of thermodynamic data such as formation
                energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
            compatibility (PymatgenCompatability): Compatability module
                to ensure energies are compatible. If not specified
                (compatibility=None), defaults to MaterialsProject2020Compatibility.
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query if query else {}
        self.compatibility = (
            compatibility
            if compatibility
            else MaterialsProject2020Compatibility()
        )
        self.completed_tasks = set()
        self.entries_cache = defaultdict(list)
        super().__init__(sources=[materials], targets=[thermo], **kwargs)

    def get_items(self):
        """
        Gets sets of entries from chemical systems that need to be processed

        Returns:
            generator of relevant entries from one chemical system
        """
        self.logger.info("Thermo Builder Started")

        self.logger.info("Setting indexes")
        self.ensure_indicies()

        # All relevant materials that have been updated since thermo props were
        # last calculated
        q = dict(self.query)
        q.update(
            {self.materials.key: {"$in": list(self.thermo.newer_in(self.materials))}}
        )
        # All chemsys associated with updated materials
        updated_comps = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(updated_comps)} updated chemsys")

        # All materials that are not present in the thermo collection
        # convert all mat_ids into str in case the underlying type is heterogeneous
        thermo_mat_ids = {ID_to_int(t) for t in self.thermo.distinct(self.thermo.key)}
        mat_ids = {ID_to_int(t) for t in self.materials.distinct(self.materials.key, self.query)}
        dif_task_ids = list(mat_ids - thermo_mat_ids)
        q = dict(self.query)
        q.update({"task_id": {"$in": ["{}-{}".format(t[0], t[1]) if t[0] != "" else str(t[1]) for t in dif_task_ids ]}})
        # All chemsys associated with new materials no present in the thermo collection
        new_mat_comps = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(new_mat_comps)} new chemsys")

        # All chemsys affected by changing these chemical systems
        # IE if we update Li-O, we need to update Li-Mn-O, Li-Mn-P-O, etc.
        affected_comps = set()
        comps = updated_comps | new_mat_comps | affected_comps

        # Only process maximal super sets: e.g. if ["A","B"] and ["A"]
        # are both in the list, will only yield ["A","B"] as this will
        # calculate thermo props for all ["A"] compounds
        processed = set()

        to_process = []

        for chemsys in sorted(comps, key=lambda x: len(x.split("-")), reverse=True):
            if chemsys not in processed:
                processed |= chemsys_permutations(chemsys)
                to_process.append(chemsys)

        self.logger.info(
            f"Found {len(to_process)} chemsys with new/updated materials"
        )
        self.total = len(to_process)

        for chemsys in to_process:
            entries = self.get_entries(chemsys)

            # build sandbox sets: ["a"] , ["a","b"], ["core","a","b"]
            sandbox_sets = set(
                [frozenset(entry.data.get("_sbxn", {})) for entry in entries]
            )
            sandbox_sets = maximal_spanning_non_intersecting_subsets(sandbox_sets)
            self.logger.debug(f"Found {len(sandbox_sets)}: {sandbox_sets}")

            for sandboxes in sandbox_sets:
                # only yield maximal subsets so that we can process a equivalent sandbox combinations at a time
                sandbox_entries = [
                    entry
                    for entry in entries
                    if all(
                        sandbox in entry.data.get("_sbxn", []) for sandbox in sandboxes
                    )
                ]

                yield sorted(sandboxes), sandbox_entries

    def process_item(self, item):
        """
        Process the list of entries into thermo docs for each sandbox
        Args:
            item (set(entry)): a list of entries to process into a phase diagram

        Returns:
            [dict]: a list of thermo dictionaries to update thermo with
        """

        docs = []

        sandboxes, entries = item
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message="Failed to guess oxidation states")
            entries = self.compatibility.process_entries(entries, clean=True)

        # determine chemsys
        chemsys = "-".join(
            sorted(set([el.symbol for e in entries for el in e.composition.elements]))
        )

        self.logger.debug(
            f"Processing {len(entries)} entries for {chemsys} - {sandboxes}"
        )

        try:
            pd = build_pd(entries)

            docs = []

            for e in entries:
                (decomp, ehull) = pd.get_decomp_and_e_above_hull(e)

                d = {
                    self.thermo.key: e.entry_id,
                    "thermo": {
                        "energy": e.uncorrected_energy,
                        "energy_per_atom": e.uncorrected_energy
                        / e.composition.num_atoms,
                        "formation_energy_per_atom": pd.get_form_energy_per_atom(e),
                        "e_above_hull": ehull,
                        "is_stable": e in pd.stable_entries,
                    },
                }

                # Store different info if stable vs decomposes
                if d["thermo"]["is_stable"]:
                    d["thermo"]["eq_reaction_e"] = pd.get_equilibrium_reaction_energy(e)
                else:
                    d["thermo"]["decomposes_to"] = [
                        {
                            "task_id": de.entry_id,
                            "formula": de.composition.formula,
                            "amount": amt,
                        }
                        for de, amt in decomp.items()
                    ]

                d["thermo"]["entry"] = e.as_dict()
                d["thermo"]["explanation"] = {
                    "compatibility": e.energy_adjustments[0].cls["@class"] if len(e.energy_adjustments) > 0 else None,
                    "uncorrected_energy": e.uncorrected_energy,
                    "corrected_energy": e.energy,
                    "correction_uncertainty": e.correction_uncertainty,
                    "corrections": [
                        {"name": c.name,
                         "description": c.explain,
                         "value": c.value,
                         "uncertainty": c.uncertainty}
                        for c in e.energy_adjustments
                                    ]
                }

                elsyms = sorted(set([el.symbol for el in e.composition.elements]))
                d["chemsys"] = "-".join(elsyms)
                d["nelements"] = len(elsyms)
                d["elements"] = list(elsyms)
                d["_sbxn"] = sorted(sandboxes)
                d["last_updated"] = e.data["last_updated"]

                docs.append(d)
        except PhaseDiagramError as p:
            elsyms = []
            for e in entries:
                elsyms.extend([el.symbol for el in e.composition.elements])

            self.logger.warning(
                f"Phase diagram errorin chemsys {'-'.join(sorted(set(elsyms)))}: {p}"
            )
            return []
        except Exception as e:
            self.logger.error(f"Got unexpected error: {e}")
            return []

        return docs

    def update_targets(self, items):
        """
        Inserts the thermo docs into the thermo collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        # flatten out lists
        items = list(filter(None, chain.from_iterable(items)))
        # check for duplicates within this set
        items = list(
            {(v[self.thermo.key], frozenset(v["_sbxn"])): v for v in items}.values()
        )
        # Check if already updated this run
        items = [i for i in items if i[self.thermo.key] not in self.completed_tasks]

        self.completed_tasks |= {i[self.thermo.key] for i in items}

        if len(items) > 0:
            self.logger.info(f"Updating {len(items)} thermo documents")
            self.thermo.update(docs=items, key=[self.thermo.key, "_sbxn"])
        else:
            self.logger.info("No items to update")

    def ensure_indicies(self):
        """
        Ensures indicies on the thermo and materials collections
        :return:
        """
        # Search indicies for materials
        self.materials.ensure_index(self.materials.key, unique=True)
        self.materials.ensure_index(self.materials.last_updated_field)
        self.materials.ensure_index("chemsys")
        self.materials.ensure_index("elements")
        self.materials.ensure_index("_sbxn")

        # Search indicies for thermo
        self.thermo.ensure_index(self.thermo.key)
        self.thermo.ensure_index(self.thermo.last_updated_field)
        self.thermo.ensure_index("chemsys")
        self.thermo.ensure_index("_sbxn")

    def get_entries(self, chemsys):
        """
        Get all entries in a chemsys from materials

        Args:
            chemsys(str): a chemical system represented by string elements seperated by a dash (-)

        Returns:
            set(ComputedEntry): a set of entries for this system
        """

        self.logger.info(f"Getting entries for: {chemsys}")

        # First check the cache
        all_chemsys = chemsys_permutations(chemsys)
        cached_chemsys = all_chemsys & set(self.entries_cache.keys())
        query_chemsys = all_chemsys - cached_chemsys

        self.logger.debug(
            f"Getting {len(cached_chemsys)} sub-chemsys from cache for {chemsys}"
        )
        self.logger.debug(
            f"Getting {len(query_chemsys)} sub-chemsys from DB for {chemsys}"
        )

        # Query for any chemsys we don't have
        new_q = dict(self.query)

        new_q["chemsys"] = {"$in": list(query_chemsys)}
        new_q["deprecated"] = False

        fields = [
            "structure",
            self.materials.key,
            "entries",
            "_sbxn",
            "last_updated"
        ]
        data = list(self.materials.query(properties=fields, criteria=new_q))

        self.logger.debug(
            f"Got {len(data)} entries from DB for {len(query_chemsys)} sub-chemsys for {chemsys}"
        )
        # Start with entries from cache
        all_entries = list(
            chain.from_iterable(self.entries_cache[c] for c in cached_chemsys)
        )

        for d in data:
            if "gga_u" in d["entries"]:
                entry = d["entries"]["gga_u"]
            elif "gga" in d["entries"]:
                entry = d["entries"]["gga"]
            else:
                # we should only process GGA or GGA+U entries for now
                continue

            entry["entry_id"] = d["task_id"]
            entry = ComputedEntry.from_dict(entry)
            entry.data["oxide_type"] = oxide_type(Structure.from_dict(d["structure"]))
            entry.data["_sbxn"] = d.get("_sbxn", [])
            entry.data["last_updated"] = d.get("last_updated", datetime.utcnow())
            entry.data["oxidation_states"] = {}
            with Timeout():
                try:
                    oxi_states = entry.composition.oxi_state_guesses(max_sites=-20)
                except ValueError:
                    oxi_states = []

                if oxi_states != []:
                    entry.data["oxidation_states"] = oxi_states[0]

            # Add to cache
            elsyms = sorted(set([el.symbol for el in entry.composition.elements]))
            self.entries_cache["-".join(elsyms)].append(entry)

            all_entries.append(entry)

        self.logger.info(f"Total entries in {chemsys} : {len(all_entries)}")

        return all_entries


def chemsys_permutations(chemsys):
    # Fancy way of getting every unique permutation of elements for all
    # possible number of elements:
    elements = chemsys.split("-")
    return {
        "-".join(sorted(c))
        for c in chain(
            *[combinations(elements, i) for i in range(1, len(elements) + 1)]
        )
    }


def maximal_spanning_non_intersecting_subsets(sets):
    """
    Finds the maximal spanning non intersecting subsets of a group of sets
    This is usefull for parsing out the sandboxes and figuring out how to group
    and calculate these for thermo documents

    sets (set(frozenset)): sets of keys to subsect, expected as a set of frozensets
    """
    to_return_subsets = []

    # Find the overlapping portions and independent portions
    for subset in sets:
        for other_set in sets:
            subset = frozenset(subset.intersection(other_set)) or subset
        if subset:
            to_return_subsets.append(subset)

    # Remove accounted for elements and recurse on remaining sets
    accounted_elements = set(chain.from_iterable(to_return_subsets))
    sets = {frozenset(subset - accounted_elements) for subset in sets}
    sets = {subset for subset in sets if subset}

    if sets:
        to_return_subsets.extend(maximal_spanning_non_intersecting_subsets(sets))

    return set(to_return_subsets)


def build_pd(entries):
    """
    Reduces the number of entries for PhaseDiagram to consider
    To Speed it up
    """

    entries_by_comp = defaultdict(list)
    for e in entries:
        entries_by_comp[e.composition.reduced_formula].append(e)

    reduced_entries = [sorted(comp_entries,key=lambda e: e.energy_per_atom)[0] for comp_entries in entries_by_comp.values()]

    return PhaseDiagram(reduced_entries)