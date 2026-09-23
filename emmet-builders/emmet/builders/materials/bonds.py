from typing import Iterator, cast

from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import filter_map, try_call
from emmet.core.bonds import BondingDoc


def build_bonding_docs(
    input_documents: list[BaseBuilderInput], **kwargs
) -> Iterator[BondingDoc]:
    """
    Generate bonding documents from input structures.

    Transforms a list of BaseBuilderInput documents containing
    Pymatgen structures into corresponding BondingDoc instances by
    analyzing the bonding environment of each structure.

    Caller is responsible for creating BaseBuilderInput instances
    within their data pipeline context.

    Args:
        input_documents: List of BaseBuilderInput documents to process.

    Returns:
       Iterator[BondingDoc]
    """

    def _build(
        deprecated: bool, material_id: str, structure, _log_extra=None, **kwargs
    ) -> BondingDoc | None:
        return BondingDoc.from_structure(
            deprecated=deprecated,
            material_id=material_id,
            structure=try_call(
                lambda s: SpacegroupAnalyzer(s).get_conventional_standard_structure(),
                structure,
                _log_extra=_log_extra,
            ),
            **kwargs,
        )

    yield from cast(
        Iterator[BondingDoc],
        filter_map(
            _build,
            input_documents,
            work_keys=["deprecated", "material_id", "structure"],
            **kwargs,
        ),
    )
