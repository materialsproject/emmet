from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.builders.base import BaseBuilderInput
from emmet.core.bonds import BondingDoc


def build_bonding_docs(
    input_documents: list[BaseBuilderInput],
) -> list[BondingDoc]:
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
       list[BondingDoc]
    """
    return list(
        map(
            lambda x: BondingDoc.from_structure(
                builder_meta=x.builder_meta,
                deprecated=x.deprecated,
                material_id=x.material_id,
                structure=SpacegroupAnalyzer(
                    x.structure
                ).get_conventional_standard_structure(),
            ),
            input_documents,
        )
    )
