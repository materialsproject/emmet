from pymatgen.core.structure import Structure
from maggma.builders import MapBuilder

from robocrys import StructureCondenser, StructureDescriber

__author__ = "Alex Ganose"


class RobocrysBuilder(MapBuilder):

    def __init__(self, materials, robocrys, **kwargs):
        """Runs robocrystallographer to get the condensed structure and
        structure description.

        Args:
            materials (Store): Store of materials documents.
            robocrys (Store): Store of condensed structure and
                text structure description.
            **kwargs: Keyword arguments that will get passed to the builder
                super method.
        """
        self.materials = materials
        self.robocrys = robocrys

        self.condenser = StructureCondenser()
        self.describer = StructureDescriber(describe_symmetry_labels=False)

        super().__init__(source=materials, target=robocrys, ufn=self.calc,
                         projection=["structure"], **kwargs)

    def calc(self, item):
        """Calculates robocrystallographer on an item.

        Args:
            item (dict): A dict with a task_id and a structure.

        Returns:
            dict: The robocrystallographer information dict with they keys:

            - ``"condensed_structure"``: The condensed structure dictionary.
            - ``"description"``: The text description.
        """
        self.logger.debug("Running robocrys on {}".format(
            item[self.materials.key]))

        structure = Structure.from_dict(item["structure"])
        doc = {}

        try:
            self.logger.debug("Adding oxidation states for {}".format(
                item[self.materials.key]))
            structure.add_oxidation_state_by_guess(max_sites=-80)
        except ValueError:
            self.logger.warning("Could not add oxidation states for {}".format(
                item[self.materials.key]))

        condensed_structure = self.condenser.condense_structure(structure)
        description = self.describer.describe(condensed_structure)
        doc.update({"condensed_structure": condensed_structure,
                        "description": description})
        
        return doc
