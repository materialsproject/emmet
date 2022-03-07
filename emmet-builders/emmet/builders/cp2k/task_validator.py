from typing import Dict, Optional

from maggma.builders import MapBuilder
from maggma.core import Store

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.vasp.task import TaskDocument
from emmet.core.vasp.validation import DeprecationMessage, ValidationDoc


class TaskValidator(MapBuilder):
    def __init__(
        self,
        tasks: Store,
        task_validation: Store,
        settings: Optional[EmmetBuildSettings] = None,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks: Store of task documents
            task_validation: Store of task_types for tasks
        """
        self.tasks = tasks
        self.task_validation = task_validation
        self.settings = EmmetBuildSettings.autoload(settings)
        self.query = query
        self.kwargs = kwargs

        super().__init__(
            source=tasks,
            target=task_validation,
            projection=[
                "orig_inputs",
                "input.hubbards",
                "output.structure",
                "output.bandgap",
                "calcs_reversed.output.ionic_steps.electronic_steps.e_fr_energy",
                "tags",
                # Need these two for proper run_type determination
                "calcs_reversed.input.parameters",
                "calcs_reversed.input.incar",
            ],
            query=query,
            **kwargs,
        )

    def unary_function(self, item):
        """
        Find the task_type for the item

        Args:
            item (dict): a (projection of a) task doc
        """
        task_doc = TaskDocument(**item)
        validation_doc = ValidationDoc.from_task_doc(
            task_doc=task_doc,
            kpts_tolerance=self.settings.VASP_KPTS_TOLERANCE,
            kspacing_tolerance=self.settings.VASP_KSPACING_TOLERANCE,
            input_sets=self.settings.VASP_DEFAULT_INPUT_SETS,
            LDAU_fields=self.settings.VASP_CHECKED_LDAU_FIELDS,
            max_allowed_scf_gradient=self.settings.VASP_MAX_SCF_GRADIENT,
        )

        bad_tags = list(set(task_doc.tags).intersection(self.settings.DEPRECATED_TAGS))
        if len(bad_tags) > 0:
            validation_doc.warnings.append(f"Manual Deprecation by tags: {bad_tags}")
            validation_doc.valid = False
            validation_doc.reasons.append(DeprecationMessage.MANUAL)

        return validation_doc
