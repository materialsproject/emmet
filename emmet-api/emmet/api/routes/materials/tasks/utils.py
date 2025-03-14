from typing import List, Dict

from fastapi import HTTPException
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.core import Structure, Composition
from pymatgen.core.periodic_table import DummySpecies
from pymatgen.core.trajectory import Trajectory
from pymatgen.entries.computed_entries import ComputedStructureEntry


def calcs_reversed_to_trajectory(calcs_reversed: List[dict]):
    """
    Converts data from calc_reversed to pymatgen Trajectory objects
    that contain structure, energy, force and stress data for each
    ionic step.

    Args:
        calcs_reversed: List of dictionaries in calcs_reversed entry
            of a task document.
    """
    trajectories = []

    for calculation in calcs_reversed:
        structures = []
        frame_props = []

        steps = calculation.get("output", {}).get("ionic_steps", None)

        if steps is None:
            raise HTTPException(
                status_code=404, detail="No ionic step data found for task"
            )
        else:
            for step in steps:
                step_dict = {}

                structure_dict = step.get("structure", None)

                if structure_dict is not None:
                    structure = Structure.from_dict(structure_dict)

                structures.append(structure)

                step_dict["e_fr_energy"] = step.get("e_fr_energy", None)
                step_dict["e_wo_entrp"] = step.get("e_wo_entrp", None)
                step_dict["e_0_energy"] = step.get("e_0_energy", None)
                step_dict["forces"] = step.get("forces", None)
                step_dict["stresses"] = step.get("stress", None)
                step_dict["electronic_steps"] = step.get("electronic_steps", None)

                frame_props.append(step_dict)

            traj = Trajectory.from_structures(
                structures, frame_properties=frame_props, time_step=None
            ).as_dict()
            trajectories.append(traj)

    return trajectories


def task_to_entry(doc: dict, include_structure: bool = True):
    """Turns a Task Doc into a ComputedStructureEntry"""

    input = doc.get("input", None)
    output = doc.get("output", None)

    try:
        output_struct = Structure.from_dict(output["structure"])

        entry_dict = {
            "correction": 0.0,
            "entry_id": doc["task_id"],
            "composition": output_struct.composition,
            "energy": output.get("energy", None),
            "parameters": {
                "potcar_spec": input.get("potcar_spec", None),
                "is_hubbard": input.get("is_hubbard", None),
                "hubbards": input.get("hubbards", None),
                "run_type": str(doc["run_type"]) if "run_type" in doc else None,
                "task_type": str(doc["task_type"]) if "task_type" in doc else None,
            },
            "data": {
                "oxide_type": oxide_type(output_struct),
                "aspherical": input.get("parameters", {}).get("LASPH", False),
                "last_updated": doc["last_updated"] if "last_updated" in doc else None,
                "completed_at": doc["completed_at"] if "completed_at" in doc else None,
            },
            "structure": output_struct,
        }

        return ComputedStructureEntry.from_dict(entry_dict).as_dict()

    except (AttributeError, KeyError, TypeError):
        return "Problem obtaining entry for {}. It might be missing necessary output structure information.".format(
            doc["task_id"]
        )


def chemsys_to_search(chemsys: str) -> Dict:
    """
    Converts a chemsys string to a search query

    Args:
        chemsys:A comma delimited string list of chemical systems
            with wildcards in it for unknown elements

    Returns:
        A dictionary representing a search query
    """
    crit = {}

    chemsys_list = [chemsys_val.strip() for chemsys_val in chemsys.split(",")]

    if "*" in chemsys:
        if len(chemsys_list) > 1:
            raise HTTPException(
                status_code=400,
                detail="Wild cards only supported for single chemsys queries.",
            )
        else:
            eles = chemsys_list[0].split("-")

            crit["equals"] = {"path": "nelements", "value": len(eles)}

            crit["exists"] = []
            for el in eles:
                if el != "*":
                    crit["exists"].append({"path": f"composition_reduced.{el}"})

            return crit
    else:
        query_vals = []
        for chemsys_val in chemsys_list:
            eles = chemsys_val.split("-")
            sorted_chemsys = "-".join(sorted(eles))
            query_vals.append(sorted_chemsys)
        if len(query_vals) == 1:
            crit = {"equals": {"path": "chemsys", "value": query_vals[0]}}
        else:
            crit = {"in": {"path": "chemsys", "value": query_vals}}
    return crit


def formula_to_search(formulas: str) -> Dict:
    """
    Santizes formula into a dictionary to search with wild cards

    Arguments:
        formula: formula with wildcards in it for unknown elements

    Returns:
        Mongo style search criteria for this formula
    """
    dummies = "AEGJLMQRXZ"

    formula_list = [formula.strip() for formula in formulas.split(",")]
    crit = dict()
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
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Problem processing formula with wild cards.",
                )

            comp = Composition(integer_formula).reduced_composition
            crit["equals"] = []
            crit["equals"].append(
                {"path": "formula_anonymous", "value": comp.anonymized_formula}
            )
            real_elts = [
                str(e)
                for e in comp.elements
                if e.as_dict().get("element", "A") not in dummies
            ]

            for el, n in comp.to_reduced_dict.items():
                if el in real_elts:
                    crit["equals"].append(
                        {"path": f"composition_reduced.{el}", "value": n}
                    )

            return crit

    else:
        try:
            composition_list = [Composition(formula) for formula in formula_list]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Problem processing one or more provided formulas.",
            )

        if any(
            isinstance(el, DummySpecies) for comp in composition_list for el in comp
        ):
            # Assume fully anonymized formula
            if len(formula_list) == 1:
                crit["equals"] = {
                    "path": "formula_anonymous",
                    "value": composition_list[0].anonymized_formula,
                }
            else:
                for comp in composition_list:
                    crit["equals"].append(
                        {"path": "formula_anonymous", "value": comp.anonymized_formula}
                    )
            return crit

        else:
            crit["in"] = {
                "path": "formula_pretty",
                "value": [comp.reduced_formula for comp in composition_list],
            }
        return crit
