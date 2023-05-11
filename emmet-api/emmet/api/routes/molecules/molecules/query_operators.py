from typing import Any, Dict, Optional

from fastapi import Body, HTTPException, Query

from maggma.api.query_operator import QueryOperator
from maggma.api.utils import STORE_PARAMS

from emmet.api.routes.materials.materials.utils import chemsys_to_criteria

from pymatgen.analysis.molecule_matcher import MoleculeMatcher
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Molecule


class FormulaQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        formula.

    NOTE: wildcards are not currently supported. It's unclear, at present,
    if wildcards are really necessary or useful for molecular queries. Even
    if they are used, they might be different than the wildcards used on the
    materials side. For instance, one might desire wildcard numbers, rather than
    wildcard elements, e.g. "C1 Li* O3"
    """

    def query(
        self,
        formula: Optional[str] = Query(
            None,
            description="Query by alphabetical formula. \
A comma delimited string list of alphabetical formulas can also be provided.",
        ),
    ) -> STORE_PARAMS:
        crit: Dict[str, Any] = {}  # type: ignore

        if formula:
            # Do we need to handle wildcards? For now, don't worry about it.
            # See: emmet.api.routes.materials.utils.formula_to_criteria
            if "," in formula:
                crit.update({"formula_alphabetical": {"$in": [x.strip() for x in formula.split(",")]}})  # type: ignore
            else:
                crit.update({"formula_alphabetical": formula})  # type: ignore

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("formula_alphabetical", False)]


class ChemsysQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        chemical system with wild cards.
    """

    def query(
        self,
        chemsys: Optional[str] = Query(
            None,
            description="A comma delimited string list of chemical systems. \
Wildcards for unknown elements only supported for single chemsys queries",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if chemsys:
            crit.update(chemsys_to_criteria(chemsys))

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = ["chemsys", "elements", "nelements"]
        return [(key, False) for key in keys]


class ElementsQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by element data
    """

    def query(
        self,
        elements: Optional[str] = Query(
            None,
            description="Query by elements in the material composition as a comma-separated list",
        ),
        exclude_elements: Optional[str] = Query(
            None,
            description="Query by excluded elements in the material composition as a comma-separated list",
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if elements or exclude_elements:
            crit["elements"] = {}

        if elements:
            try:
                element_list = [Element(e.strip()) for e in elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )

            crit["elements"]["$all"] = [str(el) for el in element_list]

        if exclude_elements:
            try:
                element_list = [
                    Element(e.strip()) for e in exclude_elements.strip().split(",")
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )
            crit["elements"]["$nin"] = [str(el) for el in element_list]

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("elements", False)]


class ChargeSpinQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        charge and spin multiplicity.
    """

    def query(
        self,
        charge: Optional[int] = Query(
            None,
            description="Query by molecular charge",
        ),
        spin_multiplicity: Optional[int] = Query(
            None, description="Query by molecular spin multiplicity."
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if charge:
            crit.update({"charge": charge})
        if spin_multiplicity:
            crit.update({"spin_multiplicity": spin_multiplicity})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("charge", False), ("spin_multiplicity", False)]


class DeprecationQuery(QueryOperator):
    """
    Method to generate a deprecation state query
    """

    def query(
        self,
        deprecated: Optional[bool] = Query(
            False,
            description="Whether the material is marked as deprecated",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if deprecated is not None:
            crit.update({"deprecated": deprecated})

        return {"criteria": crit}


class MultiTaskIDQuery(QueryOperator):
    """
    Method to generate a query for different task_ids
    """

    def query(
        self,
        task_ids: Optional[str] = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
            # TODO: do task_ids need to be converted to ints?
            crit.update(
                {
                    "task_ids": {
                        "$in": [task_id.strip() for task_id in task_ids.split(",")]
                    }
                }
            )

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("task_ids", False)]


class MultiMPculeIDQuery(QueryOperator):
    """
    Method to generate a query for different root-level mpcule_id values
    """

    def query(
        self,
        molecule_ids: Optional[str] = Query(
            None, description="Comma-separated list of MPculeIDs to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if molecule_ids:
            molecule_ids_list = [
                mpcule_id.strip() for mpcule_id in molecule_ids.split(",")
            ]

            if len(molecule_ids_list) == 1:
                crit.update({"molecule_id": molecule_ids_list[0]})
            else:
                crit.update({"molecule_id": {"$in": molecule_ids_list}})

        return {"criteria": crit}


class FindMoleculeQuery(QueryOperator):
    """
    Method to generate a find molecule query
    """

    def query(
        self,
        molecule: Molecule = Body(
            ...,
            description="Pymatgen Molecule object to query with",
        ),
        tolerance: float = Query(
            0.01,
            description="RMSD difference threshold. Default is 0.01.",
        ),
        charge: Optional[int] = Query(
            None,
            description="Molecule charge. If None (default), don't limit by charge.",
        ),
        spin_multiplicity: Optional[int] = Query(
            None,
            description="Molecule spin_multiplicity. If None (default), don't limit by spin multiplicity.",
        ),
        _limit: int = Query(
            1,
            description="Maximum number of matches to show. Defaults to 1, only showing the best match.",
        ),
    ) -> STORE_PARAMS:
        self.tolerance = tolerance
        self._limit = _limit
        self.molecule = molecule

        crit: Dict[str, Any] = dict()

        if charge is not None:
            crit.update({"charge": charge})

        if spin_multiplicity is not None:
            crit.update({"spin_multiplicity": spin_multiplicity})

        try:
            if isinstance(molecule, dict):
                m = Molecule.from_dict(molecule)  # type: ignore
            elif isinstance(molecule, Molecule):
                m = molecule  # type: ignore
            elif isinstance(molecule, str):
                m = Molecule.from_str(molecule)  # type: ignore
            else:
                raise Exception("Unexpected type for molecule")

            comp = dict(m.composition)  # type: ignore

            crit.update({"composition": comp})
            return {"criteria": crit}
        except Exception:
            raise HTTPException(
                status_code=404,
                detail="Body cannot be converted to a pymatgen Molecule object.",
            )

    def post_process(self, docs, query):
        m1 = Molecule.from_dict(self.molecule)

        match = MoleculeMatcher(tolerance=self.tolerance)

        matches = list()

        for doc in docs:
            m2 = Molecule.from_dict(doc["molecule"])
            matched = match.fit(m1, m2)

            if matched:
                rmsd = match.get_rmsd(m1, m2)

                matches.append(
                    {
                        "molecule_id": doc["molecule_id"],
                        "rmsd": rmsd,
                    }
                )

        response = sorted(
            matches[: self._limit],
            key=lambda x: x["rmsd"],
        )

        return response

    def ensure_indexes(self):  # pragma: no cover
        return [("composition", False)]


class CalcMethodQuery(QueryOperator):
    """
    Method to generate a query based on level of theory and solvent.

    This query differs from ExactCalcMethodQuery in that CalcMethodQuery will check
    that the desired level of theory and/or solvent was used for some calculations
    (they are included in the sets of unique levels of theory, solvents, or lot-solvent
    combinations), whereas ExactCalcMethodQuery will check that the desired level of theory
    and/or solvent were used to generate the specific document being queried.
    """

    def query(
        self,
        level_of_theory: Optional[str] = Query(
            None,
            description="Level of theory used for calculation. Default is None, meaning that level of theory"
            "will not be queried.",
        ),
        solvent: Optional[str] = Query(
            None,
            description="Solvent data used for calculation. Default is None, meaning that solvent will not be"
            "queried.",
        ),
        lot_solvent: Optional[str] = Query(
            None,
            description="String representing the combination of level of theory and solvent. Default is None,"
            "meaning lot_solvent will not be queried.",
        ),
        _limit: int = Query(
            100, description="Maximum number of matches to show. Defaults to 100."
        ),
    ):
        self._limit = _limit
        self.level_of_theory = level_of_theory
        self.solvent = solvent
        self.lot_solvent = lot_solvent

        crit = dict()

        if self.level_of_theory:
            crit.update({"unique_levels_of_theory": level_of_theory})
        if self.solvent:
            crit.update({"unique_solvents": solvent})
        if self.lot_solvent:
            crit.update({"unique_lot_solvents": lot_solvent})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [
            ("unique_levels_of_theory", False),
            ("unique_solvents", False),
            ("unique_lot_solvents", False),
        ]

    def post_process(self, docs, query):
        # TODO: should this be somehow sorted?
        response = docs[: self._limit]

        return response


class ExactCalcMethodQuery(QueryOperator):
    """
    Method to generate a query based on level of theory and solvent

    This query differs from CalcMethodQuery in that CalcMethodQuery will check
    that the desired level of theory and/or solvent was used for some calculations
    (they are included in the sets of unique levels of theory, solvents, or lot-solvent
    combinations), whereas ExactCalcMethodQuery will check that the desired level of theory
    and/or solvent were used to generate the specific document being queried.
    """

    def query(
        self,
        level_of_theory: Optional[str] = Query(
            None,
            description="Level of theory used for calculation. Default is None, meaning that level of theory"
            "will not be queried.",
        ),
        solvent: Optional[str] = Query(
            None,
            description="Solvent data used for calculation. Default is None, meaning that solvent will not be"
            "queried.",
        ),
        lot_solvent: Optional[str] = Query(
            None,
            description="String representing the combination of level of theory and solvent. Default is None,"
            "meaning lot_solvent will not be queried.",
        ),
        _limit: int = Query(
            100, description="Maximum number of matches to show. Defaults to 100."
        ),
    ):
        self._limit = _limit
        self.level_of_theory = level_of_theory
        self.solvent = solvent
        self.lot_solvent = lot_solvent

        crit = dict()

        if self.level_of_theory:
            crit.update({"level_of_theory": level_of_theory})
        if self.solvent:
            crit.update({"solvent": solvent})
        if self.lot_solvent:
            crit.update({"lot_solvent": lot_solvent})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("level_of_theory", False), ("solvent", False), ("lot_solvent", False)]

    def post_process(self, docs, query):
        # TODO: should this be somehow sorted?
        response = docs[: self._limit]

        return response


class HashQuery(QueryOperator):
    """
    Method to generate a query based on the augmented graph hashes of the molecule
    """

    def query(
        self,
        species_hash: Optional[str] = Query(
            None, description="Graph hash augmented with node species"
        ),
        coord_hash: Optional[str] = Query(
            None, description="Graph hash augmented with node XYZ coordinates"
        ),
    ):
        crit = dict()

        if species_hash is not None:
            crit.update({"species_hash": species_hash})
        if coord_hash is not None:
            crit.update({"coord_hash": coord_hash})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("species_hash", False), ("coord_hash", False)]
