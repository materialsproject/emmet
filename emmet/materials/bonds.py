from pymatgen import Structure
from pymatgen.analysis.local_env import NearNeighbors
from pymatgen.analysis.graphs import StructureGraph
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
                    "successful": {"type": "boolean"}
                },
            "required": ["task_id", "method", "successful"]
        }

    @property
    def msonable_keypaths(self):
        return {"graph": StructureGraph}


class BondBuilder(Builder):
    def __init__(self, materials, bonding,
                 strategies=('MinimumDistanceNN', 'MinimumOKeeffeNN', 'JMolNN',
                             'MinimumVIRENN', 'VoronoiNN', 'CrystalNN', 'EconNN',
                             'BrunnerNN_real', 'BrunnerNN_relative',
                             'BrunnerNN_reciprocal', 'Critic2NN'),
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

        self.chunk_size = 100

        self.materials = materials
        self.bonding = bonding
        self.query = query or {}

        available_strategies = {nn.__name__: nn for nn in NearNeighbors.__subclasses__()}

        if strategies:
            # use the class if passed directly (e.g. with custom kwargs),
            # otherwise instantiate class with default options
            self.strategies = [strategy if isinstance(strategy, NearNeighbors)
                                else available_strategies[strategy]()
                                for strategy in strategies]
        else:
            # calculate all the strategies
            self.strategies = available_strategies.values()

        bonding.validator = BondValidator()

        super().__init__(sources=[materials],
                         targets=[bonding],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.logger.info("Topology Builder Started")

        # All relevant materials that have been updated since topology
        # was last calculated
        already_calculated = list(self.bonding.query(criteria={}, properties=["task_id"]))
        already_calculated = [d["task_id"] for d in already_calculated]
        q = {'task_id': {'$nin': already_calculated}}
        q.update(self.query)
        materials = self.materials.query(criteria=q,
                                         properties=["task_id", "structure"])

        self.total = materials.count()
        self.logger.info("Found {} new materials for topological analysis".format(self.total))
        return materials

    def process_item(self, item):
        """
        Calculates StructureGraphs (bonding information) for a material
        """

        topology_docs = []

        task_id = item['task_id']
        structure = Structure.from_dict(item['structure'])

        self.logger.debug("Calculating bonding for {}".format(task_id))

        # try all local_env strategies
        for strategy in self.strategies:
            method = strategy.__class__.__name__

            # failure statistics are interesting
            try:
                topology_docs.append({
                    'task_id': task_id,
                    'method': method,
                    'graph': StructureGraph.with_local_env_strategy(structure,
                                                                    strategy).as_dict(),
                    'successful': True
                })
            except Exception as e:

                topology_docs.append({
                    'task_id': task_id,
                    'method': method,
                    'successful': False,
                    'error_message': str(e)
                })

                self.logger.warning(e)
                self.logger.warning("Failed to calculate bonding for {} using "
                                    "{} strategy.".format(task_id, method))

        return topology_docs

    def update_targets(self, items):

        self.logger.info("Updating {} topology documents".format(len(items)))
        for item in items:
            self.bonding.update(item, key=['task_id', 'method'])
