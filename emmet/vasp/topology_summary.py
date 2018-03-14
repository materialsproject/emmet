import numpy as np

from pymatgen.analysis.graphs import StructureGraph
from maggma.builder import Builder
from maggma.validator import StandardValidator

__author__ = "Matthew Horton <mkhorton@lbl.gov>"

class TopologySummaryValidator(StandardValidator):

    @property
    def schema(self):
        return {
            "type": "object",
            "properties":
                {
                    "task_id": {"type": "string"},
                    "methods": {"type": "array", "items": {"type": "string"}},
                    "distances": {"type": "array", "items": {"type": "array",
                                                             "items": {"type": "number"}}},
                    "preferred_graph": {"type": "object"},
                    "preferred_graph_method": {"type": "string"}
                },
            "required": ["task_id", "methods", "distances",
                         "preferred_graph", "preferred_graph_method"]
        }

    @property
    def msonable_keypaths(self):
        return {"graph": StructureGraph}


class TopologySummaryBuilder(Builder):
    def __init__(self, topology, topology_summary,
                 preferred_methods=('critic2_chgcar', 'MinimumOKeeffeNN'),
                 query=None, **kwargs):
        """
        Summarizes topology information (this is the 'materials' to
        topology's 'tasks').

        Args:
            topology (Store): Store of topology documents
            topology_summary (Store): Store of topology summary documents
            preferred_methods (Tuple): List of which topology methods to favor
            query (dict): dictionary to limit materials to be analyzed
        """

        self.topology = topology
        self.topology_summary = topology_summary
        self.preferred_methods = preferred_methods
        self.query = query if query else {}

        self.topology_summary.validator = TopologySummaryValidator()

        super().__init__(sources=[topology],
                         targets=[topology_summary],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.logger.info("Topology Summary Builder Started")

        # Retrieve new task ids that were not included in previous summary
        new_task_ids_query = dict(self.query)
        new_task_ids_query.update(self.topology.lu_filter(self.topology_summary))

        new_task_ids = set([doc['task_id'] for doc in
                            self.topology.query(criteria=new_task_ids_query,
                                                properties=["task_id"])])

        self.logger.info("Found {} new topology docs to summarize.".format(len(new_task_ids)))

        # ensure we only aggregate a consistent set of user settings,
        # currently this is just default settings
        standard_critic2_user_settings = None

        for task_id in new_task_ids:

            topology_docs = list(self.topology.query(
                criteria={'task_id': task_id,
                          'successful': True,
                          '$or': [{'critic2_settings': {'$exists': False}},
                                  {'critic2_settings': standard_critic2_user_settings}]},
                properties=['task_id', 'method', 'graph', 'critic2_settings']))

            print(topology_docs)

            yield {
                'task_id': task_id,
                'topology_docs': topology_docs
            }

    def process_item(self, item):
        """
        Summarizes a set of StructureGraphs (calculates differences
        between them, picks one to be preferred output)
        """

        task_id = item['task_id']
        topology_docs = item['topology_docs']

        topology_summary = {'task_id': task_id}

        available_methods = [doc['method'] for doc in topology_docs]

        standard_methods = ('MinimumDistanceNN', 'MinimumOKeeffeNN', 'JMolNN',
                            'MinimumVIRENN', 'VoronoiNN', 'critic2_promol', 'critic2')

        sg = [StructureGraph.from_dict(doc['graph']) for doc in topology_docs]

        # standardized matrix to store graph distances
        distances = np.empty((len(standard_methods), len(standard_methods)))
        distances[:] = np.NaN

        # calculate distances between graphs
        # gives a measure of how 'different' one method
        # of determining bonding is from another method
        for i, method_a in enumerate(standard_methods):
            if method_a in available_methods:
                for j, method_b in enumerate(standard_methods[:i]):
                    if method_b in available_methods:

                        a_idx = available_methods.index(method_a)
                        b_idx = available_methods.index(method_b)

                        dist = sg[a_idx].diff(sg[b_idx])['dist']

                        distances[i][j] = dist
                        distances[j][i] = dist

        topology_summary['methods'] = standard_methods
        topology_summary['distances'] = distances

        # we want to store one canonical set of bonds for a material
        # we see if our preferred method is here
        preferred_method = None
        for method in reversed(self.preferred_methods):
            if method in available_methods:
                preferred_method = method

        if preferred_method:
            preferred_graph = sg[standard_methods.index(preferred_method)]
            topology_summary['preferred_graph'] = preferred_graph.as_dict()
            topology_summary['preferred_graph_method'] = preferred_method
            if 'ce_info' in preferred_graph.structure.site_properties:
                # for easier querying in mongo
                topology_summary['ce_info'] = preferred_graph.structure.site_properties['ce_info']

        self.logger.debug("Summarized bonding for {}".format(task_id))

        return topology_summary

    def update_targets(self, items):

        self.logger.info("Updating topology summary documents")
        self.topology_summary.update(items, key='task_id')