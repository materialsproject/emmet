import re
from datetime import datetime
from typing import List, Union, Dict, Optional
from collections import defaultdict

from emmet.core.utils import ValueEnum

from monty.json import MontyDecoder
from pydantic import field_validator, BaseModel, Field
from pymatgen.apps.battery.battery_abc import AbstractElectrode
from pymatgen.apps.battery.conversion_battery import ConversionElectrode
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.analysis.phase_diagram import PhaseDiagram
from pymatgen.core import Composition, Structure
from pymatgen.core.periodic_table import Element
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry

from emmet.core.mpid import MPID


class BatteryType(str, ValueEnum):
    """
    Enum for battery type
    """

    insertion = "insertion"
    conversion = "conversion"


class VoltagePairDoc(BaseModel):
    """
    Data for individual voltage steps.
    Note: Each voltage step is represented as a sub_electrode (ConversionElectrode/InsertionElectrode)
        object to gain access to some basic statistics about the voltage step
    """

    formula_charge: Optional[str] = Field(
        None, description="The chemical formula of the charged material."
    )

    formula_discharge: Optional[str] = Field(
        None, description="The chemical formula of the discharged material."
    )

    max_delta_volume: Optional[float] = Field(
        None,
        description="Volume changes in % for a particular voltage step using: "
        "max(charge, discharge) / min(charge, discharge) - 1.",
    )

    average_voltage: Optional[float] = Field(
        None, description="The average voltage in V for a particular voltage step."
    )

    capacity_grav: Optional[float] = Field(
        None, description="Gravimetric capacity in mAh/g."
    )

    capacity_vol: Optional[float] = Field(
        None, description="Volumetric capacity in mAh/cc."
    )

    energy_grav: Optional[float] = Field(
        None, description="Gravimetric energy (Specific energy) in Wh/kg."
    )

    energy_vol: Optional[float] = Field(
        None, description="Volumetric energy (Energy Density) in Wh/l."
    )

    fracA_charge: Optional[float] = Field(
        None, description="Atomic fraction of the working ion in the charged state."
    )

    fracA_discharge: Optional[float] = Field(
        None, description="Atomic fraction of the working ion in the discharged state."
    )

    @classmethod
    def from_sub_electrode(cls, sub_electrode: AbstractElectrode, **kwargs):
        """
        Convert a pymatgen electrode object to a document
        """
        return cls(**sub_electrode.get_summary_dict(), **kwargs)


class InsertionVoltagePairDoc(VoltagePairDoc):
    """
    Features specific to insertion electrode
    """

    stability_charge: Optional[float] = Field(
        None, description="The energy above hull of the charged material in eV/atom."
    )

    stability_discharge: Optional[float] = Field(
        None, description="The energy above hull of the discharged material in eV/atom."
    )

    id_charge: Optional[Union[MPID, int, None]] = Field(
        None, description="The Materials Project ID of the charged structure."
    )

    id_discharge: Optional[Union[MPID, int, None]] = Field(
        None, description="The Materials Project ID of the discharged structure."
    )


class ConversionVoltagePairDoc(VoltagePairDoc):
    """
    Features specific to conversion electrode
    """

    reaction: Optional[dict] = Field(
        None,
        description="The reaction that characterizes that particular voltage step.",
    )


class EntriesCompositionSummary(BaseModel):
    """
    Composition summary data for all material entries associated with this electrode.
    Included to enable better searching via the API.
    """

    all_formulas: Optional[List[str]] = Field(
        None,
        description="Reduced formulas for material entries across all voltage pairs.",
    )

    all_chemsys: Optional[List[str]] = Field(
        None,
        description="Chemical systems for material entries across all voltage pairs.",
    )

    all_formula_anonymous: Optional[List[str]] = Field(
        None,
        description="Anonymous formulas for material entries across all voltage pairs.",
    )

    all_elements: Optional[List[Element]] = Field(
        None,
        description="Elements in material entries across all voltage pairs.",
    )

    all_composition_reduced: Optional[Dict] = Field(
        None,
        description="Composition reduced data for entries across all voltage pairs.",
    )

    @classmethod
    def from_compositions(cls, compositions: List[Composition]):
        all_formulas = list({comp.reduced_formula for comp in compositions})
        all_chemsys = list({comp.chemical_system for comp in compositions})
        all_formula_anonymous = list({comp.anonymized_formula for comp in compositions})
        all_elements = sorted(compositions)[-1].elements

        all_composition_reduced = defaultdict(set)

        for comp in compositions:
            comp_red = comp.get_reduced_composition_and_factor()[0].as_dict()

            for ele, num in comp_red.items():
                all_composition_reduced[ele].add(num)

        return cls(
            all_formulas=all_formulas,
            all_chemsys=all_chemsys,
            all_formula_anonymous=all_formula_anonymous,
            all_elements=all_elements,
            all_composition_reduced=all_composition_reduced,
        )


