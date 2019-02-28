from maggma.builders import MapBuilder

from pymatgen.core.structure import Structure
from crystal_toolkit.components.structure import StructureMoleculeComponent


class VisualizationBuilder(MapBuilder):
    def __init__(self, materials, visualization, projection=("structure",), **kwargs):
        """
        Builds JSON to visualize crystal structures
        :param materials: Any store whose docs contain structures
        :param visualization: Destination store
        :param projection: The key for the origin structure
        :param kwargs: to pass to MapBuilder
        """

        self.materials = materials
        self.visualization = visualization

        self.settings = {
            "bonding_strategy": "CrystalNN",
            "bonding_strategy_kwargs": None,
            "color_scheme": "Jmol",
            "color_scale": None,
            "radius_strategy": "uniform",
            "draw_image_atoms": True,
            "bonded_sites_outside_unit_cell": True,
            "hide_incomplete_bonds": False,
        }

        super().__init__(
            source=materials,
            target=visualization,
            ufn=self.calc,
            projection=projection,
            **kwargs
        )

    def calc(self, item):

        struct = Structure.from_dict(item["structure"])

        graph = StructureMoleculeComponent._preprocess_input_to_graph(
            struct,
            bonding_strategy=self.settings["bonding_strategy"],
            bonding_strategy_kwargs=self.settings["bonding_strategy_kwargs"],
        )

        scene, legend = StructureMoleculeComponent.get_scene_and_legend(
            graph,
            color_scheme=self.settings["color_scheme"],
            color_scale=self.settings["color_scale"],
            radius_strategy=self.settings["radius_strategy"],
            draw_image_atoms=self.settings["draw_image_atoms"],
            bonded_sites_outside_unit_cell=self.settings[
                "bonded_sites_outside_unit_cell"
            ],
            hide_incomplete_bonds=self.settings["hide_incomplete_bonds"],
        )

        return {"scene": scene, "legend": legend, "settings": self.settings}
