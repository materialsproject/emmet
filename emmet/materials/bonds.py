from itertools import chain

from pymatgen import Structure
from pymatgen.analysis.local_env import NearNeighbors
from pymatgen.analysis.graphs import StructureGraph
from pymatgen import __version__ as pymatgen_version

from maggma.builder import Builder
from maggma.validator import StandardValidator

__author__ = "Matthew Horton <mkhorton@lbl.gov>"


class BondValidator(StandardValidator):
    """
    Validates documents for bonding stores.
    """

    @property
    def schema(self):
        return {
            "type": "object",
            "properties":
                {
                    "task_id": {"type": "string"},
                    "method": {"type": "string"},
                    "successful": {"type": "boolean"},
                    "pymatgen_version": {"type": "string"}
                },
            "required": ["task_id", "method", "successful"]
        }

    @property
    def msonable_keypaths(self):
        return {"graph": StructureGraph}


class BondBuilder(Builder):

    def __init__(self, materials, bonding,
                 strategies=('CrystalNN',),
                 query=None, **kwargs):
        """
        Builder to calculate bonding in a crystallographic
        structure via near neighbor strategies, including those
        in pymatgen.analysis.local_env and using the critic2 tool.

        Args:
            materials (Store): Store of materials documents
            bonding (Store): Store of topology data
            strategies (list): List of NearNeighbor classes to use (can be
            an instance of a NearNeighbor class or its name as a string,
            in which case it will be instantiated with default arguments)
            query (dict): dictionary to limit materials to be analyzed
        """

        self.materials = materials
        self.bonding = bonding
        self.query = query or {}

        # self.bonding.validator = BondValidator()

        available_strategies = {nn.__name__: nn for nn in NearNeighbors.__subclasses__()}

        # use the class if passed directly (e.g. with custom kwargs),
        # otherwise instantiate class with default options
        self.strategies = [strategy if isinstance(strategy, NearNeighbors)
                           else available_strategies[strategy]()
                           for strategy in strategies]
        self.strategy_names = [strategy.__class__.__name__ for strategy in self.strategies]

        self.bad_task_ids = []  # Voronoi-based strategies can cause some structures to cause crash

        super().__init__(sources=[materials],
                         targets=[bonding],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.logger.info("Bonding Builder Started")

        # All relevant materials that have been updated since topology
        # was last calculated
        already_calculated = list(
            self.bonding.query(criteria={'strategy': {'$in': self.strategy_names}},
                               properties=["task_id"]))
        already_calculated = [d["task_id"] for d in already_calculated]
        self.logger.info("Found {} tasks already analyzed".format(len(already_calculated)))

        q = {'task_id': {'$nin': already_calculated}}
        q.update(self.query)
        materials = self.materials.query(criteria=q,
                                         properties=["task_id", "structure"])

        self.total = materials.count()
        self.logger.info("Found {} new materials for bonding analysis".format(self.total))

        for material in materials:
            yield material

    def process_item(self, item):
        """
        Calculates StructureGraphs (bonding information) for a material
        """

        topology_docs = []

        task_id = item['task_id']
        structure = Structure.from_dict(item['structure'])

        # try all local_env strategies
        for strategy, strategy_name in zip(self.strategies, self.strategy_names):

            if task_id not in self.bad_task_ids:

                self.logger.debug("Calculating bonding for {} {}".format(task_id, strategy_name))

                # failure statistics are interesting
                try:
                    topology_docs.append({
                        'task_id': task_id,
                        'strategy': strategy_name,
                        'graph': StructureGraph.with_local_env_strategy(structure,
                                                                        strategy).as_dict(),
                        'pymatgen_version': pymatgen_version,
                        'successful': True
                    })
                except Exception as e:

                    self.logger.warning(
                        'Failed to calculate bonding: {} {} {}'.format(task_id, strategy_name, e))

                    topology_docs.append({
                        'task_id': task_id,
                        'strategy': strategy_name,
                        'successful': False,
                        'pymatgen_version': pymatgen_version,
                        'error_message': str(e)
                    })

        return topology_docs

    def update_targets(self, items):
        self.logger.debug("Updating {} topology documents".format(len(items)))
        items = chain.from_iterable(items)
        self.bonding.update(docs=items, key=['task_id', 'strategy'])