class BaseElectrode(BaseModel):
    battery_type: Optional[BatteryType] = Field(
        None, description="The type of battery (insertion or conversion)."
    )

    battery_id: Optional[str] = Field(
        None,
        description="The id for this battery document is the numerically smallest material_id followed by "
        "the working ion.",
    )

    thermo_type: Optional[str] = Field(
        None,
        description="The functional type used to compute the thermodynamics of this electrode document.",
    )

    battery_formula: Optional[str] = Field(
        None,
        description="Reduced formula with working ion range produced by combining the charge and discharge formulas.",
    )

    working_ion: Optional[Element] = Field(
        None, description="The working ion as an Element object."
    )

    num_steps: Optional[int] = Field(
        None,
        description="The number of distinct voltage steps in from fully charge to "
        "discharge based on the stable intermediate states.",
    )

    max_voltage_step: Optional[float] = Field(
        None, description="Maximum absolute difference in adjacent voltage steps."
    )

    last_updated: Optional[datetime] = Field(
        None,
        description="Timestamp for the most recent calculation for this Material document.",
    )

    framework: Optional[Composition] = Field(
        None, description="The chemical compositions of the host framework."
    )

    framework_formula: Optional[str] = Field(
        None, description="The id for this battery document."
    )

    elements: Optional[List[Element]] = Field(
        None,
        description="The atomic species contained in this electrode (not including the working ion).",
    )

    nelements: Optional[int] = Field(
        None,
        description="The number of elements in the material (not including the working ion).",
    )

    chemsys: Optional[str] = Field(
        None,
        description="The chemical system this electrode belongs to (not including the working ion).",
    )

    formula_anonymous: Optional[str] = Field(
        None,
        title="Anonymous Formula",
        description="Anonymized representation of the formula (not including the working ion).",
    )

    warnings: List[str] = Field(
        [], description="Any warnings related to this electrode data."
    )

    # Make sure that the datetime field is properly formatted
    @field_validator("last_updated", mode="before")
    @classmethod
    def last_updated_dict_ok(cls, v):
        return MontyDecoder().process_decoded(v)


