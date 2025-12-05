import copy
import warnings

from pydantic import BaseModel, Field
from pymatgen.entries.compatibility import Compatibility

from emmet.builders.utils import HiddenPrints
from emmet.core.corrected_entries import CorrectedEntriesDoc
from emmet.core.thermo import ThermoType
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedStructureEntryType,
)


class CorrectedEntriesBuilderInput(BaseModel):
    entries: list[ComputedStructureEntryType] = Field(
        ...,
        description="""
        List of computed structure entries to apply corrections to.
        Entries MUST belong to a single chemical system (chemsys).
        """,
    )


def build_corrected_entries_doc(
    input: CorrectedEntriesBuilderInput,
    compatibilities: list[Compatibility | None] = [None],
) -> CorrectedEntriesDoc:
    """
    Process computed structure entries using corrections defined in pymatgen
    compatibility classes. Ensures compatibility of energies for entries for
    different thermodynamic hulls.

    Input entries must all belong to the same chemical system. Caller is
    responsible for constructing CorrectedEntriesBuilderInput instances within
    their data pipeline context.

    Args:
        input: CorrectedEntriesBuilderInput with an aggregated list of computed
            structure entries for a single chemical system.
        compatibilities: List of pymatgen compatibility classes to apply to
            input entries.

    Returns:
        CorrectedEntriesDoc: if no Compatibility class(es) are provided, and all
            entries have the same functional, no corrections will be applied and
            entries will simply be passed through to CorrectedEntriesDoc constructor.
    """
    all_entry_types = {str(e.data["run_type"]) for e in input.entries}

    elements = sorted(
        set([el.symbol for e in input.entries for el in e.composition.elements])
    )
    chemsys = "-".join(elements)

    corrected_entries = {}

    for compatibility in compatibilities:
        if compatibility is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with HiddenPrints():
                    if compatibility.name == "MP DFT mixing scheme":
                        thermo_type = ThermoType.GGA_GGA_U_R2SCAN

                        if "R2SCAN" in all_entry_types:
                            only_scan_pd_entries = [
                                e
                                for e in input.entries
                                if str(e.data["run_type"]) == "R2SCAN"
                            ]
                            corrected_entries["R2SCAN"] = only_scan_pd_entries

                            pd_entries = compatibility.process_entries(
                                copy.deepcopy(input.entries),
                                verbose=False,
                            )

                        else:
                            corrected_entries["R2SCAN"] = None
                            pd_entries = None

                    elif compatibility.name == "MP2020":
                        thermo_type = ThermoType.GGA_GGA_U
                        pd_entries = compatibility.process_entries(
                            copy.deepcopy(input.entries), verbose=False
                        )
                    else:
                        thermo_type = ThermoType.UNKNOWN
                        pd_entries = compatibility.process_entries(
                            copy.deepcopy(input.entries), verbose=False
                        )

                    corrected_entries[str(thermo_type)] = pd_entries

        else:
            if len(all_entry_types) > 1:
                # TODO: logging over raising
                raise ValueError(
                    "More than one functional type has been provided without a mixing scheme!"
                )
            else:
                thermo_type = all_entry_types.pop()

            corrected_entries[str(thermo_type)] = copy.deepcopy(input.entries)

    return CorrectedEntriesDoc(chemsys=chemsys, entries=corrected_entries)
