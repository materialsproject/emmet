"""
This module is intended to allow building derivative workflows
for material properties based on missing properties in a
materials collection
"""

from maggma.builder import Builder
from atomate.vasp.workflows.presets.core import wf_elastic_constant
from atomate.vasp.powerups import add_tags, add_modify_incar, add_priority
from atomate.utils.utils import get_fws_and_tasks
from pymatgen.analysis.elasticity.tensors import Tensor, SquareTensor,\
        get_tkd_value, symmetry_reduce
from pymatgen.analysis.elasticity.strain import Strain
from pymatgen.core.operations import SymmOp
from pymatgen import Structure
from fireworks import LaunchPad
import numpy as np
import logging

logger = logging.getLogger(__name__)

__author__ = "Joseph Montoya"
__maintainer__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"


# TODO: kind of specific to vasp in the add_tags, improve metadata handling
# TODO: I'm a bit wary to implement an incremental strategy here,
#       but I think it can be done
class PropertyWorkflowBuilder(Builder):
    def __init__(self, materials, wf_function, filter=None, lpad=None,
                 **kwargs):
        """
        Creates a elastic collection for materials

        Args:
            materials (Store): Store of materials properties

            filter (dict): dict filter for getting items to process
                e. g. {"elasticity": None}
            wf_function (method): method to generate a workflow
                based on structure in document with missing property
                can be custom method or atomate preset wf generator
            lpad (LaunchPad): fireworks launchpad to use for adding workflows
        """
        self.materials = materials
        self.wf_function = wf_function
        self.filter = filter
        self.lpad = lpad or LaunchPad.auto_load()

        super().__init__(sources=[materials], targets=[], **kwargs)

    def get_items(self):
        """
        Gets all items to create new workflows for

        Returns:

        """
        noprop_mats = self.materials.query(["structure", "material_id"],
                                           self.filter)
        # find existing tags in workflows
        current_wf_tags = self.lpad.workflows.distinct("metadata.tags")
        for mat in noprop_mats:
            yield mat, current_wf_tags

    def process_item(self, item):
        mat, current_wf_tags = item
        if mat['material_id'] in current_wf_tags:
            return None
        else:
            structure = Structure.from_dict(mat["structure"])
            wf = self.wf_function(structure)
            wf = add_tags(wf, [mat['material_id']])
            return wf

    def update_targets(self, items):
        """
        Filters items and updates the launchpad

        Args:
            items ([Workflow]): list of workflows to be added
        """
        items = filter(bool, items)
        self.lpad.bulk_add_wfs(items)

# TODO: build priorities?
def PriorityBuilder(Builder):
    def __init__(self, lpad, propjockey, **kwargs):
        self.lpad = lpad
        self.propjockey = propjockey
        pass


# TODO: maybe this should be somewhere else?
def generate_elastic_workflow(structure, tags=[]):
    """
    Generates a standard production workflow.

    Notes:
        Uses a primitive structure transformed into
        the conventional basis (for equivalent deformations).

        Adds the "minimal" category to the minimal portion
        of the workflow necessary to generate the elastic tensor,
        and the "minimal_full_stencil" category to the portion that
        includes all of the strain stencil, but is symmetrically complete
    """
    # transform the structure
    ieee_rot = Tensor.get_ieee_rotation(structure)
    assert SquareTensor(ieee_rot).is_rotation(tol=0.005)
    symm_op = SymmOp.from_rotation_and_translation(ieee_rot)
    ieee_structure = structure.copy()
    ieee_structure.apply_operation(symm_op)

    # construct workflow
    wf = wf_elastic_constant(ieee_structure)

    # Set categories, starting with optimization
    opt_fws = get_fws_and_tasks(wf, fw_name_constraint="optimization")
    wf.fws[opt_fws[0][0]].spec['elastic_category'] = "minimal"

    # find minimal set of fireworks using symmetry reduction
    fws_by_strain = {Strain(fw.tasks[-1]['pass_dict']['strain']): n
                     for n, fw in enumerate(wf.fws) if 'deformation' in fw.name}
    unique_tensors = symmetry_reduce(fws_by_strain.keys(), ieee_structure)
    for unique_tensor in unique_tensors:
        fw_index = get_tkd_value(fws_by_strain, unique_tensor)
        if np.isclose(unique_tensor, 0.005).any():
            wf.fws[fw_index].spec['elastic_category'] = "minimal"
        else:
            wf.fws[fw_index].spec['elastic_category'] = "minimal_full_stencil"

    # Add tags
    if tags:
        wf = add_tags(wf, tags)

    wf = add_modify_incar(wf)
    priority = 500 - structure.num_sites
    wf = add_priority(wf, priority)
    for fw in wf.fws:
        if fw.spec['elastic_category'] == 'minimal':
            fw.spec['_priority'] += 2000
        elif fw.spec['elastic_category'] == 'minimal_full_stencil':
            fw.spec['_priority'] += 1000
    return wf


def get_elastic_builder(materials, lpad=None, filter=None):
    """
    Args:
        materials (Store): materials store
        lpad (LaunchPad): LaunchPad to add workflows

    Returns:
        PropertyWorkflowBuilder for elastic workflow
    """
    if filter is None:
        filter = {"elasticity": None}
    return PropertyWorkflowBuilder(materials, filter,
                                   generate_elastic_workflow, lpad)