class InsertionElectrodeDoc(InsertionVoltagePairDoc, BaseElectrode):
    """
    Insertion electrode
    """

    host_structure: Optional[Structure] = Field(
        None, description="Host structure (structure without the working ion)."
    )

    adj_pairs: Optional[List[InsertionVoltagePairDoc]] = Field(
        None, description="Returns all of the voltage steps material pairs."
    )

    material_ids: Optional[List[MPID]] = Field(
        None,
        description="The ids of all structures that matched to the present host lattice, regardless of stability. "
        "The stable entries can be found in the adjacent pairs.",
    )

    entries_composition_summary: Optional[EntriesCompositionSummary] = Field(
        None,
        description="Composition summary data for all material in entries across all voltage pairs.",
    )

    electrode_object: Optional[InsertionElectrode] = Field(
        None, description="The Pymatgen electrode object."
    )

    @classmethod
    def from_entries(
        cls,
        grouped_entries: List[ComputedStructureEntry],
        working_ion_entry: ComputedEntry,
        battery_id: str,
        strip_structures: bool = False,
    ) -> Union["InsertionElectrodeDoc", None]:
        try:
            ie = InsertionElectrode.from_entries(
                entries=grouped_entries,
                working_ion_entry=working_ion_entry,
                strip_structures=strip_structures,
            )
        except IndexError:
            return None

        d = cls.get_elec_doc(ie)
        d["last_updated"] = datetime.utcnow()

        stripped_host = ie.fully_charged_entry.structure.copy()
        stripped_host.remove_species([d["working_ion"]])
        elements = stripped_host.composition.elements
        chemsys = stripped_host.composition.chemical_system
        framework = Composition(d["framework_formula"])
        dchg_comp = Composition(d["formula_discharge"])
        battery_formula = get_battery_formula(
            Composition(d["formula_charge"]),
            dchg_comp,
            ie.working_ion,
        )

        compositions = []
        for doc in d["adj_pairs"]:
            compositions.append(Composition(doc["formula_charge"]))
            compositions.append(Composition(doc["formula_discharge"]))

        entries_composition_summary = EntriesCompositionSummary.from_compositions(
            compositions
        )

        # Check if more than one working ion per transition metal and warn
        warnings = []
        if any([element.is_transition_metal for element in dchg_comp]):
            transition_metal_fraction = sum(
                [
                    dchg_comp.get_atomic_fraction(elem)
                    for elem in dchg_comp
                    if elem.is_transition_metal
                ]
            )
            if (
                dchg_comp.get_atomic_fraction(ie.working_ion)
                / transition_metal_fraction
                > 1.0
            ):
                warnings.append("More than one working ion per transition metal")
        else:
            warnings.append("Transition metal not found")

        return cls(
            battery_type="insertion",  # type: ignore
            battery_id=battery_id,
            host_structure=stripped_host.as_dict(),
            framework=framework,
            battery_formula=battery_formula,
            electrode_object=ie.as_dict(),
            elements=elements,
            nelements=len(elements),
            chemsys=chemsys,
            formula_anonymous=framework.anonymized_formula,
            entries_composition_summary=entries_composition_summary,
            warnings=warnings,
            **d,
        )

    @staticmethod
    def get_elec_doc(ie: InsertionElectrode) -> dict:
        """
        Gets a summary doc for an InsertionElectrode object.
        Similar to InsertionElectrode.get_summary_dict() with modifications specific
        to the Materials Project.
        Args:
            ie (pymatgen InsertionElectrode): electrode_object
        Returns:
            summary doc
        """
        entries = ie.get_all_entries()

        def get_dict_from_elec(ie):
            d = {
                "average_voltage": ie.get_average_voltage(),
                "max_voltage": ie.max_voltage,
                "min_voltage": ie.min_voltage,
                "max_delta_volume": ie.max_delta_volume,
                "max_voltage_step": ie.max_voltage_step,
                "capacity_grav": ie.get_capacity_grav(),
                "capacity_vol": ie.get_capacity_vol(),
                "energy_grav": ie.get_specific_energy(),
                "energy_vol": ie.get_energy_density(),
                "working_ion": ie.working_ion.symbol,
                "num_steps": ie.num_steps,
                "fracA_charge": ie.voltage_pairs[0].frac_charge,
                "fracA_discharge": ie.voltage_pairs[-1].frac_discharge,
                "framework_formula": ie.framework_formula,
                "id_charge": ie.fully_charged_entry.data["material_id"],
                "formula_charge": ie.fully_charged_entry.composition.reduced_formula,
                "id_discharge": ie.fully_discharged_entry.data["material_id"],
                "formula_discharge": ie.fully_discharged_entry.composition.reduced_formula,
                "max_instability": ie.get_max_instability(),
                "min_instability": ie.get_min_instability(),
                "material_ids": [itr_ent.data["material_id"] for itr_ent in entries],
                "stable_material_ids": [
                    itr_ent.data["material_id"] for itr_ent in ie.get_stable_entries()
                ],
                "unstable_material_ids": [
                    itr_ent.data["material_id"] for itr_ent in ie.get_unstable_entries()
                ],
            }

            if all("decomposition_energy" in e.data for e in entries):
                thermo_data = {
                    "stability_charge": ie.fully_charged_entry.data[
                        "decomposition_energy"
                    ],
                    "stability_discharge": ie.fully_discharged_entry.data[
                        "decomposition_energy"
                    ],
                    "stability_data": {
                        e.entry_id: e.data["decomposition_energy"] for e in entries
                    },
                }
            else:
                thermo_data = {
                    "stability_charge": None,
                    "stability_discharge": None,
                    "stability_data": {},
                }
            d.update(thermo_data)

            return d

        d = get_dict_from_elec(ie)

        d["adj_pairs"] = list(
            map(get_dict_from_elec, ie.get_sub_electrodes(adjacent_only=True))
        )

        return d


