import logging
import warnings

from pydantic import BaseModel, Field
from pymatgen.analysis.phase_diagram import PhaseDiagram, PhaseDiagramError
from pymatgen.entries.computed_entries import ComputedStructureEntry

from emmet.builders.utils import HiddenPrints
from emmet.core.thermo import PhaseDiagramDoc, ThermoDoc
from emmet.core.types.enums import ThermoType
from emmet.core.types.pymatgen_types.computed_entries_adapter import (
    ComputedStructureEntryType,
)
from emmet.core.vasp.calc_types.enums import RunType


class ThermoBuilderInput(BaseModel):
    """
    Minimum inputs required to build ThermoDocs and PhaseDiagramDocs
    for a chemical system.
    """

    chemsys: str = Field(
        ...,
        description="Dash-delimited string of elements in the material.",
    )

    entries: dict[RunType | ThermoType, list[ComputedStructureEntryType]] = Field(
        ...,
        description="""
        List of all computed entries for 'chemsys' that are valid for the specified thermo type.
        Entries for elemental endpoints of 'chemsys' are required.
        """,
    )


class ThermoBuilderOutput(BaseModel):
    """Output of build_thermo_docs_and_phase_diagram_docs function"""

    chemsys: str
    thermo_docs: dict[RunType | ThermoType, list[ThermoDoc] | None]
    phase_diagram_docs: dict[RunType | ThermoType, PhaseDiagramDoc | None]


ThermoPDPair = tuple[list[ThermoDoc] | None, PhaseDiagramDoc | None]

logger = logging.getLogger()


def build_thermo_docs_and_phase_diagram_docs(
    thermo_input: ThermoBuilderInput,
) -> ThermoBuilderOutput:
    chemsys = thermo_input.chemsys

    thermo_docs = dict()
    phase_diagram_docs = dict()
    for thermo_type, entry_list in thermo_input.entries.items():
        logger.debug(
            f"Processing {len(entry_list)} entries for: {chemsys} and thermo type: {thermo_type}"
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with HiddenPrints():
                _thermo_docs, _phase_diagram_doc = _produce_pair(
                    entry_list, thermo_type
                )
                thermo_docs[thermo_type] = _thermo_docs
                phase_diagram_docs[thermo_type] = _phase_diagram_doc

    return ThermoBuilderOutput(
        chemsys=chemsys,
        thermo_docs=thermo_docs,
        phase_diagram_docs=phase_diagram_docs,
    )


def _produce_pair(
    computed_structure_entries: list[ComputedStructureEntry],
    thermo_type: RunType | ThermoType,
) -> ThermoPDPair:
    phase_diagram_doc = None
    try:
        phase_diagram: PhaseDiagram = ThermoDoc.construct_phase_diagram(
            computed_structure_entries
        )
        thermo_docs: list[ThermoDoc] = ThermoDoc.from_entries(
            computed_structure_entries,
            thermo_type,
            phase_diagram,
            use_max_chemsys=True,
            deprecated=False,
        )

        if phase_diagram:
            chemsys = "-".join(
                sorted(set([el.symbol for el in phase_diagram.elements]))
            )
            phase_diagram_id = f"{chemsys}_{thermo_type.value}"
            phase_diagram_doc = PhaseDiagramDoc(
                phase_diagram_id=phase_diagram_id,
                chemsys=chemsys,
                phase_diagram=phase_diagram,
                thermo_type=thermo_type,
            )

        if not thermo_docs:
            return None, phase_diagram_doc

        return thermo_docs, phase_diagram_doc

    except PhaseDiagramError as p:
        elsyms = []
        for entry in computed_structure_entries:
            elsyms.extend([el.symbol for el in entry.composition.elements])

        logger.error(
            f"Phase diagram error in chemsys {'-'.join(sorted(set(elsyms)))}: {p}"
        )

        return None, None
