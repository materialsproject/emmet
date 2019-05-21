from maggma.builders import MapBuilder

from monty.json import MontyDecoder
from crystal_toolkit.components.structure import StructureMoleculeComponent


class VisualizationBuilder(MapBuilder):
    def __init__(
        self,
        materials,
        visualization,
        projection=("structure",),
        bonding_strategy="CrystalNN",
        bonding_strategy_kwargs=None,
        color_scheme="Jmol",
        color_scale=None,
        radius_strategy="uniform",
        draw_image_atoms=True,
        bonded_sites_outside_unit_cell=True,
        hide_incomplete_bonds=True,
        **kwargs
    ):
        """
        Builds JSON to visualize crystal structures or molecules.
        :param materials: Any store whose docs contain structures
        :param visualization: Destination store
        :param projection: The key for the origin structure or molecule (if
        a StructureGraph or MoleculeGraph is provided directly, the graph
        connections will be used as bonds, and bonding_strategy kwargs ignored)
        :param bonding_strategy: The name of a NearNeighbor class, see
        StructureMoleculeComponent.available_bonding_strategies.keys() for
        a full list
        :param bonding_strategy_kwargs: kwargs to pass to the NearNeighbor
        class above
        :param color_scheme: can be "Jmol", "VESTA" or the name of a scalar
        site property (in future, a color-blind friendly scheme and categorical
        site properties will be supported)
        :param color_scale: name of a standard matplotlib cmap object if using
        a scalar site property to color code, will default as blue-white-red
        with white at zero
        :param radius_strategy: defaults to "uniform" for constant radii atoms,
        see StructureMoleculeComponent.available_radius_strategies for more
        :param draw_image_atoms: whether to draw repeats of atoms that are on
        periodic boundaries
        :param bonded_sites_outside_unit_cell: whether to draw sites that are
        outside the unit cell but bonded to sites within it
        :param hide_incomplete_bonds: whether or not to draw bonds where the
        destination atoms are not visible (can be useful to see a bond is
        present even if the destination atom is not drawn)
        :param kwargs: to pass to MapBuilder
        """

        self.materials = materials
        self.visualization = visualization
        self.projection = projection
        self.bonding_strategy = bonding_strategy
        self.bonding_strategy_kwargs = bonding_strategy_kwargs
        self.color_scheme = color_scheme
        self.color_scale = color_scale
        self.radius_strategy = radius_strategy
        self.draw_image_atoms = draw_image_atoms
        self.bonded_sites_outside_unit_cell = bonded_sites_outside_unit_cell
        self.hide_incomplete_bonds = hide_incomplete_bonds
        self.kwargs = kwargs

        self.projected_object_name = projection[0]

        # stored as a dict so settings can be stored in the visualization
        # document in case we want to store multiple visualizations
        # of the same structure,
        self.settings = {
            "bonding_strategy": bonding_strategy,
            "bonding_strategy_kwargs": bonding_strategy_kwargs,
            "color_scheme": color_scheme,
            "color_scale": color_scale,
            "radius_strategy": radius_strategy,
            "draw_image_atoms": draw_image_atoms,
            "bonded_sites_outside_unit_cell": bonded_sites_outside_unit_cell,
            "hide_incomplete_bonds": hide_incomplete_bonds,
        }

        super().__init__(
            source=materials,
            target=visualization,
            ufn=self.calc,
            projection=list(projection),
            **kwargs
        )

    def calc(self, item):

        struct_or_mol = MontyDecoder().process_decoded(item[self.projected_object_name])

        # TODO: will combine these two functions into something more intuitive

        graph = StructureMoleculeComponent._preprocess_input_to_graph(
            struct_or_mol,
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

        return {
            "scene": scene.to_json(),
            "legend": legend,
            "settings": self.settings,
            "source": item[self.projected_object_name],
        }
