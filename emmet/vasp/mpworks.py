import numpy as np
from datetime import datetime
import os

from pymatgen import Composition
from pymatgen.entries.compatibility import MaterialsProjectCompatibility
from pymatgen.entries.computed_entries import ComputedEntry

from maggma.builder import Builder

from pydash.objects import get, set_

from monty.serialization import loadfn

import traceback, logging

__author__ = "Joseph Montoya <montoyjh@lbl.gov>"

logger = logging.getLogger(__name__)

module_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
settings = loadfn(os.path.join(
    module_dir, "settings", "mpworks_conversion.yaml"))

class MPWorksCompatibilityBuilder(Builder):
    def __init__(self, mpworks_tasks, atomate_tasks, query=None,
                 incremental=True, redo_task_ids=True, **kwargs):
        """
        Converts a task collection from the MPWorks schema to
        Atomate tasks.

        Args:
            mpworks_tasks (Store): Store of task documents
            atomate_tasks (Store): Store of elastic properties
            query (dict): dictionary to limit materials to be analyzed
            incremental (bool): whether to operate in incremental mode,
                i.e. to filter by only tasks that have been updated
                after the last last_updated field in the target store
            redo_task_ids (str/bool): whether to redo_task_ids, if
                a string is supplied, this will be used as the new prefix.
            **kwargs (kwargs): further kwargs for maggma builders
        """

        self.mpworks_tasks = mpworks_tasks
        self.atomate_tasks = atomate_tasks
        self.query = query if query is not None else {}
        self.incremental = incremental
        self.builder_start_time = datetime.utcnow()
        self.redo_task_ids = redo_task_ids

        super().__init__(sources=[mpworks_tasks],
                         targets=[atomate_tasks],
                         **kwargs)

    def connect(self):
        self.mpworks_tasks.connect()
        self.atomate_tasks.connect()

    def get_items(self):
        """
        Gets all items to process into materials documents

        Returns:
            generator or list relevant tasks and materials
            to process into materials documents
        """

        logger.info("MPWorks Elastic Compatibility Builder Started")

        # Get only successful tasks
        q = dict(self.query)
        q["state"] = "successful"

        # only consider tasks that have been updated since tasks was last updated
        if self.incremental:
            logger.info("Ensuring indices on lu_field")
            self.mpworks_tasks.ensure_index(self.mpworks_tasks.lu_field)
            self.atomate_tasks.ensure_index(self.atomate_tasks.lu_field)
            q.update(self.mpworks_tasks.lu_filter(self.atomate_tasks))

        # No cursor timeout should probably be fixed with smaller batch sizes
        tasks_to_convert = self.mpworks_tasks.query(criteria=q, no_cursor_timeout=True)
        count = tasks_to_convert.count()
        logger.info("Found {} new/updated tasks to process".format(count))

        # Redo all task ids at the beginning
        if self.redo_task_ids:
            # Get counter for atomate tasks db
            counter = self.atomate_tasks.collection.database.counter
            counter_doc = counter.find_one({'_id': 'taskid'})
            if not counter_doc:
                counter.insert({"_id": "taskid", "c": 1})
                starting_taskid = 1
            else:
                starting_taskid = counter_doc['c']
            counter.find_one_and_update({"_id": "taskid"}, {"$inc": {"c": count}})
        else:
            starting_task_id = 1

        for n, task in enumerate(tasks_to_convert):
            if self.redo_task_ids:
                new_task_id = n + starting_taskid
            else:
                new_task_id = None
            logger.debug("Processing item: {}->{}, {} of {}".format(
                task['task_id'], new_task_id, n, count))
            yield task, new_task_id

    def process_item(self, item):
        """
        Process the MPWorks tasks and materials
        into an Atomate tasks collection

        Args:
            item (dict): an mpworks document

        Returns:
            an Atomate task document
        """
        mpw_doc, new_task_id = item
        atomate_doc = convert_mpworks_to_atomate(mpw_doc)
        atomate_doc['last_updated'] = self.builder_start_time
        if self.redo_task_ids:
            atomate_doc['_mpworks_meta']['task_id'] = atomate_doc.pop("task_id")
            atomate_doc['task_id'] = new_task_id
        return atomate_doc

    def update_targets(self, items):
        """
        Inserts the new tasks into atomate_tasks collection

        Args:
            items ([([dict],[int])]): A list of tuples of materials to
                update and the corresponding processed task_ids
        """
        logger.info("Updating {} atomate documents".format(len(items)))

        self.atomate_tasks.update(items, key='task_id')

    def finalize(self, cursor):
        self.atomate_tasks.close()
        self.mpworks_tasks.close()


