from datetime import datetime

from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from maggma.builder import Builder
from itertools import chain, combinations
from pymatgen.entries.computed_entries import ComputedEntry
from pymatgen import Structure, Composition

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
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials to process into materials documents
        """
        q = dict(self.query)

        # Find all chem systems that need to be update
        # 1.) Any system with a new material
        to_update = set(self.materials().find(q).distinct("material_id")) - set(
            self.thermo().find().distinct("material_id"))
        # 2.) Any system with an updated material
        mat_updated_dates = {m['material_id']: m['updated_at'] for m in
                             self.materials().find(q, {"material_id": 1, "updated_at": 1})}
        thermo_updated_dates = {m['material_id']: m['updated_at'] for m in
                                self.thermo().find({}, {"material_id": 1, "updated_at": 1})}
        to_update |= {m for m, d in mat_updated_dates.items() if d > thermo_updated_dates.get(m, datetime.min)}

        # TODO: Make this more efficient
        comps = []
        for m in to_update:
            q['material_id'] = m
            comps.append(self.materials().find_one(q, {"elements": 1}).get('elements', {}))

        # TODO: Reduce down to supersets, no need to calcuate A-B if we're going to calc A-B-C

        for chemsys in comps:
            yield self.get_entries(chemsys)

    def get_entries(self, chemsys):
        """
         Get all entries in a chemsys from materials
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
            item ([entry]): a list of entries to process into a phase diagram
        """

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([[dict]]): task_type dicts to insert into task_types collection
                                We know this will be double list [[]] of dicts from the process items

        """

        pass

    def finalize(self):
        pass
