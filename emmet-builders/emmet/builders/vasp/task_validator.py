from typing import Any

from emmet.builders.settings import EmmetBuildSettings
from emmet.builders.utils import get_potcar_stats
from emmet.core.tasks import CoreTaskDoc, TaskDoc
from emmet.core.types.enums import DeprecationMessage
from emmet.core.vasp.task_valid import TaskDocument
from emmet.core.vasp.validation_legacy import ValidationDoc


def build_validation_doc(
    input: CoreTaskDoc | TaskDoc | TaskDocument,
    settings: EmmetBuildSettings = EmmetBuildSettings(),
    potcar_stats: dict[str, Any] = get_potcar_stats(method="stored"),
) -> ValidationDoc:
    """
    Build a ValidationDoc from a CoreTaskDoc by checking CoreTaskDoc
    parameters against reference values.

    Args:
        input: Parsed task document to validate.
        settings: Reference values used in validation, defaults defined in EmmetBuildSettings.
            Relevant settings: VASP_KSPACING_TOLERANCE, VASP_DEFAULT_INPUT_SETS, VASP_CHECKED_LDAU_FIELDS,
            VASP_MAX_SCF_GRADIENT, and DEPRECATED_TAGS.
        potcar_stats: POTCAR stats used to validate POTCARs used for the source calculation
            for 'input'. Defaults to compiled values in 'emmet.builders.vasp.mp_potcar_stats.json.gz'

    Returns:
        ValidationDoc
    """
    validation_doc = ValidationDoc.from_task_doc(
        task_doc=input,
        kpts_tolerance=0.4 if "mp_production_old" in input.tags else 0.9,
        kspacing_tolerance=settings.VASP_KSPACING_TOLERANCE,
        input_sets=settings.VASP_DEFAULT_INPUT_SETS,
        LDAU_fields=settings.VASP_CHECKED_LDAU_FIELDS,
        max_allowed_scf_gradient=settings.VASP_MAX_SCF_GRADIENT,
        potcar_stats=potcar_stats,
    )

    bad_tags = list(set(input.tags).intersection(settings.DEPRECATED_TAGS))

    if len(bad_tags) > 0:
        validation_doc.warnings.append(f"Manual Deprecation by tags: {bad_tags}")
        validation_doc.valid = False
        validation_doc.reasons.append(DeprecationMessage.MANUAL)

    return validation_doc
