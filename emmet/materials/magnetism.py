import os.path
from monty.serialization import loadfn

from pymatgen import Structure
from pymatgen.analysis.magnetism import CollinearMagneticStructureAnalyzer
from pymatgen import __version__ as pymatgen_version
from maggma.validator import JSONSchemaValidator
from maggma.builders import MapBuilder

import numpy as np

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>, Matthew Horton <mkhorton@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
MAGNETISM_SCHEMA = os.path.join(MODULE_DIR, "schema", "magnetism.json")


class MagneticBuilder(MapBuilder):
    def __init__(self, materials, magnetism, **kwargs):
        """
        Creates a magnetism collection for materials

        Args:
            materials (Store): Store of materials documents to match to
            magnetism (Store): Store of magnetism properties

        """

        self.materials = materials
        self.magnetism = magnetism

        self.magnetism.validator = JSONSchemaValidator(loadfn(MAGNETISM_SCHEMA))

        super().__init__(
            source=materials, target=magnetism, projection=["structure", "magnetism"], ufn=self.calc, **kwargs)

    def calc(self, item):
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
        magmoms = list(sign * np.array(msa.magmoms))

        magnetism = {
            "magnetism": {
                'ordering':
                msa.ordering.value,
                'is_magnetic':
                msa.is_magnetic,
                'exchange_symmetry':
                msa.get_exchange_group_info()[1],
                'num_magnetic_sites':
                msa.number_of_magnetic_sites,
                'num_unique_magnetic_sites':
                msa.number_of_unique_magnetic_sites(),
                'types_of_magnetic_species': 
                [str(t) for t in msa.types_of_magnetic_specie],
                'magmoms':
                magmoms,
                'total_magnetization':
                total_magnetization,
                'total_magnetization_normalized_vol':
                total_magnetization / struct.volume,
                'total_magnetization_normalized_formula_units':
                total_magnetization / (struct.composition.get_reduced_composition_and_factor()[1])
            },
            "pymatgen_version": pymatgen_version
        }
        return magnetism
