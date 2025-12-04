from robocrys import __version__ as __robocrys_version__
from robocrys.condense.mineral import MineralMatcher

from emmet.builders.base import BaseBuilderInput
from emmet.core.robocrys import RobocrystallogapherDoc


def build_robocrys_docs(
    input_documents: list[BaseBuilderInput],
) -> list[RobocrystallogapherDoc]:
    """
    Generate robocrystallographer descriptions from input structures.

    Transforms a list of BaseBuilderInput documents containing
    Pymatgen structures into corresponding RobocrystallogapherDoc instances by
    using robocrys' StructureCondenser and StructureDescriber classes.

    Caller is responsible for creating BaseBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of BaseBuilderInput documents to process.

    Returns:
        list[RobocrystallogapherDoc]
    """
    mineral_matcher = MineralMatcher()
    return list(
        map(
            lambda x: RobocrystallogapherDoc.from_structure(
                builder_meta=x.builder_meta,
                deprecated=x.deprecated,
                material_id=x.material_id,
                mineral_matcher=mineral_matcher,
                robocrys_version=__robocrys_version__,
                structure=x.structure,
            ),
            input_documents,
        )
    )
