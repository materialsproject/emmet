from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

from emmet.builders.base import BaseBuilderInput
from emmet.builders.utils import try_call
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
        filter(
            lambda y: y is not None,
            map(
                lambda x: try_call(
                    BondingDoc.from_structure,
                    deprecated=x.deprecated,
                    material_id=x.material_id,
                    structure=try_call(
                        lambda s: SpacegroupAnalyzer(
                            s
                        ).get_conventional_standard_structure(),
                        x.structure,
                    ),
                ),
                input_documents,
            ),
        )
    )
