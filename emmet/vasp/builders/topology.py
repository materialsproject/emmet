import logging
import os
import glob

from datetime import datetime
from pymatgen.core.structure import Structure
from pymatgen.analysis.local_env import *
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.command_line.critic2_caller import Critic2Caller
from pymatgen.command_line.bader_caller import BaderAnalysis
from monty.os.path import which
from maggma.builder import Builder

__author__ = "Matthew Horton <mkhorton@lbl.gov>"

class TopologyBuilder(Builder):
    def __init__(self, tasks, materials, topology, bader,
                 query={}, use_chgcars=True, **kwargs):
        """
        Builder to perform topological analysis of materials, either using
        the Bader method or through local environment nearest-neighbor
        strategies.

        This only requires tasks store to be able to look up
        original path and stored volumetric data. If use_chgcars is
        False, it won't be read.

        Topology store contains bonding information using various
        strategies, including those in pymatgen.analysis.local_env
        and using the critic2 tool.

        A topological analysis using Henkelman's bader tool is also
        done when use_chgcars=True, but since bonding information is
        not provided, the output format is different and so bader
        output is stored in a separate Store.

        TODO: support custom critic2 settings

        Args:
            tasks (Store): Store of tasks documents
            materials (Store): Store of materials documents
            topology (Store): Store of topology data
            bader (Store): Store of bader data
            query (dict): dictionary to limit materials to be analyzed
            use_chgcars (bool): if True, will look for charge densities
            in task directories and run bader and critic2 if found
        """

        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(logging.NullHandler())

        self.tasks = tasks
        self.materials = materials
        self.topology = topology
        self.bader = bader
        self.query = query

        self.use_chgcars = use_chgcars

        self.bader_available = which('bader')
        self.critic2_available = which('critic2')

        if not use_chgcars:
            self.__logger.info("Not performing analysis of charge densities.")

        if use_chgcars and not self.bader_available:
            self.__logger.error("bader binary not found! "
                                "TopologyBuilder will not be able to perform a full analysis.")
        if not self.critic2_available:
            self.__logger.error("critic2 binary not found! "
                                "TopologyBuilder will not be able to perform a full analysis.")

        super().__init__(sources=[tasks, materials],
                         targets=[topology, bader],
                         **kwargs)

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.__logger.info("Topology Builder Started")

        # All relevant materials that have been updated since topology
        # was last calculated
        q = dict(self.query)
        q.update(self.materials.lu_filter(self.topology))
        mats = self.materials().find(q, {"material_id": 1,
                                         "structure": 1,
                                         "origins": 1})
        self.__logger.info("Found {} new materials for topological analysis".format(mats.count()))
        return mats

    def process_item(self, item):
        """
        Calculates diffraction patterns for the structures

        Args:
            item (dict): a dict with a material_id and a structure

        Returns:
            StructureGraph: a dict of StructureGraphs serialized as dicts,
        with keys as the method
        """

        topology_docs = []
        bader_doc = None

        mid = item['material_id']
        structure = Structure.from_dict(item['structure'])

        # bonding first

        self.__logger.debug("Calculating bonding for {}".format(mid))

        # try all local_env strategies
        strategies = NearNeighbors.__subclasses__()
        for strategy in strategies:
            try:
                topology_docs.append({
                    'material_id': mid,
                    'method': strategy.__name__,
                    'graph': StructureGraph.with_local_env_strategy(structure,
                                                                    strategy()).as_dict()
                })
            except Exception as e:
                self.__logger.warning(e)
                self.__logger.warning("Failed to calculate bonding for {} using "
                                      "{} local_env strategy.".format(mid,
                                                                      strategy.__name__))

        # and also critic2 with sum of atomic charge densities
        if self.critic2_available:

            try:
                c2 = Critic2Caller(structure)

                topology_docs.append({
                    'material_id': mid,
                    'method': 'critic2_promol',
                    'graph': c2.output.structure_graph().as_dict()
                })

            except Exception as e:
                self.__logger.warning(e)
                self.__logger.warning("Failed to calculate bonding for {} using "
                                      "critic2 and sum of atomic charge densities.".format(mid))

        if self.use_chgcars:

            # retrieve task_id for static calculation
            # this might be improved later
            task_id = None
            for origin in item['origins']:
                if origin['task_type'] == 'static':
                    task_id = origin['task_id']
            task = self.tasks().find_one({'task_id': task_id}, {'calcs_reversed': 1})

            root_dir = task['calcs_reversed'][0]['dir_name']

            # remove hostname if it's present, assumes builder runs on same host
            # or has access to the root_dir
            root_dir = root_dir.split(':')[1] if ':' in root_dir else root_dir

            if not os.path.isdir(root_dir):

                self.__logger.error("Cannot find or cannot access {} (task {}) for {}."
                                    .format(root_dir, task_id, mid))

            else:

                if 'output_file_paths' in task['calcs_reversed'][0]:
                    # we know what output files we have

                    paths = task['calcs_reversed'][0]['output_file_paths']
                    chgcar = paths.get('chgcar', None)
                    aeccar0 = paths.get('aeccar0', None)
                    aeccar2 = paths.get('aeccar2', None)

                else:
                    # we have to search manually

                    self.__logger.info("Searching {} ({}) for charge density files for {}."
                                       .format(root_dir, task_id, mid))

                    chgcar = glob.glob(root_dir+'/*CHGCAR*')
                    chgcar = chgcar[0] if chgcar else None
                    aeccar0 = glob.glob(root_dir+'/*AECCAR0*')
                    aeccar0 = aeccar0[0] if aeccar0 else None
                    aeccar2 = glob.glob(root_dir+'/*AECCAR2*')
                    aeccar2 = aeccar2[0] if aeccar2 else None

                if chgcar and aeccar0 and aeccar2:

                    try:
                        c2 = Critic2Caller(structure)

                        topology_docs.append({
                            'material_id': mid,
                            'method': 'critic2_chgcar',
                            'graph': c2.output.structure_graph().as_dict(),
                            'critic2_stdout': c2._stdout
                        })

                    except Exception as e:
                        self.__logger.warning(e)
                        self.__logger.warning("Failed to calculate bonding on {} for {} "
                                              "using critic2 from CHGCAR.".format(task_id, mid))

                    if self.bader_available:

                        try:
                            ba = BaderAnalysis.from_path(root_dir)
                            bader_doc = ba.summary
                        except Exception as e:
                            self.__logger.warning(e)
                            self.__logger.warning("Failed to perform bader analysis "
                                                  "on task {} for {}".format(task_id, mid))


                else:
                    self.__logger.warning("Not all files necessary for charge analysis "
                                          "are present.")
                    if not chgcar:
                        self.__logger.warning("Could not find CHGCAR for {}.".format(mid))
                    else:
                        self.__logger.warning("CHGCAR found for {}, but AECCAR0 "
                                              "or AECCAR2 not present.".format(mid))


        return {
            'topology_docs': topology_docs,
            'bader_doc': bader_doc
        }

    def update_targets(self, items):

        self.__logger.info("Updating topology documents")

        for item in items:

            for topology_doc in item['topology_docs']:
                topology_doc[self.topology.lu_field] = datetime.utcnow()
                self.topology().replace_one({'material_id': topology_doc['material_id'],
                                             'method': topology_doc['method']},
                                            topology_doc, upsert=True)

            item['bader_doc'][self.bader.lu_field] = datetime.utcnow()
            self.bader().replace_one({"material_id": item['bader_doc']['material_id']},
                                     item['bader_doc'], upsert=True)
