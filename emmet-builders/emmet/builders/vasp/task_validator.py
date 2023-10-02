from typing import Dict, Optional
from collections import defaultdict

from maggma.builders import MapBuilder
from maggma.core import Store

from emmet.builders.settings import EmmetBuildSettings
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.calc_types.enums import CalcType
from emmet.core.vasp.validation import DeprecationMessage, ValidationDoc


class TaskValidator(MapBuilder):
    def __init__(
        self,
        tasks: Store,
        task_validation: Store,
        potcar_hashes: Optional[Dict[CalcType, Dict[str, str]]] = None,
        settings: Optional[EmmetBuildSettings] = None,
        query: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks: Store of task documents
            task_validation: Store of task_types for tasks
            potcar_hashes: Optional dictionary of potcar hash data.
                Mapping is calculation type -> potcar symbol -> hash value.
        """
        self.tasks = tasks
        self.task_validation = task_validation
        self.settings = EmmetBuildSettings.autoload(settings)
        self.query = query
        self.kwargs = kwargs
        self.potcar_hashes = potcar_hashes

        # Set up potcar cache if appropriate
        if self.settings.VASP_VALIDATE_POTCAR_HASHES:
            if not self.potcar_hashes:
                from pymatgen.io.vasp.inputs import PotcarSingle

                hashes = defaultdict(dict)  # type: dict

                for (
                    calc_type,
                    input_set,
                ) in self.settings.VASP_DEFAULT_INPUT_SETS.items():
                    functional = input_set.CONFIG["POTCAR_FUNCTIONAL"]
                    for potcar_symbol in input_set.CONFIG["POTCAR"].values():
                        potcar = PotcarSingle.from_symbol_and_functional(
                            symbol=potcar_symbol, functional=functional
                        )
                        hashes[calc_type][potcar_symbol] = potcar.md5_header_hash

                self.potcar_hashes = potcar_hashes
        else:
            self.potcar_hashes = None

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
            potcar_hashes=self.potcar_hashes,
        )

        bad_tags = list(set(task_doc.tags).intersection(self.settings.DEPRECATED_TAGS))
        if len(bad_tags) > 0:
            validation_doc.warnings.append(f"Manual Deprecation by tags: {bad_tags}")
            validation_doc.valid = False
            validation_doc.reasons.append(DeprecationMessage.MANUAL)

        return validation_doc
