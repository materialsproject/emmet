from pymatgen.core import Composition
from pymatgen.core.periodic_table import DummySpecies
from typing import Dict
from fastapi import HTTPException


def electrodes_formula_to_criteria(formulas: str) -> Dict:
    """
    Santizes formula into a dictionary to search with wild cards
    over electrodes data

    Arguments:
        formula: formula with wildcards in it for unknown elements

    Returns:
        Mongo style search criteria for this formula
    """
    dummies = "ADEGJLMQRXZ"

    formula_list = [formula.strip() for formula in formulas.split(",")]

    if "*" in formulas:
        if len(formula_list) > 1:
            raise HTTPException(
                status_code=400,
                detail="Wild cards only supported for single formula queries.",
            )
        else:
            # Wild card in formula
            nstars = formulas.count("*")

            formula_dummies = formulas.replace("*", "{}").format(*dummies[:nstars])

            try:
                integer_formula = Composition(
                    formula_dummies
                ).get_integer_formula_and_factor()[0]
            except (ValueError, IndexError):
                raise HTTPException(
                    status_code=400,
                    detail="Problem processing one or more provided formulas.",
                )

            comp = Composition(integer_formula).reduced_composition
            crit = dict()  # type: dict
            crit[
                "entries_composition_summary.all_formula_anonymous"
            ] = comp.anonymized_formula

            real_elts = [
                str(e)
                for e in comp.elements
                if not e.as_dict().get("element", "A") in dummies
            ]

            for el, n in comp.to_reduced_dict.items():
                if el in real_elts:
                    crit[
                        f"entries_composition_summary.all_composition_reduced.{el}"
                    ] = n

            return crit

    else:
        try:
            if any(
                isinstance(el, DummySpecies)
                for formula in formula_list
                for el in Composition(formula)
            ):
                # Assume fully anonymized formula
                if len(formula_list) == 1:
                    return {
                        "entries_composition_summary.all_formula_anonymous": Composition(
                            formula_list[0]
                        ).anonymized_formula
                    }
                else:
                    return {
                        "entries_composition_summary.all_formula_anonymous": {
                            "$in": [
                                Composition(formula).anonymized_formula
                                for formula in formula_list
                            ]
                        }
                    }

            else:
                if len(formula_list) == 1:
                    comp = Composition(formula_list[0])
                    nele = len(comp)
                    # Paranoia below about floating-point "equality"
                    crit = {}
                    crit["nelements"] = {"$in": [nele, nele - 1]}  # type: ignore

                    for el, n in comp.to_reduced_dict.items():
                        crit[
                            f"entries_composition_summary.all_composition_reduced.{el}"
                        ] = n

                    return crit
                else:
                    return {
                        "entries_composition_summary.all_formulas": {
                            "$in": [
                                Composition(formula).reduced_formula
                                for formula in formula_list
                            ]
                        }
                    }
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=400,
                detail="Problem processing one or more provided formulas.",
            )


def electrodes_chemsys_to_criteria(chemsys: str) -> Dict:
    """
    Santizes chemsys into a dictionary to search with wild cards
    over electrodes data

    Arguments:
        chemsys: A comma delimited string list ofchemical systems
            with wildcards in it for unknown elements

    Returns:
        Mongo style search criteria for this formula
    """

    crit = {}  # type: dict

    chemsys_list = [chemsys_val.strip() for chemsys_val in chemsys.split(",")]

    if "*" in chemsys:
        if len(chemsys_list) > 1:
            raise HTTPException(
                status_code=400,
                detail="Wild cards only supported for single chemsys queries.",
            )
        else:
            eles = chemsys_list[0].split("-")
            neles = len(eles)

            crit["nelements"] = {"$in": [neles, neles - 1]}
            crit["entries_composition_summary.all_elements"] = {
                "$all": [ele for ele in eles if ele != "*"]
            }

            if crit["entries_composition_summary.all_elements"]["$all"] == []:
                del crit["entries_composition_summary.all_elements"]

            return crit
    else:
        query_vals = []
        for chemsys_val in chemsys_list:
            eles = chemsys_val.split("-")
            sorted_chemsys = "-".join(sorted(eles))
            query_vals.append(sorted_chemsys)

        if len(query_vals) == 1:
            crit["entries_composition_summary.all_chemsys"] = query_vals[0]
        else:
            crit["entries_composition_summary.all_chemsys"] = {"$in": query_vals}

        return crit
