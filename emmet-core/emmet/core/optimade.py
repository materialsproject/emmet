import string
from datetime import datetime
from typing import Dict

from monty.fractions import gcd
from optimade.models import Species, StructureResourceAttributes
from pymatgen.core.composition import Composition, formula_double_format
from pymatgen.core.structure import Structure

from emmet.core.base import BaseModel, EmmetBaseModel
from emmet.core.mpid import MPID

letters = "ABCDEFGHIJKLMNOPQRSTUVXYZ"


def optimade_form(comp: Composition):

    symbols = sorted([str(e) for e in comp.keys()])
    numbers = set([comp[s] for s in symbols if comp[s]])

    reduced_form = []
    for s in symbols:
        reduced_form.append(s)
        if comp[s] != 1 and len(numbers) > 1:
            reduced_form.append(str(int(comp[s])))

    return "".join(reduced_form)


def optimade_anonymous_form(comp: Composition):

    reduced = comp.element_composition
    if all(x == int(x) for x in comp.values()):
        reduced /= gcd(*(int(i) for i in comp.values()))

    anon = []

    for e, amt in zip(string.ascii_uppercase, sorted(reduced.values(), reverse=True)):
        if amt == 1:
            amt_str = ""
        elif abs(amt % 1) < 1e-8:
            amt_str = str(int(amt))
        else:
            amt_str = str(amt)
        anon.append(str(e))
        anon.append(amt_str)
    return "".join(anon)


def hill_formula(comp: Composition) -> str:
    """
    :return: Hill formula. The Hill system (or Hill notation) is a system
    of writing empirical chemical formulas, molecular chemical formulas and
    components of a condensed formula such that the number of carbon atoms
    in a molecule is indicated first, the number of hydrogen atoms next,
    and then the number of all other chemical elements subsequently, in
    alphabetical order of the chemical symbols. When the formula contains
    no carbon, all the elements, including hydrogen, are listed
    alphabetically.
    """
    c = comp.element_composition
    elements = sorted([el.symbol for el in c.keys()])

    form_elements = []
    if "C" in elements:
        form_elements.append("C")
        if "H" in elements:
            form_elements.append("H")

        form_elements.extend([el for el in elements if el != "C" and el != "H"])
    else:
        form_elements = elements

    formula = [
        "%s%s" % (el, formula_double_format(c[el]) if c[el] != 1 else "")
        for el in form_elements
    ]
    return "".join(formula)


class OptimadeMaterialsDoc(StructureResourceAttributes, EmmetBaseModel):
    """Optimade Structure resource with a few extra MP specific fields for materials"""

    material_id: MPID
    _mp_chemical_system: str

    @classmethod
    def from_structure(
        cls, structure: Structure, material_id: MPID, last_updated: datetime, **kwargs
    ) -> StructureResourceAttributes:

        structure.remove_oxidation_states()
        return OptimadeMaterialsDoc(
            material_id=material_id,
            _mp_chemical_system=structure.composition.chemical_system,
            elements=sorted(set([e.symbol for e in structure.composition.elements])),
            nelements=len(structure.composition.elements),
            elements_ratios=list(structure.composition.fractional_composition.values()),
            chemical_formula_descriptive=optimade_form(structure.composition),
            chemical_formula_reduced=optimade_form(
                structure.composition.get_reduced_composition_and_factor()[0]
            ),
            chemical_formula_anonymous=optimade_anonymous_form(structure.composition),
            chemical_formula_hill=hill_formula(structure.composition),
            dimension_types=[1, 1, 1],
            nperiodic_dimensions=3,
            lattice_vectors=structure.lattice.matrix.tolist(),
            cartesian_site_positions=[site.coords.tolist() for site in structure],
            nsites=len(structure),
            species=list(
                {
                    site.species_string: Species(
                        chemical_symbols=[site.species_string],
                        concentration=[1.0],
                        name=site.species_string,
                    )
                    for site in structure
                }.values()
            ),
            species_at_sites=[site.species_string for site in structure],
            last_modified=last_updated,
            structure_features=[],
            **kwargs
        )
