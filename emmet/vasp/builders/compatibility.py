import numpy as np
import os
from datetime import datetime
from itertools import chain

from monty.json import jsanitize

from pymatgen import Structure, Composition
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from pymatgen.analysis.elasticity.strain import Strain, Deformation
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.structure_matcher import StructureMatcher, ElementComparator

from maggma.builder import Builder

from emmet.vasp.builders.task_tagger import TaskTagger
from atomate.utils.utils import get_mongolike, get_structure_metadata

__author__ = "Joseph Montoya <montoyjh@lbl.gov>"


class MPWorksCompatibilityBuilder(Builder):
    def __init__(self, mpworks_tasks, atomate_tasks, query={}, preserve_mpids=True, 
                 incremental=True, **kwargs):
        """
        Converts a task collection from the MPWorks schema to
        Atomate tasks.

        Args:
            mpworks_tasks (Store): Store of task documents
            atomate_tasks (Store): Store of elastic properties
            preserve_mpids (bool): whether to keep the mpids or create
                new ones based on the counter in a new collection
            query (dict): dictionary to limit materials to be analyzed
        """
        #TODO: implement preserve_mpids

        self.mpworks_tasks = mpworks_tasks
        self.atomate_tasks = atomate_tasks 
        self.query = query
        self.kwargs = kwargs
        self.incremental = incremental

        super().__init__(sources=[mpworks_tasks],
                         targets=[atomate_tasks],
                         **kwargs)

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

        for task in tasks_to_convert:
            self.logger.debug("Processing MPWorks task_id: {} of {}".format(task['task_id'], count))
            yield task

    def process_item(self, item):
        """
        Process the MPWorks tasks and materials into an Atomate tasks collection

        Args:
            item dict: a dict of material_id, structure, and tasks

        Returns:
            dict: an Atomate task document dictionary 
        """
        atomate_doc = convert_mpworks_to_atomate(item)
        if "original_task_id" in item:
            original_doc = self.mpworks_tasks.collection.find_one(
                {"task_id": item['original_task_id']}, ['output.crystal'])
            parent_structure = Structure.from_dict(original_doc['output']['crystal'])
            atomate_doc['parent_structure'] = get_structure_metadata(parent_structure)
        atomate_doc['last_updated'] = datetime.utcnow()
        return atomate_doc

    def update_targets(self, items):
        """
        Inserts the new tasks into atomate_tasks collection 

        Args:
            items ([([dict],[int])]): A list of tuples of materials to update and the corresponding processed task_ids
        """
        self.logger.info("Updating {} atomate documents".format(len(items)))

        self.atomate_tasks.collection.insert_many(items, ordered=False)

        # This is just too slow at the moment, need to refactor maggma maybe?
        # self.atomate_tasks.update("task_id", items, update_lu=True, ordered=False)

        
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
                     #"task_id": "_mpworks_meta.task_id",
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
                     "fw_id": "_mpworks_meta.fw_id"
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
"input.parameters" - Don't really know what to do with this
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
    except:
        pass

    if '.' in key:
        remainder = key.split('.', 1)[1]
        next_key = remainder.split('.')[0]
        # Note: Be careful here if trying to set the value of a list,
        #  you can't set values on a nonexistent list
        if lead_key not in ddict:
            ddict[lead_key] = {}
        set_mongolike(ddict[lead_key], remainder, value)
    else:
        ddict[key] = value


# TODO: should add the rest of these
task_type_conversion = {"Calculate deformed structure static optimize": "elastic deformation",
                        "Vasp force convergence optimize structure (2x)": "structure optimization",
                        "Optimize deformed structure": "elastic deformation"}

def convert_mpworks_to_atomate(mpworks_doc):
    """
    Function to convert an mpworks document into an atomate
    document, uses schema above and a few custom cases
    """
    atomate_doc = {}
    for key_mpworks, key_atomate in conversion_schema.items():
        val = get_mongolike(mpworks_doc, key_mpworks)
        set_mongolike(atomate_doc, key_atomate, val)

    # Task type
    atomate_doc["task_label"] = task_type_conversion[mpworks_doc["task_type"]]

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
        set_mongolike(atomate_doc, "transmuter.transformations", 
                      ["DeformStructureTransformation"])
        set_mongolike(atomate_doc, "transmuter.transformation_params", 
                      [{"deformation": defo}])

    # original task id
    if "original_task_id" in mpworks_doc:
        atomate_doc["_mpworks_meta"]["original_task_id"] = mpworks_doc["original_task_id"]
    return atomate_doc 

def convert_string_deformation_to_list(string_defo):
    """
    Some of the older documents in the mpworks schema have a string version
    of the deformation matrix, this function fixes those
    """
    string_defo = string_defo.replace("[", "").replace("]", "").split()
    defo = np.array(string_defo, dtype=float).reshape(3, 3)
    return defo.tolist()
