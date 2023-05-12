from typing import Any, Optional, Dict
from fastapi import Query
from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS


class ThermoCorrectionQuery(QueryOperator):
    """
    Method to generate a query on thermodynamic.
    """

    def query(
        self,
        has_correction: Optional[bool] = Query(
            False,
            description="Whether the thermodynamics involve a single-point energy correction.",
        ),
        correction_level_of_theory: Optional[str] = Query(
            None,
            description="Level of theory used for the single-point energy correction. Default is None, "
            "meaning that level of theory will not be queried.",
        ),
        correction_solvent: Optional[str] = Query(
            None,
            description="Solvent data used for the single-point energy correction. Default is None, "
            "meaning that solvent will not be queried.",
        ),
        correction_lot_solvent: Optional[str] = Query(
            None,
            description="String representing the combination of level of theory and solvent for the "
            "single-point energy correction. Default is None, meaning lot_solvent will not be "
            "queried.",
        ),
        combined_lot_solvent: Optional[str] = Query(
            None,
            description="String representing the combination of level of theory and solvent for the complete "
            "thermodynamic calculation, including the frequency analysis and single-point energy "
            "correction.",
        ),
    ) -> STORE_PARAMS:
        self.level_of_theory = correction_level_of_theory
        self.solvent = correction_solvent
        self.lot_solvent = correction_lot_solvent
        self.combined = combined_lot_solvent

        crit: Dict[str, Any] = {"correction": has_correction}  # type: ignore

        if self.level_of_theory:
            crit.update({"correction_level_of_theory": correction_level_of_theory})
        if self.solvent:
            crit.update({"correction_solvent": correction_solvent})
        if self.lot_solvent:
            crit.update({"correction_lot_solvent": correction_lot_solvent})
        if self.combined:
            crit.update({"combined_lot_solvent": combined_lot_solvent})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("correction_level_of_theory", False),
            ("correction_solvent", False),
            ("correction_lot_solvent", False),
            ("combined_lot_solvent", False),
        ]