class ConversionElectrodeDoc(ConversionVoltagePairDoc, BaseElectrode):
    """
    Conversion electrode
    """

    initial_comp_formula: Optional[str] = Field(
        None,
        description="The starting composition for the ConversionElectrode represented as a string/formula.",
    )

    adj_pairs: Optional[List[ConversionVoltagePairDoc]] = Field(
        None, description="Returns all of the voltage steps material pairs."
    )

    electrode_object: Optional[ConversionElectrode] = Field(
        None, description="The Pymatgen conversion electrode object."
    )

    @classmethod
    def from_composition_and_entries(
        cls,
        composition: Composition,
        entries: List[ComputedEntry],
        working_ion_symbol: str,
        battery_id: str,
        thermo_type: str,
    ):
        ce = ConversionElectrode.from_composition_and_entries(
            comp=composition,
            entries_in_chemsys=entries,
            working_ion_symbol=working_ion_symbol,
        )
        d = cls.get_conversion_elec_doc(ce)
        return cls(battery_id=battery_id, thermo_type=thermo_type, **d)

    @classmethod
    def from_composition_and_pd(
        cls,
        comp: Composition,
        pd: PhaseDiagram,
        working_ion_symbol: str,
        battery_id: str,
        thermo_type: str,
    ):
        ce = ConversionElectrode.from_composition_and_pd(
            comp=comp, pd=pd, working_ion_symbol=working_ion_symbol
        )
        d = cls.get_conversion_elec_doc(ce)
        return cls(battery_id=battery_id, thermo_type=thermo_type, **d)

    @staticmethod
    def get_conversion_elec_doc(ce: ConversionElectrode) -> dict:
        """
        Gets a summary doc for a ConversionElectrode object.
        Args:
            ie (pymatgen ConversionElectrode): electrode_object
        Returns:
            summary doc
        """

        def get_dict_from_conversion_elec(ce):
            fracA_charge = ce.voltage_pairs[0].frac_charge
            fracA_discharge = ce.voltage_pairs[-1].frac_discharge
            x_charge = fracA_charge * ce.framework.num_atoms / (1 - fracA_charge)
            x_discharge = (
                fracA_discharge * ce.framework.num_atoms / (1 - fracA_discharge)
            )
            comp_charge = ce.framework + {ce.working_ion.symbol: x_charge}
            comp_discharge = ce.framework + {ce.working_ion.symbol: x_discharge}

            battery_formula = get_battery_formula(
                comp_charge,
                comp_discharge,
                ce.working_ion,
            )

            d = {
                "battery_type": "conversion",
                "battery_formula": battery_formula,
                "framework": ce.framework,
                "framework_formula": ce.framework_formula,
                "initial_comp_formula": ce.initial_comp_formula,
                "chemsys": ce.framework.chemical_system,
                "elements": ce.framework.elements,
                "nelements": len(ce.framework.elements),
                "formula_anonymous": ce.framework.anonymized_formula,
                "electrode_object": ce.as_dict(),
                "average_voltage": ce.get_average_voltage(),
                "max_voltage": ce.max_voltage,
                "min_voltage": ce.min_voltage,
                "max_delta_volume": ce.max_delta_volume,
                "max_voltage_step": ce.max_voltage_step,
                "capacity_grav": ce.get_capacity_grav(),
                "capacity_vol": ce.get_capacity_vol(),
                "energy_grav": ce.get_specific_energy(),
                "energy_vol": ce.get_energy_density(),
                "working_ion": ce.working_ion.symbol,
                "num_steps": ce.num_steps,
                "fracA_charge": fracA_charge,
                "fracA_discharge": fracA_discharge,
                "formula_charge": comp_charge.reduced_formula,
                "formula_discharge": comp_discharge.reduced_formula,
                "reaction": ce.voltage_pairs[0].rxn.as_dict(),
                "last_updated": datetime.utcnow(),
            }
            return d

        d = get_dict_from_conversion_elec(ce)

        d["adj_pairs"] = list(
            map(
                get_dict_from_conversion_elec, ce.get_sub_electrodes(adjacent_only=True)
            )
        )

        return d


def get_battery_formula(
    charge_comp: Composition, discharge_comp: Composition, working_ion: Element
):
    working_ion_subscripts = []

    for comp in [charge_comp, discharge_comp]:
        comp_dict = comp.get_el_amt_dict()

        working_ion_num = (
            comp_dict.pop(working_ion.value) if working_ion.value in comp_dict else 0
        )
        temp_comp = Composition.from_dict(comp_dict)

        (temp_reduced, n) = temp_comp.get_reduced_composition_and_factor()

        new_subscript = re.sub(".00$", "", "{:.2f}".format(working_ion_num / n))
        if new_subscript != "0":
            new_subscript = new_subscript.rstrip("0")

        working_ion_subscripts.append(new_subscript)

    return (
        working_ion.value
        + "-".join(working_ion_subscripts)
        + temp_reduced.reduced_formula
    )
