import logging
import numpy as np

from datetime import datetime
from pymatgen.core.structure import Structure
from pymatgen.analysis.graphs import StructureGraph
from maggma.builder import Builder

__author__ = "Matthew Horton <mkhorton@lbl.gov>"

class TopologyBuilder(Builder):
    def __init__(self, topology, topology_summary,
                 preferred_methods=('critic2_chgcar', 'MinimumOKeeffeNN'),
                 query={}, **kwargs):
        """
        Summarizes topology information (this is the 'materials' to
        topology's 'tasks').

        Args:
            topology (Store): Store of topology documents
            topology_summary (Store): Store of topology summary documents
            preferred_methods (Tuple): List of which topology methods to favor
            query (dict): dictionary to limit materials to be analyzed
        """

        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(logging.NullHandler())

        self.topology = topology
        self.topology_summary = topology
        self.methods = preferred_methods
        self.query = query

        super().__init__(sources=[topology],
                         targets=[topology_summary],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.__logger.info("Topology Summary Builder Started")

        # All relevant materials that have been updated since topology
        # was last calculated
        q = dict(self.query)
        q.update(self.topology.lu_filter(self.topology_summary))
        mats = self.topology().find(q).distinct("material_id")
        self.__logger.info("Found {} new materials for topological analysis".format(mats.count()))
        return mats

    def process_item(self, item):
        """
        Summarizes a set of StructureGraphs (calculates differences
        between them, picks one to be preferred output)
        """

        topology_summary = {}

        mid = item[0]['material_id']

        names = [doc['method'] for doc in item]
        sg = [StructureGraph.from_dict(doc['graph']) for doc in item]

        distances = np.empty((len(names), len(names)))
        distances[:] = np.NaN

        # calculate distances between graphs
        # gives a measure of how 'different' one method
        # of determining bonding is from another method
        for i in range(len(names)):
            for j in range(len(i)):
                dist = sg[i].diff(sg[j])
                distances[i][j] = dist
                distances[j][i] = dist

        topology_summary['distances'] = distances

        # we want to store one canonical set of bonds for a material
        # we see if our preferred method is here
        preferred_method = None
        for method in reversed(self.methods):
            if method in names:
                preferred_method = method

        if preferred_method:
            topology_summary['graph'] = sg[names.index(preferred_method)]
            topology_summary['method'] = method

        self.__logger.debug("Summarizing bonding for {}".format(mid))

        return topology_summary

    def update_targets(self, items):

        self.__logger.info("Updating topology summary documents")

        for item in items:

            item[self.topology_summary.lu_field] = datetime.utcnow()
            self.topology_summary().replace_one({"material_id": item['material_id']},
                                                item, upsert=True)