def convert_mpworks_to_atomate(mpworks_doc, update_mpworks=True):
    """
    Function to convert an mpworks document into an atomate
    document, uses schema above and a few custom cases

    Args:
        mpworks_doc (dict): mpworks task document
        update_mpworks (bool): flag to indicate that mpworks schema
            should be updated to final MPWorks version
    """
    if update_mpworks:
        update_mpworks_schema(mpworks_doc)

    atomate_doc = {}
    for key_mpworks, key_atomate in settings['task_conversion_keys'].items():
        val = get(mpworks_doc, key_mpworks)
        set_(atomate_doc, key_atomate, val)

    # Task type
    atomate_doc["task_label"] = settings['task_label_conversions'].get(
        mpworks_doc["task_type"])

    # calculations
    atomate_doc["calcs_reversed"] = mpworks_doc["calculations"][::-1]

    # anonymous formula
    comp = Composition(atomate_doc['composition_reduced'])
    atomate_doc["formula_anonymous"] = comp.anonymized_formula

    # deformation matrix and original_task_id
    if "deformation_matrix" in mpworks_doc:
        # Transpose this b/c of old bug, should verify in doc processing
        defo = mpworks_doc["deformation_matrix"]
        if isinstance(defo, str):
            defo = convert_string_deformation_to_list(defo)
        defo = np.transpose(defo).tolist()
        set_(atomate_doc, "transmuter.transformations",
                      ["DeformStructureTransformation"])
        set_(atomate_doc, "transmuter.transformation_params",
                      [{"deformation": defo}])

    return atomate_doc


def convert_string_deformation_to_list(string_defo):
    """
    Some of the older documents in the mpworks schema have a string version
    of the deformation matrix, this function fixes those

    Args:
        string_defo (str): string corresponding to the deformation
    """
    string_defo = string_defo.replace("[", "").replace("]", "").split()
    defo = np.array(string_defo, dtype=float).reshape(3, 3)
    return defo.tolist()


def update_mpworks_schema(mpworks_doc):
    """
    Corrects an mpworks document for outdated schema,
    as enumerated below:

    1. Formats input
    2. Stores final energy according to e_wo_entrop
    3. Tests compatibility, which was added to MPWorks in a later
        iteration

    Args:
        mpworks_doc: document to update schema for

    Returns:
        formatted doc
    """
    # Input
    last_calc = mpworks_doc['calculations'][-1]
    xc = last_calc['input']['incar'].get("GGA")
    if xc:
        xc.upper()
    mpworks_doc["input"].update(
        {"is_lasph": last_calc["input"]["incar"].get("LASPH", False),
         "potcar_spec": last_calc["input"].get("potcar_spec"),
         "xc_override": xc,
         "is_hubbard": last_calc["input"]["incar"].get("LDAU", False)})

    # Final energy - this is being changed because of a change in pymatgen
    #   input parsing that uses e_wo_entrop instead of e_fr_energy
    for calc in mpworks_doc['calculations']:
        total_e = calc['output']['ionic_steps'][-1]['electronic_steps']\
            [-1]['e_wo_entrp']
        e_per_atom = total_e / mpworks_doc['nsites']
        calc['output']['final_energy'] = total_e
        calc['output']['final_energy_per_atom'] = e_per_atom

    # Compatibility
    mpc = MaterialsProjectCompatibility("Advanced")
    func = mpworks_doc["pseudo_potential"]["functional"]
    labels = mpworks_doc["pseudo_potential"]["labels"]
    symbols = ["{} {}".format(func, label) for label in labels]
    parameters = {"run_type": mpworks_doc["run_type"],
                  "is_hubbard": mpworks_doc["is_hubbard"],
                  "hubbards": mpworks_doc["hubbards"],
                  "potcar_symbols": symbols}
    entry = ComputedEntry(Composition(mpworks_doc["unit_cell_formula"]),
                          0.0, 0.0, parameters=parameters,
                          entry_id=mpworks_doc["task_id"])
    try:
        mpworks_doc['is_compatible'] = bool(mpc.process_entry(entry))
    except:
        traceback.print_exc()
        logger.warning('ERROR in getting compatibility')
        mpworks_doc['is_compatible'] = None
    return mpworks_doc
