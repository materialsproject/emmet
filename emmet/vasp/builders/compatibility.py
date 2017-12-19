import numpy as np
from datetime import datetime

from pymatgen import Composition

from maggma.builder import Builder

from atomate.utils.utils import get_mongolike

__author__ = "Joseph Montoya <montoyjh@lbl.gov>"


class MPWorksCompatibilityBuilder(Builder):
    def __init__(self, mpworks_tasks, atomate_tasks, query={},
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
        self.query = query
        self.incremental = incremental
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
            generator or list relevant tasks and materials to process into materials documents
        """

        self.logger.info("MPWorks Elastic Compatibility Builder Started")

        # Get only successful tasks
        q = dict(self.query)
        q["state"] = "successful"
        
        # only consider tasks that have been updated since tasks was last updated
        if self.incremental:
            q.update(self.mpworks_tasks.lu_filter(self.atomate_tasks))

        tasks_to_convert = self.mpworks_tasks.query(criteria=q)
        count = tasks_to_convert.count()
        self.logger.info("Found {} new/updated tasks to process".format(count))

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

        for n, task in enumerate(tasks_to_convert):
            self.logger.debug("Processing MPWorks task_id: {} of {}".format(task['task_id'], count))
            new_task_id = n + starting_taskid
            yield task, new_task_id

    def process_item(self, item):
        """
        Process the MPWorks tasks and materials into an Atomate tasks collection

        Args:
            item (dict): an mpworks document

        Returns:
            an Atomate task document
        """
        mpw_doc, new_task_id = item
        atomate_doc = convert_mpworks_to_atomate(mpw_doc)
        atomate_doc['last_updated'] = datetime.utcnow()
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
        self.logger.info("Updating {} atomate documents".format(len(items)))

        self.atomate_tasks.update(items, key='task_id')

    def finalize(self, cursor):
        self.atomate_tasks.close()
        self.mpworks_tasks.close()


## MPWorks key: Atomate key
conversion_schema = {"dir_name_full": "dir_name",
                     "last_updated": "last_updated",
                     "unit_cell_formula": "composition_unit_cell",
                     "reduced_cell_formula": "composition_reduced",
                     "pretty_formula": "formula_pretty",
                     "completed_at": "completed_at",
                     "chemsys": "chemsys",
                     "nsites": "nsites",
                     "run_tags": "tags",
                     "is_hubbard": "input.is_hubbard",
                     "input.is_lasph": "input.is_lasph",
                     "input.xc_override": "input.xc_override",
                     "input.potcar_spec": "input.potcar_spec",
                     "input.crystal": "input.structure",
                     "hubbards": "input.hubbards",
                     "pseudo_potential": "input.pseudo_potential",
                     "run_stats": "run_stats", # Not sure if completely compatible
                     "density": "output.density",
                     "schema_version": "_mpworks_meta.schema_version",
                     "spacegroup": "output.spacegroup",
                     "custodian": "custodian",
                     "run_type": "_mpworks_meta.run_type",
                     "elements": "elements",
                     "snl": "_mpworks_meta.snl", # Not sure if completely compatible
                     "task_id": "task_id", # might change this in the future
                     "nelements": "nelements",
                     "is_compatible": "_mpworks_meta.is_compatible",
                     "analysis.percent_delta_volume": "analysis.delta_volume_percent",
                     "analysis.warnings": "analysis.warnings", # Not sure if these are substantially different
                     "analysis.delta_volume": "analysis.delta_volume",
                     "analysis.max_force": "analysis.max_force",
                     "analysis.errors": "analysis.errors",
                     "analysis.errors_MP": "_mpworks_meta.errors_MP",
                     "analysis.bandgap": "output.bandgap",
                     "analysis.cbm": "output.cbm",
                     "analysis.is_gap_direct": "output.is_gap_direct",
                     "output.crystal": "output.structure",
                     "output.final_energy": "output.energy",
                     "output.final_energy_per_atom": "output.energy_per_atom",
                     "fw_id": "_mpworks_meta.fw_id",
                     "state": "state"
                     }

####### Orphan MPWorks keys
"""
"vaspinputset_name": - Don't need
"task_type": X need to convert manually to match atomate schema
"calculations": X need to reverse these, so handle manually
"name": - getting rid of this, it appears to just be "aflow"
"dir_name": - encompassed by dir_name_full
"anonymous_formula": X convert manually b/c doesn't really work the same
"deformation_matrix": X need to handle these manually as well
"""
###### Orphan Atomate keys
"""
"input.parameters" - Not clear what to do with this
"""

def set_mongolike(ddict, key, value):
    """
    Function to set key in a dictionary to value
    using a mongolike key

    Args:
        ddict (dict): dictionary for which to set key
        key (string): key containing strings and/or integers separated
            by periods to indicate subfields, e. g. calcs_reversed.0.output
        value: value to be placed into the dictionary corresponding to
            the mongolike key
    """
    lead_key = key.split('.', 1)[0]
    try:
        lead_key = int(lead_key) # for searching array data
        lead_key_is_int = True
    except:
        lead_key_is_int = False

    if '.' in key:
        remainder = key.split('.', 1)[1]
        next_key = remainder.split('.')[0]
        if lead_key not in ddict:
            if lead_key_is_int:
                raise ValueError("Error for key {}, One or more keys is an integer,"
                                 "but no list exists at that key, integer keys may "
                                 "only be specified when a list exists at that key.")
            ddict[lead_key] = {}
        set_mongolike(ddict[lead_key], remainder, value)
    else:
        ddict[key] = value


# TODO: could add the rest of these, e. g. Static, NSCF Bandstructure
task_type_conversion = {"Calculate deformed structure static optimize": "elastic deformation",
                        "Vasp force convergence optimize structure (2x)": "structure optimization",
                        "Optimize deformed structure": "elastic deformation"}

def convert_mpworks_to_atomate(mpworks_doc):
    """
    Function to convert an mpworks document into an atomate
    document, uses schema above and a few custom cases
    """
    # TODO: ensure energy compatibility (i.e. using e_wo_entrop)
    atomate_doc = {}
    for key_mpworks, key_atomate in conversion_schema.items():
        val = get_mongolike(mpworks_doc, key_mpworks)
        set_mongolike(atomate_doc, key_atomate, val)

    # Task type
    atomate_doc["task_label"] = task_type_conversion[mpworks_doc["task_type"]]

    # calculations
    atomate_doc["calcs_reversed"] = mpworks_doc["calculations"][::-1]

    # Final energy - this is being changed because of a change in pymatgen
    #       input parsing that uses e_wo_entrop instead of e_fr_energy
    for calc in atomate_doc['calcs_reversed']:
        total_e = calc['output']['ionic_steps'][-1]['e_wo_entrp']
        e_per_atom = total_e / atomate_doc['nsites']
        calc['output']['energy'] = total_e
        calc['output']['energy_per_atom'] = e_per_atom
        calc['output'].pop('final_energy')
        calc['output'].pop('final_energy_per_atom')
        calc['output']['structure'] = calc['output'].pop('crystal')
    atomate_doc['output']['energy'] = \
        atomate_doc['calcs_reversed'][0]['output']['energy']
    atomate_doc['output']['energy_per_atom'] = \
        atomate_doc['calcs_reversed'][0]['output']['energy_per_atom']

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
        set_mongolike(atomate_doc, "transmuter.transformations", 
                      ["DeformStructureTransformation"])
        set_mongolike(atomate_doc, "transmuter.transformation_params", 
                      [{"deformation": defo}])

    return atomate_doc


def convert_string_deformation_to_list(string_defo):
    """
    Some of the older documents in the mpworks schema have a string version
    of the deformation matrix, this function fixes those
    """
    string_defo = string_defo.replace("[", "").replace("]", "").split()
    defo = np.array(string_defo, dtype=float).reshape(3, 3)
    return defo.tolist()
