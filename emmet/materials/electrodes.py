import os


from pymatgen.core import Structure

from maggma.builder import Builder

from emmet.common.utils import load_settings
__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"


module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
default_substrate_settings = os.path.join(
    module_dir, "settings", "electrodes.yaml")


class ElectrodeBuilder(Builder):

    def __init__(self, materials, electrodes, query=None, **kwargs):
        """
        Builds a convenient database of electrodes and properties

        Args:
            materials (Store): Store of materials documents
            electrodes (Store): Store of electrodes
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.electrodes = electrodes
        self.query = query if query else {}
        self.working_ions = ["Li","Na","K","Rb","Cs","Mg","Cs"]
        self.redox_els = ["Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Zr", "Nb",
                          "Mo","Sn", "Sb", "W", "Re", "Bi"]

        super().__init__(sources=[materials],
                         targets=[electrodes],
                         **kwargs)

    def get_items(self):
        """
        Gets sets of entries from chemical systems that need to be processed 
        for possible electrodes

        Returns:
            generator of relevant entries from one chemical system
        """
        self.logger.info("Electrode Builder Started")

        # All updated chemical systems that contain at least one redox active elements
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.thermo))
        q.update({"chemsys": {"$in": self.redox_els}})

        comps = self.materials.distinct("chemsys", q)

        self.logger.info(
            "Found {} compositions with new/updated materials".format(len(comps)))

        # Only yields maximal super sets: e.g. if ["A","B"] and ["A"] are both in the list, will only yield ["A","B"]
        # as this will calculate thermo props for all ["A"] compounds
        processed = set()

        # Start with the largest set to ensure we don"t miss superset/subset
        # relations
        for chemsys in sorted(comps, key=lambda x: len(x.split("-")), reverse=True):
            if chemsys not in processed:
                processed |= chemsys_permutations(chemsys)
                yield self.get_entries(chemsys)

    def get_electrode_entries(self, chemsys,working_ions):
        """
        Get all entries in a chemsys from materials

        Args:
            chemsys(str): a chemical system represented by string elements seperated by a dash (-)

        Returns:
            set(ComputedEntry): a set of entries for this system
        """

        self.logger.info("Getting entries for: {}".format(chemsys))

        new_q = dict(self.query)
        new_q["chemsys"] = {"$in": list(chemsys_permutations(chemsys))}
        fields = ["structure",  self.materials.key, "thermo.energy",
                  "unit_cell_formula", "calc_settings.is_hubbard",
                  "calc_settings.hubbards", "calc_settings.potcar_spec",
                  "calc_settings.run_type"]
        data = list(self.materials.query(fields, new_q))

        all_entries = []

        for d in data:
            parameters = {"is_hubbard": d["calc_settings"]["is_hubbard"],
                          "hubbards": d["calc_settings"]["hubbards"],
                          "potcar_spec": d["calc_settings"]["potcar_spec"],
                          "run_type": d["calc_settings"]["run_type"]
                          }

            entry = ComputedEntry(Composition(d["unit_cell_formula"]),
                                  d["thermo"]["energy"], 0.0, parameters=parameters,
                                  entry_id=d[self.materials.key],
                                  data={"oxide_type": oxide_type(Structure.from_dict(d["structure"]))})

            all_entries.append(entry)

        self.logger.info("Total entries in {} : {}".format(
            chemsys, len(all_entries)))

        return all_entries


def chemsys_permutations(chemsys):
    # Fancy way of getting every unique permutation of elements for all
    # possible number of elements:
    elements = chemsys.split("-")
    return {"-".join(sorted(c)) for c in
            chain(*[combinations(elements, i) for i in range(1, len(elements) + 1)])}

