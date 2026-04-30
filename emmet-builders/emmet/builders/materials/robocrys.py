from typing import Iterator

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map
from emmet.core import __version__
from emmet.core.featurization.robocrys.condense.mineral import MineralMatcher
from emmet.core.robocrys import RobocrystallogapherDoc


def build_robocrys_docs(
    input_documents: list[BaseBuilderInput], **kwargs
) -> Iterator[RobocrystallogapherDoc]:
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
        Iterator[RobocrystallogapherDoc]
    """
    mineral_matcher = MineralMatcher()
    return filter_map(
        RobocrystallogapherDoc.from_structure,
        input_documents,
        work_keys=["deprecated", "material_id", "structure", "origins"],
        mineral_matcher=mineral_matcher,
        robocrys_version=__version__,
        **kwargs
    )
