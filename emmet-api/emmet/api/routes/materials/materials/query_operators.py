from itertools import permutations
from typing import Literal, Any

from fastapi import Body, HTTPException, Query
from emmet.api.query_operator import QueryOperator
from emmet.api.utils import STORE_PARAMS
from pymatgen.analysis.structure_matcher import ElementComparator, StructureMatcher
from pymatgen.core.composition import Composition, CompositionError
from pymatgen.core.periodic_table import Element
from pymatgen.core.structure import Structure

from emmet.api.routes.materials.materials.utils import (
    chemsys_to_criteria,
    formula_to_criteria,
)
from emmet.core.symmetry import CrystalSystem
from emmet.core.vasp.calc_types import RunType
from emmet.core.vasp.material import BlessedCalcs

BLESSED_CALC_RUN_TYPES = sorted(BlessedCalcs.model_fields)


class FormulaQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        formula or chemical system with wild cards.
    """

    def query(
        self,
        formula: str | None = Query(
            None,
            description="Query by formula including anonymized formula or by including wild cards. \
A comma delimited string list of anonymous formulas or regular formulas can also be provided.",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if formula:
            crit.update(formula_to_criteria(formula))

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = ["formula_pretty", "formula_anonymous", "composition_reduced"]
        return [(key, False) for key in keys]


class ChemsysQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        chemical system with wild cards.
    """

    def query(
        self,
        chemsys: str | None = Query(
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
        elements: str | None = Query(
            None,
            description="Query by elements in the material composition as a comma-separated list",
            max_length=60,
        ),
        exclude_elements: str | None = Query(
            None,
            description="Query by excluded elements in the material composition as a comma-separated list",
            max_length=60,
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if elements:
            try:
                element_list = [Element(e) for e in elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )

            for el in element_list:
                crit[f"composition_reduced.{el}"] = {"$exists": True}

        if exclude_elements:
            try:
                element_list = [Element(e) for e in exclude_elements.strip().split(",")]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Please provide a comma-seperated list of elements",
                )

            for el in element_list:
                crit[f"composition_reduced.{el}"] = {"$exists": False}

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("elements", False)]


class DeprecationQuery(QueryOperator):
    """
    Method to generate a deprecation state query
    """

    def query(
        self,
        deprecated: bool | None = Query(
            False,
            description="Whether the material is marked as deprecated",
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if deprecated is not None:
            crit.update({"deprecated": deprecated})

        return {"criteria": crit}


class SymmetryQuery(QueryOperator):
    """
    Method to generate a query on symmetry information
    """

    def query(
        self,
        crystal_system: CrystalSystem | None = Query(
            None,
            description="Crystal system of the material",
        ),
        spacegroup_number: int | None = Query(
            None,
            description="Space group number of the material",
        ),
        spacegroup_symbol: str | None = Query(
            None,
            description="Space group symbol of the material",
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if crystal_system:
            crit.update({"symmetry.crystal_system": str(crystal_system.value)})

        if spacegroup_number:
            crit.update({"symmetry.number": spacegroup_number})

        if spacegroup_symbol:
            crit.update({"symmetry.symbol": spacegroup_symbol})

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        keys = ["symmetry.crystal_system", "symmetry.number", "symmetry.symbol"]
        return [(key, False) for key in keys]


class MultiTaskIDQuery(QueryOperator):
    """
    Method to generate a query for different task_ids
    """

    def query(
        self,
        task_ids: str | None = Query(
            None, description="Comma-separated list of task_ids to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}

        if task_ids:
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


class BlessedCalcsQuery(QueryOperator):
    """
    Method to generate a query for nested blessed calculation data
    """

    def query(
        self,
        run_type: Literal[*BLESSED_CALC_RUN_TYPES] | RunType = Query(  # type: ignore[valid-type]
            ..., description="Calculation run type of blessed task data"
        ),
        energy_min: float | None = Query(
            None, description="Minimum total uncorrected DFT energy in eV/atom"
        ),
        energy_max: float | None = Query(
            None, description="Maximum total uncorrected DFT energy in eV/atom"
        ),
    ) -> STORE_PARAMS:

        parsed_run_type: str | None = None
        if isinstance(run_type, RunType):
            aliases = {
                RunType.PBE: "GGA",
                RunType.PBE_U: "GGA_U",
                RunType.GGA: "GGA",
                RunType.GGA_U: "GGA_U",
                RunType.SCAN: "SCAN",
                RunType.r2SCAN: "R2SCAN",
                RunType.HSE06: "HSE",
            }
            parsed_run_type = aliases.get(run_type)

        elif run_type in BLESSED_CALC_RUN_TYPES:
            parsed_run_type = run_type

        if parsed_run_type is None:
            raise ValueError(
                f"Unsupported {run_type=}, please choose one of "
                f"{', '.join(BLESSED_CALC_RUN_TYPES)}"
            )

        crit: dict[str, Any] = {f"entries.{parsed_run_type}.energy": {}}

        if energy_min is not None:
            crit[f"entries.{parsed_run_type}.energy"].update({"$gte": energy_min})

        if energy_max is not None:
            crit[f"entries.{parsed_run_type}.energy"].update({"$lte": energy_max})

        if not crit[f"entries.{parsed_run_type}.energy"]:
            return {"criteria": {f"entries.{parsed_run_type}": {"$ne": None}}}

        return {"criteria": crit}

    def post_process(self, docs, query):
        """Return only the blessed entry."""
        run_type = list(query["criteria"].keys())[0].split(".")[1]

        return_data = [
            {
                "material_id": doc["material_id"],
                "entries": {run_type: doc["entries"][run_type]},
            }
            for doc in docs
        ]

        return return_data


class MultiMaterialIDQuery(QueryOperator):
    """
    Method to generate a query for different root-level material_id values
    """

    def query(
        self,
        material_ids: str | None = Query(
            None, description="Comma-separated list of material_id values to query on"
        ),
    ) -> STORE_PARAMS:
        crit = {}  # type: dict

        if material_ids:
            mpids_list = [
                material_id.strip() for material_id in material_ids.split(",")
            ]

            if len(mpids_list) == 1:
                crit.update({"material_id": mpids_list[0]})
            else:
                crit.update({"material_id": {"$in": mpids_list}})

        return {"criteria": crit}


class FindStructureQuery(QueryOperator):
    """
    Method to generate a find structure query
    """

    def query(
        self,
        structure: dict = Body(
            ...,
            description="Dictionary representaion of Pymatgen structure object to query with",
        ),
        ltol: float = Query(
            0.2,
            description="Fractional length tolerance. Default is 0.2.",
        ),
        stol: float = Query(
            0.3,
            description="Site tolerance. Defined as the fraction of the average free \
                    length per atom := ( V / Nsites ) ** (1/3). Default is 0.3.",
        ),
        angle_tol: float = Query(
            5,
            description="Angle tolerance in degrees. Default is 5 degrees.",
        ),
        _limit: int = Query(
            1,
            description="Maximum number of matches to show. Defaults to 1, only showing the best match.",
        ),
    ) -> STORE_PARAMS:
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self._limit = _limit
        self.structure = structure

        crit = {}

        try:
            s = Structure.from_dict(structure)
        except Exception:
            raise HTTPException(
                status_code=404,
                detail="Body cannot be converted to a pymatgen structure object.",
            )

        crit.update({"composition_reduced": dict(s.composition.to_reduced_dict)})

        return {"criteria": crit}

    def post_process(self, docs, query):
        s1 = Structure.from_dict(self.structure)

        m = StructureMatcher(
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
            primitive_cell=True,
            scale=True,
            attempt_supercell=False,
            comparator=ElementComparator(),
        )

        matches = []

        for doc in docs:
            s2 = Structure.from_dict(doc["structure"])
            matched = m.fit(s1, s2)

            if matched:
                rms = m.get_rms_dist(s1, s2)

                matches.append(
                    {
                        "material_id": doc["material_id"],
                        "normalized_rms_displacement": rms[0],
                        "max_distance_paired_sites": rms[1],
                    }
                )

        response = sorted(
            matches[: self._limit],
            key=lambda x: (
                x["normalized_rms_displacement"],
                x["max_distance_paired_sites"],
            ),
        )

        return response

    def ensure_indexes(self):  # pragma: no cover
        return [("composition_reduced", False)]


class FormulaAutoCompleteQuery(QueryOperator):
    """
    Method to generate a formula autocomplete query
    """

    def query(
        self,
        formula: str = Query(
            ...,
            description="Human readable chemical formula.",
        ),
        limit: int = Query(
            10,
            description="Maximum number of matches to show. Defaults to 10.",
        ),
    ) -> STORE_PARAMS:
        self.formula = formula
        self.limit = limit

        try:
            comp = Composition(formula)
        except (CompositionError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid formula provided.",
            )

        ind_str = []
        eles = []

        if len(comp) == 1:
            d = comp.get_integer_formula_and_factor()

            s = d[0] + str(int(d[1])) if d[1] != 1 else d[0]

            ind_str.append(s)
            eles.append(d[0])
        else:
            comp_red = comp.reduced_composition.items()

            for i, j in comp_red:
                # The keys of pymatgen's Composition can be Element, Species, or DummySpecies
                # Element and Species both have a name attr, DummySpecies doesn't by default
                # This bothers mypy a lot, so we placate it here - all three have __str__ methods:
                spec_name = str(getattr(i, "name", None) or i)
                if j != 1:
                    ind_str.append(spec_name + str(int(j)))
                else:
                    ind_str.append(spec_name)

                eles.append(spec_name)

        final_terms = ["".join(entry) for entry in permutations(ind_str)]

        pipeline = [
            {
                "$search": {
                    "index": "formula_autocomplete",
                    "text": {"path": "formula_pretty", "query": final_terms},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "formula_pretty": 1,
                    "elements": 1,
                    "length": {"$strLenCP": "$formula_pretty"},
                }
            },
            {
                "$match": {
                    "length": {"$gte": len(final_terms[0])},
                    "elements": {"$all": eles},
                }
            },
            {"$limit": limit},
            {"$sort": {"length": 1}},
            {"$project": {"elements": 0, "length": 0}},
        ]

        return {"pipeline": pipeline}

    def ensure_indexes(self):  # pragma: no cover
        return [("formula_pretty", False)]


class LicenseQuery(QueryOperator):
    """
    Factory method to generate a dependency for querying by
        license information in builder meta
    """

    def query(
        self,
        license: Literal["BY-C", "BY-NC", "All"] | None = Query(
            "BY-C",
            description="Query by license. Can be commercial or non-commercial, or both",
        ),
    ) -> STORE_PARAMS:
        q = {"$in": ["BY-C", "BY-NC"]} if license == "All" else license
        return {"criteria": {"builder_meta.license": q}}


class BatchIdQuery(QueryOperator):
    """Method to generate a query on batch_id"""

    def __init__(self, field="builder_meta.batch_id"):
        self._field = field

    def query(
        self,
        batch_id: str | None = Query(
            None,
            description="Query by batch identifier",
        ),
        batch_id_not_eq: str | None = Query(
            None,
            description="Exclude batch identifier",
        ),
        batch_id_eq_any: str | None = Query(
            None,
            description="Query by a comma-separated list of batch identifiers",
        ),
        batch_id_neq_any: str | None = Query(
            None,
            description="Exclude a comma-separated list of batch identifiers",
        ),
    ) -> STORE_PARAMS:
        # NOTE: maggma's StringQueryOperator doesn't work for nested fields?
        all_kwargs = [batch_id, batch_id_not_eq, batch_id_eq_any, batch_id_neq_any]
        if sum(bool(kwarg) for kwarg in all_kwargs) > 1:
            raise HTTPException(
                status_code=400,
                detail="Please only choose one of `batch_id` parameters to filter.",
            )

        crit = {}  # type: dict
        k = self._field
        if batch_id:
            crit[k] = batch_id
        elif batch_id_not_eq:
            crit[k] = {"$ne": batch_id_not_eq}
        elif batch_id_eq_any or batch_id_neq_any:
            value = batch_id_eq_any if batch_id_eq_any else batch_id_neq_any
            batch_ids = [batch_id.strip() for batch_id in value.split(",")]  # type: ignore
            if len(batch_ids) > 1:
                crit[k] = {"$in" if batch_id_eq_any else "$nin": batch_ids}
            else:
                crit[k] = batch_ids[0] if batch_id_eq_any else {"$ne": batch_ids[0]}

        return {"criteria": crit}

    def ensure_indexes(self):  # pragma: no cover
        return [("builder_meta.batch_id", False)]
