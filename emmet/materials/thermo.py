from itertools import chain, combinations
from collections import defaultdict

from pymatgen import Structure
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.analysis.structure_analyzer import oxide_type

from maggma.builders import Builder

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
        self._entries_cache = defaultdict(list)
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
        q.update(self.materials.lu_filter(self.thermo))
        updated_chemsys = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(updated_chemsys)} updated chemical systems")

        # All materials that are not present in the thermo collection
        thermo_mat_ids = self.thermo.distinct(self.thermo.key)
        mat_ids = self.materials.distinct(self.materials.key, self.query)
        dif_task_ids = list(set(mat_ids) - set(thermo_mat_ids))
        q = dict(self.query)
        q.update({"task_id": {"$in": dif_task_ids}})
        new_mat_chemsys = set(self.materials.distinct("chemsys", q))
        self.logger.debug(f"Found {len(new_mat_chemsys)} new chemical systems")

        # All comps affected by changing these chemical systems
        # IE if we update Li-O, we need to update Li-Mn-O, Li-Mn-P-O, etc.
        affected_chemsys = set()
        affected_els = list(
            {el for c in updated_chemsys | new_mat_chemsys for el in c.split("-")}
        )
        possible_affected_chemsys = self.materials.distinct(
            "chemsys", {"elements": {"$in": affected_els}}
        )

        sub_chemsys = defaultdict(list)
        # Build a dictionary mapping sub_chemsys to all super_chemsys
        for chemsys in possible_affected_chemsys:
            for permutation in chemsys_permutations(chemsys):
                sub_chemsys[permutation].append(chemsys)

        # Select and merge distinct super chemsys from sub_chemsys
        for chemsys in updated_chemsys | new_mat_chemsys:
            affected_chemsys |= set(sub_chemsys[chemsys])

        self.logger.debug(
            f"Found {len(affected_chemsys)} chemical systems affected by this build"
        )

        comps = updated_chemsys | new_mat_chemsys | affected_chemsys
        self.logger.info(f"Found {len(comps)} compositions with new/updated materials")
        self.total = len(comps)

        # Yield the chemical systems in order of increasing size
        # Will build them in a similar manner to fast Pourbaix
        for chemsys in sorted(comps, key=lambda x: len(x.split("-"))):
            yield self.get_entries(chemsys)

    def process_item(self, entries):
        """
        Process the list of entries into thermo docs for each sandbox
        Args:
            item (set(entry)): a list of entries to process into a phase diagram

        Returns:
            [dict]: a list of thermo dictionaries to update thermo with
        """

        docs = []

        # build sandbox sets: ["a"] , ["a","b"], ["core","a","b"]
        sandbox_sets = set(
            [frozenset(entry.data.get("_sbxn", {})) for entry in entries]
        )
        sandbox_sets = maximal_spanning_non_intersecting_subsets(sandbox_sets)
        self.logger.debug(f"Found {len(sandbox_sets)}: {sandbox_sets}")

        for sandboxes in sandbox_sets:

            # only yield maximal subsets so that we can process a equivalent sandbox combinations at a time
            entries = [
                entry
                for entry in entries
                if all(sandbox in entry.data.get("_sbxn", []) for sandbox in sandboxes)
            ]

            entries = self.compatibility.process_entries(entries)

            # determine chemsys
            chemsys = "-".join(
                sorted(
                    set([el.symbol for e in entries for el in e.composition.elements])
                )
            )

            processed_docs = self.process_pd(entries)
            for d in processed_docs:
                d["_sbxn"] = sorted(sandboxes)

            self.logger.debug(
                f"Processed {len(entries)} entries for {chemsys} - {sandboxes}"
            )
            docs.extend(processed_docs)

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
        items = [i for i in items if i["chemsys"] not in self._entries_cache]

        # Add stable entries to my entries cache
        for entry in items:
            if entry["thermo"]["is_stable"]:
                self._entries_cache[entry["chemsys"]].append(
                    ComputedEntry.from_dict(entry["thermo"]["entry"])
                )

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
        self.materials.ensure_index(self.materials.lu_field)
        self.materials.ensure_index("chemsys")
        self.materials.ensure_index("elements")
        self.materials.ensure_index("_sbxn")

        # Search indicies for thermo
        self.thermo.ensure_index(self.thermo.key)
        self.thermo.ensure_index(self.thermo.lu_field)
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

        self.logger.debug(f"Getting entries for: {chemsys}")

        entries = []
        for query_chemsys in chemsys_permutations(chemsys):
            if query_chemsys in self._entries_cache:
                # Get the stable entries from the entries cache

                self.logger.debug(
                    f"Got {len(self._entries_cache[query_chemsys])} entries"
                    f"from Cache for {query_chemsys} sub-chemsys for {chemsys}"
                )
                entries.extend(self._entries_cache[query_chemsys])
            else:

                # Query for any chemsys we don't have
                new_q = dict(self.query)

                new_q["chemsys"] = query_chemsys
                new_q["deprecated"] = False

                fields = ["structure", "entries", "_sbxn", "task_id"]
                data = list(self.materials.query(properties=fields, criteria=new_q))

                self.logger.debug(
                    f"Got {len(data)} entries from DB for "
                    f"{query_chemsys} sub-chemsys for {chemsys}"
                )
                for d in data:
                    entry_type = "gga_u" if "gga_u" in d["entries"] else "gga"
                    entry = d["entries"][entry_type]
                    entry["correction"] = 0.0
                    entry["entry_id"] = d["task_id"]
                    entry = ComputedEntry.from_dict(entry)
                    entry.data["oxide_type"] = oxide_type(
                        Structure.from_dict(d["structure"])
                    )
                    entry.data["_sbxn"] = d.get("_sbxn", [])
                    entries.append(entry)

        self.logger.info(f"Total entries in {chemsys} : {len(entries)}")

        return entries

    def process_pd(self, entries):
        docs = []
        try:
            pd = PhaseDiagram(entries)

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
                d["thermo"]["explanation"] = self.compatibility.get_explanation_dict(e)

                elsyms = sorted(set([el.symbol for el in e.composition.elements]))
                d["chemsys"] = "-".join(elsyms)
                d["nelements"] = len(elsyms)
                d["elements"] = list(elsyms)
                docs.append(d)

        except PhaseDiagramError as p:
            elsyms = []
            for e in entries:
                elsyms.extend([el.symbol for el in e.composition.elements])

            self.logger.warning(
                f"Phase diagram errorin chemsys {'-'.join(sorted(set(elsyms)))}: {p}"
            )
        except Exception as e:
            self.logger.error(f"Got unexpected error: {e}")

        return docs


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
