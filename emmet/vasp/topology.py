import os
import glob

from pymatgen.analysis.local_env import *
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.command_line.critic2_caller import Critic2Caller
from pymatgen.command_line.bader_caller import bader_analysis_from_path
from monty.os.path import which
from maggma.builder import Builder
from maggma.validator import StandardValidator

from monty.json import jsanitize

from emmet.vasp.task_tagger import task_type

__author__ = "Matthew Horton <mkhorton@lbl.gov>"


class TopologyValidator(StandardValidator):

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


class TopologyBuilder(Builder):
    def __init__(self, tasks, topology, bader,
                 query=None, use_chgcars=True,
                 critic2_settings=None,
                 **kwargs):
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

        Args:
            tasks (Store): Store of tasks documents
            topology (Store): Store of topology data
            bader (Store): Store of bader data
            query (dict): dictionary to limit materials to be analyzed
            use_chgcars (bool): if True, will look for charge densities
            critic2_settings (dict): user_input_settings for critic2
            in task directories and run bader and critic2 if found
        """

        self.tasks = tasks
        self.topology = topology
        self.bader = bader
        self.query = query if query else {}

        topology.validator = TopologyValidator()

        self.use_chgcars = use_chgcars
        self.critic2_settings = critic2_settings

        self.bader_available = which('bader')
        self.critic2_available = which('critic2')

        super().__init__(sources=[tasks],
                         targets=[topology, bader],
                         **kwargs)

        if not use_chgcars:
            self.logger.info("Not performing analysis of charge densities.")

        if use_chgcars and not self.bader_available:
            self.logger.error("bader binary not found! "
                                "TopologyBuilder will not be able to perform a full analysis.")
            self.logger.error("If running for Materials Project, try adding "
                                "/project/projectdirs/matgen/emmet_bin/cori to your path.")

        if not self.critic2_available:
            self.logger.error("critic2 binary not found! "
                                "TopologyBuilder will not be able to perform a full analysis.")
            self.logger.error("If running for Materials Project, try adding "
                                "/project/projectdirs/matgen/emmet_bin/cori to your path.")

    def get_items(self):
        """
        Gets all materials that need topology analysis
        """

        self.logger.info("Topology Builder Started")

        # All relevant materials that have been updated since topology
        # was last calculated
        q = dict(self.query)
        q.update(self.tasks.lu_filter(self.topology))
        tasks = self.tasks.query(criteria=q,
                                 properties=["task_id", "input.incar",
                                             "output.structure", "calcs_reversed"])

        self.logger.info("Found {} new tasks for topological analysis".format(tasks.count()))

        for task in tasks:
            if "Static" in task_type(task['input']['incar']):
                yield task

    @staticmethod
    def rewrite_dir(original_dir):
        """
        Stub. If locations of original folders has been moved,
        this function will help locate them. In practice, this
        will likely mean extracting the name of the launch dir,
        and finding this on a new host.

        Args:
            original_dir: original directory in task doc

        Returns: rewritten directory
        """

        # remove hostname if it's present, assumes builder runs on same host
        # or has access to the root_dir
        new_dir = original_dir.split(':')[1] if ':' in original_dir else original_dir

        return new_dir

    def process_item(self, item):
        """
        Calculates StructureGraphs (bonding information) for a material
        """

        topology_docs = []
        bader_doc = None

        task_id = item['task_id']
        structure = Structure.from_dict(item['output']['structure'])

        # bonding first

        self.logger.debug("Calculating bonding for {}".format(task_id))

        # try all local_env strategies
        strategies = NearNeighbors.__subclasses__()
        for strategy in strategies:
            try:
                topology_docs.append({
                    'task_id': task_id,
                    'method': strategy.__name__,
                    'graph': StructureGraph.with_local_env_strategy(structure,
                                                                    strategy()).as_dict(),
                    'successful': True
                })
            except Exception as e:

                topology_docs.append({
                    'task_id': task_id,
                    'method': strategy.__name__,
                    'successful': False,
                    'error_message': str(e)
                })

                self.logger.warning(e)
                self.logger.warning("Failed to calculate bonding for {} using "
                                      "{} local_env strategy.".format(task_id,
                                                                      strategy.__name__))

        # and also critic2 with sum of atomic charge densities
        if self.critic2_available:

            try:
                c2 = Critic2Caller(structure,
                                   user_input_settings=self.critic2_settings)

                topology_docs.append({
                    'task_id': task_id,
                    'method': 'critic2_promol',
                    'graph': c2.output.structure_graph().as_dict(),
                    'succesful': True
                })

            except Exception as e:

                topology_docs.append({
                    'task_id': task_id,
                    'method': 'critic2_promol',
                    'critic2_settings': self.critic2_settings,
                    'successful': False,
                    'error_message': str(e)
                })

                self.logger.warning(e)
                self.logger.warning("Failed to calculate bonding for {} using "
                                      "critic2 and sum of atomic charge densities.".format(task_id))

        if self.use_chgcars:

            root_dir = item['calcs_reversed'][0]['dir_name']
            root_dir = self.rewrite_dir(root_dir)

            if not os.path.isdir(root_dir):

                self.logger.error("Cannot find or cannot access {} for {}."
                                    .format(root_dir, task_id))

            else:

                if 'output_file_paths' in item['calcs_reversed'][0]:
                    # we know what output files we have

                    paths = item['calcs_reversed'][0]['output_file_paths']
                    chgcar = paths.get('chgcar', None)
                    aeccar0 = paths.get('aeccar0', None)
                    aeccar2 = paths.get('aeccar2', None)

                else:
                    # we have to search manually

                    self.logger.info("Searching {} for charge density files for {}."
                                       .format(root_dir, task_id))

                    chgcar = glob.glob(root_dir+'/*CHGCAR*')
                    chgcar = chgcar[0] if chgcar else None
                    aeccar0 = glob.glob(root_dir+'/*AECCAR0*')
                    aeccar0 = aeccar0[0] if aeccar0 else None
                    aeccar2 = glob.glob(root_dir+'/*AECCAR2*')
                    aeccar2 = aeccar2[0] if aeccar2 else None

                if chgcar and aeccar0 and aeccar2:

                    try:
                        c2 = Critic2Caller(structure,
                                           user_input_settings=self.critic2_settings)

                        topology_docs.append({
                            'task_id': task_id,
                            'method': 'critic2_chgcar',
                            'graph': c2.output.structure_graph().as_dict(),
                            'critic2_settings': self.critic2_settings,
                            'critic2_stdout': c2._stdout,
                            'successful': True
                        })

                    except Exception as e:

                        topology_docs.append({
                            'task_id': task_id,
                            'method': 'critic2_chgcar',
                            'critic2_settings': self.critic2_settings,
                            'successful': False,
                            'error_message': str(e)
                        })

                        self.logger.warning(e)
                        self.logger.warning("Failed to calculate bonding for {} "
                                              "using critic2 from CHGCAR.".format(task_id))

                    if self.bader_available:

                        try:
                            bader_doc = bader_analysis_from_path(root_dir)
                            bader_doc['task_id'] = task_id
                            bader_doc['successful'] = True
                        except Exception as e:

                            bader_doc = {
                                'task_id': task_id,
                                'successful': False,
                                'error_message': str(e)
                            }

                            self.logger.warning(e)
                            self.logger.warning("Failed to perform bader analysis "
                                                  "for {}".format(task_id))


                else:
                    self.logger.warning("Not all files necessary for charge analysis "
                                          "are present.")
                    if not chgcar:
                        self.logger.warning("Could not find CHGCAR for {}.".format(task_id))
                    else:
                        self.logger.warning("CHGCAR found for {}, but AECCAR0 "
                                              "or AECCAR2 not present.".format(task_id))

        return {
            'topology_docs': topology_docs,
            'bader_doc': bader_doc
        }

    def update_targets(self, items):

        self.logger.info("Updating topology documents")
        items = jsanitize(items)

        for item in items:

            self.topology.update(item['topology_docs'], key=['task_id', 'method'])
            if item['bader_doc']:
                self.bader.update(item['bader_doc'], key=['task_id', 'method'])