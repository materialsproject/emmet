"""
This module is intended to allow building derivative workflows
for material properties based on missing properties in a
materials collection
"""

import numpy as np
import logging
import six

from maggma.builder import Builder
from atomate.vasp.workflows.presets.core import wf_elastic_constant
from atomate.vasp.powerups import add_tags, add_modify_incar, add_priority
from atomate.utils.utils import get_fws_and_tasks, load_class
from pymatgen.core.tensors import Tensor, SquareTensor,\
        get_tkd_value, symmetry_reduce
from pymatgen.analysis.elasticity.strain import Strain
from pymatgen.core.operations import SymmOp
from pymatgen import Structure
from fireworks import LaunchPad

logger = logging.getLogger(__name__)

__author__ = "Joseph Montoya"
__maintainer__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"


# TODO: kind of specific to vasp in the add_tags, improve metadata handling,
#       in principle this could be abstracted to just build workflows from
#       collections generally
# TODO: I'm a bit wary to implement an incremental strategy here,
#       but I think it can be done
class PropertyWorkflowBuilder(Builder):
    def __init__(self, source, materials, wf_function,
                 material_filter=None, lpad=None, **kwargs):
        """
        Adds workflows to a launchpad based on material inputs.
        This is primarily to be used for derivative property
        workflows but could in principles used to generate workflows
        for any workflow that can be invoked from structure data

        Args:
            source (Store): store of properties
            materials (Store): Store of materials properties
            material_filter (dict): dict filter for getting items to process
                e. g. {"elasticity": None}
            wf_function (string or method): method to generate a workflow
                based on structure in document with missing property
                can be a string to be loaded or a custom method.
                Note that the builder/runner will not be serializable
                with custom methods.
            lpad (LaunchPad or dict): fireworks launchpad to use for adding
                workflows, can either be None (autoloaded), a LaunchPad
                instance, or a dict from which the LaunchPad will be invoked
            **kwargs (kwargs): kwargs for builder
        """
        self.source = source
        self.materials = materials
        # Will this be pickled properly for multiprocessing? could just put
        # it into the processor if that's the case
        if isinstance(wf_function, six.string_types):
            self.wf_function = load_class(*wf_function.rsplit('.', 1))
            self._wf_function_string = wf_function
        elif callable(wf_function):
            self.wf_function = wf_function
            self._wf_function_string = None
        else:
            raise ValueError("wf_function must be callable or a string "
                             "corresponding to a loadable method")
        self.material_filter = material_filter
        if lpad is None:
            self.lpad = LaunchPad.auto_load()
        elif isinstance(lpad, dict):
            self.lpad = LaunchPad.from_dict(lpad)
        else:
            self.lpad = lpad

        super().__init__(sources=[source, materials],
                         targets=[], **kwargs)

    def get_items(self):
        """
        Gets all items for which new workflows are created

        Returns:
             generator for items
        """
        wf_inputs = self.materials.query(properties=["structure", "task_id"],
                                         criteria=self.material_filter,
                                         no_cursor_timeout=True)
        # find existing tags in workflows
        current_prop_ids = self.source.distinct("task_id")
        current_wf_tags = self.lpad.workflows.distinct("metadata.tags")
        ids_to_filter = list(set(current_prop_ids + current_wf_tags))
        for wf_input in wf_inputs:
            logger.debug("Processing {}".format(wf_input["task_id"]))
            yield wf_input, ids_to_filter

    def process_item(self, item):
        """
        Processes items into workflows

        Args:
            item ((dict, list)): pair of doc and task_ids to filter

        Returns:
            Workflow
        """
        wf_input, ids_to_filter = item
        mat_id = wf_input["task_id"]
        if mat_id in ids_to_filter:
            return None
        else:
            structure = Structure.from_dict(wf_input.get('structure'))
            wf = self.wf_function(structure)
            wf = add_tags(wf, [mat_id])
            return wf

    def update_targets(self, items):
        """
        Filters items and updates the launchpad

        Args:
            items ([Workflow]): list of workflows to be added
        """
        items = filter(bool, items)
        self.lpad.bulk_add_wfs(items)

    def as_dict(self):
        d = super().as_dict()
        if self._wf_function_string:
            d['wf_function'] = self._wf_function_string
        return d


# TODO: maybe this should be somewhere else, atomate?
def generate_elastic_workflow(structure, tags=None):
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
    if tags == None:
        tags = []
    # transform the structure
    ieee_rot = Tensor.get_ieee_rotation(structure)
    if not SquareTensor(ieee_rot).is_rotation(tol=0.005):
        raise ValueError("Rotation matrix does not satisfy rotation conditions")
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
    unique_tensors = symmetry_reduce(list(fws_by_strain.keys()), ieee_structure)
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
        if fw.spec.get('elastic_category') == 'minimal':
            fw.spec['_priority'] += 2000
        elif fw.spec.get('elastic_category') == 'minimal_full_stencil':
            fw.spec['_priority'] += 1000
    return wf


def get_elastic_wf_builder(elasticity, materials, lpad=None, material_filter=None):
    """
    Args:
        elasticity (Store): Elasticity store
        materials (Store): Materials store
        lpad (LaunchPad): LaunchPad to add workflows

    Returns:
        PropertyWorkflowBuilder for elastic workflow
    """
    wf_method = "emmet.workflows.property_workflows.generate_elastic_workflow"
    return PropertyWorkflowBuilder(elasticity, materials, wf_method,
                                   material_filter, lpad)
