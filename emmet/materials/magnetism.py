from pymatgen import Structure
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen import __version__ as pymatgen_version

from maggma.builder import Builder
from maggma.validator import JSONSchemaValidator

import numpy as np

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>, Matthew Horton <mkhorton@lbl.gov>"


MAGNETISM_SCHEMA = {
    "title": "magnetism",
    "type": "object",
    "properties":
        {
            "task_id": {"type": "string"},
            "magnetism": {"type": "object"},
            "pymatgen_version": {"type": "string"}
        },
    "required": ["task_id", "magnetism", "pymatgen_version"]
}


class MagneticBuilder(Builder):
    def __init__(self, materials, magnetism, query=None, **kwargs):
        """
        Creates a magnetism collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            magnetism (Store): Store of magnetism properties
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.magnetism = magnetism
        self.query = query or {}

        self.magnetism.validator = JSONSchemaValidator(MAGNETISM_SCHEMA)

        super().__init__(sources=[materials],
                         targets=[magnetism],
                         **kwargs)

    def get_items(self):
        """
        Gets all items to process into magnetismdocuments

        Returns:
            generator or list relevant tasks and materials to process into magnetism documents
        """
        self.logger.info("Magnestism Builder Started")

        # All relevant materials that have been updated since magnetism props
        # were last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.magnetism))
        mats = list(self.materials.distinct(self.materials.key, q))
        self.logger.info(
            "Found {} new materials for magnetism data".format(len(mats)))
        self.total = len(mats)

        for m in mats:
            yield self.materials.query_one(properties=[self.materials.key, "structure", "magnetism"],
                                           criteria={self.materials.key: m})

    def process_item(self, item):
        """
        Process the tasks and materials into a magnetism collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: a magnetism dictionary
        """

        struct = Structure.from_dict(item["structure"])
        total_magnetization = item["magnetism"].get("total_magnetization", 0)  # not necessarily == sum(magmoms)
        msa = CollinearMagneticStructureAnalyzer(struct)

        sign = np.sign(total_magnetization)
        total_magnetization = abs(total_magnetization)
        magmoms = list(sign*np.array(msa.magmoms))

        magnetism = {
            self.magnetism.key : item[self.materials.key],
            "magnetism": {
                'ordering': msa.ordering.value,
                'is_magnetic': msa.is_magnetic,
                'exchange_symmetry': msa.get_exchange_group_info()[1],
                'num_magnetic_sites': msa.number_of_magnetic_sites,
                'num_unique_magnetic_sites': msa.number_of_unique_magnetic_sites(),
                'types_of_magnetic_species': [str(t) for t in msa.types_of_magnetic_specie],
                'magmoms': magmoms,
                'total_magnetization_normalized_vol': total_magnetization/struct.volume,
                'total_magnetization_normalized_formula_units': total_magnetization/
                (struct.composition.get_reduced_composition_and_factor()[1])
                },
            "pymatgen_version": pymatgen_version
        }
        return magnetism

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """

        items = list(filter(None, items))

        if len(items) > 0:
            self.logger.info("Updating {} magnetism docs".format(len(items)))
            self.magnetism.update(docs=items)
        else:
            self.logger.info("No items to update")


