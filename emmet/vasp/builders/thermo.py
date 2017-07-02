from datetime import datetime

from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from maggma.builder import Builder
from itertools import chain, combinations
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen import Structure, Composition
from pymatgen.phasediagram.maker import PhaseDiagram, PhaseDiagramError
from pymatgen.phasediagram.analyzer import PDAnalyzer

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


class ThermoBuilder(Builder):
    def __init__(self, materials, thermo, query={}, compatibility=MaterialsProjectCompatibility('Advanced'), **kwargs):
        """
        Calculates thermodynamic quantities for materials from phase diagram constructions

        Args:
            materials (Store): Store of materials documents
            thermo (Store): Store of thermodynamic data such as formation energy and decomposition pathway
            query (dict): dictionary to limit tasks to be analyzed
            compatibility (PymatgenCompatability): Compatability module to ensure energies are compatible
        """

        self.materials = materials
        self.thermo = thermo
        self.query = query
        self.__compat = compatibility

        super().__init__(sources=[materials],
                         targets=[thermo],
                         **kwargs)

    def get_items(self):
        """
        Gets sets of entries from chemical systems that need to be processed 

        Returns:
            generator of relevant entries from one chemical system
        """
        q = dict(self.query)

        # Find materials that need an update
        # 1.) All new materials
        to_update = set(self.materials().find(q).distinct("material_id")) - set(
            self.thermo().find().distinct("material_id"))
        # 2.) All materials that have been updated since thermo props were last calculated
        m_lu = self.materials.lu_field
        t_lu = self.thermo.lu_field
        mat_updated_dates = {m['material_id']: m[m_lu] for m in
                             self.materials().find(q, {"material_id": 1, m_lu: 1})}
        thermo_updated_dates = {t['material_id']: t[t_lu] for t in
                                self.thermo().find({}, {"material_id": 1, t_lu: 1})}
        to_update |= {m for m, d in mat_updated_dates.items() if d > thermo_updated_dates.get(m, datetime.min)}

        # TODO: Make this more efficient
        # TODO: Reduce down to supersets, no need to calcuate A-B if we're going to calc A-B-Cs
        comps = []
        for m in to_update:
            q['material_id'] = m
            comps.append(self.materials().find_one(q, {"elements": 1}).get('elements', {}))

        for chemsys in comps:
            yield self.get_entries(chemsys)

    def get_entries(self, chemsys):
        """
        Get all entries in a chemsys from materials
        
        Args:
            chemsys([str]): a chemical system represented by an array of elements
            
        Returns:
            set(ComputedEntry): a set of entries for this system
        """
        all_entries = []
        # Fancy way of getting every unique permutation of elements for all possible number of elements:
        chemsys_list = ["-".join(sorted(c)) for c in
                        chain(*[combinations(chemsys, i) for i in range(1, len(chemsys) + 1)])]
        new_q = dict(self.query)
        new_q["chemsys"] = {"$in": chemsys_list}
        fields = {f: 1 for f in ["material_id", "thermo.energy", "unit_cell_formula", "calc_settings"]}
        data = list(self.materials().find(new_q, fields))

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
            return []

        return docs

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): a list of list of thermo dictionaries to update
        """

        for doc in chain(*items):
            doc[self.thermo.lu_field] = datetime.utcnow()
            self.thermo().replace_one({"material_id": doc['material_id']}, doc, upsert=True)

    def finalize(self):
        pass
