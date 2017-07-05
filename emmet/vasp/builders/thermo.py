import logging
from datetime import datetime
from itertools import chain, combinations

from pymatgen import Structure, Composition
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen.phasediagram.maker import PhaseDiagram, PhaseDiagramError
from pymatgen.phasediagram.analyzer import PDAnalyzer

from maggma.builder import Builder

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ThermoBuilder(Builder):
    def __init__(self, materials, thermo, query={}, compatibility=MaterialsProjectCompatibility('Advanced'), **kwargs):
        """
        Calculates thermodynamic quantities for materials from phase diagram constructions

        Args:
            materials (Store): Store of materials documents
            thermo (Store): Store of thermodynamic data such as formation energy and decomposition pathway
            query (dict): dictionary to limit materials to be analyzed
            compatibility (PymatgenCompatability): Compatability module to ensure energies are compatible
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query
        self.__compat = compatibility


        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(logging.NullHandler())

        super().__init__(sources=[materials],
                         targets=[thermo],
                         **kwargs)

    def get_items(self):
        """
        Gets sets of entries from chemical systems that need to be processed 

        Returns:
            generator of relevant entries from one chemical system
        """

        self.__logger.info("Thermo Builder Started")

        # All relevant materials that have been updated since thermo props were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.thermo))
        comps = [m['elements'] for m in self.materials().find(q, {"elements": 1})]

        self.__logger.info("Found {} compositions with new/updated materials".format(len(comps)))

        # Only yields maximal super sets: e.g. if ["A","B"] and ["A"] are both in the list, will only yield ["A","B"]
        # as this will calculate thermo props for all ["A"] compounds
        processed = set()
        # Start with the largest set to ensure we don't miss superset/subset relations
        for chemsys in sorted(comps, key=lambda x: len(x), reverse=True):
            if "-".join(sorted(chemsys)) not in processed:
                processed |= self.chemsys_permutations(chemsys)
                yield self.get_entries(chemsys)

    def chemsys_permutations(self, chemsys):
        # Fancy way of getting every unique permutation of elements for all possible number of elements:
        return {"-".join(sorted(c)) for c in
                chain(*[combinations(chemsys, i) for i in range(1, len(chemsys) + 1)])}

    def get_entries(self, chemsys):
        """
        Get all entries in a chemsys from materials
        
        Args:
            chemsys([str]): a chemical system represented by an array of elements
            
        Returns:
            set(ComputedEntry): a set of entries for this system
        """

        new_q = dict(self.query)
        new_q["chemsys"] = {"$in": list(self.chemsys_permutations(chemsys))}
        fields = {f: 1 for f in ["material_id", "thermo.energy", "unit_cell_formula", "calc_settings"]}
        data = list(self.materials().find(new_q, fields))

        all_entries = []
        for d in data:
            parameters = {"is_hubbard": d['calc_settings']["is_hubbard"],
                          "hubbards": d['calc_settings']["hubbards"],
                          "potcar_spec": d['calc_settings']["potcar_spec"]
                          }
            entry = ComputedEntry(Composition(d["unit_cell_formula"]),
                                  d["thermo"]["energy"], 0.0, parameters=parameters,
                                  entry_id=d["material_id"])

            all_entries.append(entry)

        return set(all_entries)

    def process_item(self, item):
        """
        Process the list of entries into a phase diagram

        Args:
            item (set(entry)): a list of entries to process into a phase diagram
            
        Returns:
            [dict]: a list of thermo dictionaries to update thermo with
        """
        entries = self.__compat.process_entries(item)
        try:
            pd = PhaseDiagram(entries)
            analyzer = PDAnalyzer(pd)

            docs = []

            for e in entries:
                (decomp, ehull) = \
                    analyzer.get_decomp_and_e_above_hull(e)

                d = {"material_id": e.entry_id}
                d["thermo"] = {}
                d["thermo"]["formation_energy_per_atom"] = pd.get_form_energy_per_atom(e)
                d["thermo"]["e_above_hull"] = ehull
                d["thermo"]["is_stable"] = e in stable_entries
                d["thermo"]["eq_reaction_e"] = analyzer.get_equilibrium_reaction_energy(e)
                d["thermo"]["decomposes_to"] = [{"material_id": de.entry_id,
                                                 "formula": de.composition.formula,
                                                 "amount": amt}
                                                for de, amt in decomp.items()]
                docs.append(d)
        except PhaseDiagramError as p:
            self.__logger.warning("Phase diagram error: {}".format(p))
            return []

        return docs

    def update_targets(self, items):
        """
        Inserts the thermo docs into the thermo collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """
        items = list(chain(*items))

        self.__logger.info("Updating {} thermo documents".format(len(items)))

        for doc in items:
            doc[self.thermo.lu_field] = datetime.utcnow()
            self.thermo().replace_one({"material_id": doc['material_id']}, doc, upsert=True)

    def finalize(self):
        pass
