from typing import Dict, List, Union

import numpy as np
from maggma.builders import MapBuilder
from maggma.core import Store
from pymatgen import Structure

from emmet.core import SETTINGS
from emmet.core.vasp.calc_types import run_type, task_type
from emmet.core.vasp.task import TaskDocument
from emmet.core.vasp.validation import DeprecationMessage, ValidationDoc

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"


class TaskValidator(MapBuilder):
    def __init__(
        self,
        tasks: Store,
        task_validation: Store,
        kpts_tolerance: float = SETTINGS.VASP_KPTS_TOLERANCE,
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks: Store of task documents
            task_validation: Store of task_types for tasks
            input_sets: dictionary of task_type and pymatgen input set to validate against
            kpts_tolerance: the minimum kpt density as dictated by the InputSet to require
            LDAU_fields: LDAU fields to check for consistency
        """
        self.tasks = tasks
        self.task_validation = task_validation
        self.kpts_tolerance = kpts_tolerance

        self.kwargs = kwargs

        super().__init__(
            source=tasks,
            target=task_validation,
            projection=["orig_inputs", "output.structure", "input.parameters"],
            **kwargs,
        )

    def unary_function(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        task_doc = TaskDocument(**item)
        return ValidationDoc.from_task_doc(task_doc=task_doc).dict()
