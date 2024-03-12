from typing import Dict, Optional

from maggma.builders import MapBuilder
from maggma.core import Store

from emmet.builders.settings import EmmetBuildSettings
from emmet.builders.utils import get_potcar_stats
from emmet.core.vasp.calc_types.enums import CalcType
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.validation import DeprecationMessage, ValidationDoc


class TaskValidator(MapBuilder):
    def __init__(
        self,
        tasks: Store,
        task_validation: Store,
        potcar_stats: Optional[Dict[CalcType, Dict[str, str]]] = None,
        settings: Optional[EmmetBuildSettings] = None,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks: Store of task documents
            task_validation: Store of task_types for tasks
            potcar_stats: Optional dictionary of potcar hash data.
                Mapping is calculation type -> potcar symbol -> hash value.
        """
        self.tasks = tasks
        self.task_validation = task_validation
        self.settings = EmmetBuildSettings.autoload(settings)
        self.query = query
        self.kwargs = kwargs
        self.potcar_stats = potcar_stats

        # Set up potcar cache if appropriate
        if self.settings.VASP_VALIDATE_POTCAR_STATS:
            if not self.potcar_stats:
                self.potcar_stats = get_potcar_stats()
        else:
            self.potcar_stats = None

        super().__init__(
            source=tasks,
            target=task_validation,
            projection=[
                "orig_inputs",
                "input.hubbards",
                "output.structure",
                "output.bandgap",
                "chemsys",
                "calcs_reversed",
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
            potcar_stats=self.potcar_stats,
        )

        bad_tags = list(set(task_doc.tags).intersection(self.settings.DEPRECATED_TAGS))
        if len(bad_tags) > 0:
            validation_doc.warnings.append(f"Manual Deprecation by tags: {bad_tags}")
            validation_doc.valid = False
            validation_doc.reasons.append(DeprecationMessage.MANUAL)

        return validation_doc
