from __future__ import annotations

from datetime import datetime

from emmet.core.base import EmmetBaseModel
from emmet.core.mpid import MPID
from emmet.core.triage.filter import Filter
from emmet.core.triage.triager import Triager
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.task_valid import TaskDocument

from emmet.core.utils import DocEnum

from importlib.resources import files as import_files
from monty.serialization import loadfn
import numpy as np
from pydantic import Field

from pymatgen.analysis.bond_valence import BVAnalyzer
from pymatgen.analysis.local_env import CrystalNN


from typing import Any, Dict, List, Union

_MP_PARAMS = loadfn(str(import_files("emmet.core.triage") / "./MP_filter_bounds.json"))


class FailedTriageMessage(DocEnum):
    WRONGPOT = "TR0", "Used non-MP POTCARs"
    MAGMOM = "TR1", "Max |magmom| too large"
    OOBMAXAVG = "TR2", "Ratio of the max to avg relative composition out of bounds"
    OOBMAXMIN = "TR3", "Ratio of the max to min relative composition out of bounds"
    OOBAVGMIN = "TR4", "Ratio of the avg to min relative composition out of bounds"
    LOWPACK = "TR5", "Packing density too low"
    HIPACK = "TR6", "Packing density too high"
    MAXCOORD = "TR7", "Maximum coordination number too large"
    UKNCHEM = "TR8", "Coordination environment does not exist in MP"


class EmmetFilter(Filter):
    reason: FailedTriageMessage = None


class potcar_titels(EmmetFilter):
    ref_arg: set[str] = set(_MP_PARAMS["potcar_titels"])
    operation: str = "issuperset"
    reason = FailedTriageMessage.WRONGPOT


class max_magmom(EmmetFilter):
    ref_arg: float = 5.0  # _MP_stats["max_magmom"]["max"]
    operation: str = ">="
    reason = FailedTriageMessage.MAGMOM


class ratio_max_to_avg_concentration(EmmetFilter):
    ref_arg: List[float] = _MP_PARAMS["ratio_max_to_avg_concentration"]
    operation: List[str] = ["<=", ">="]
    reason = FailedTriageMessage.OOBMAXAVG


class ratio_max_to_min_concentration(EmmetFilter):
    ref_arg: List[float] = _MP_PARAMS["ratio_max_to_min_concentration"]
    operation: List[str] = ["<=", ">="]
    reason = FailedTriageMessage.OOBMAXMIN


class ratio_avg_to_min_concentration(Filter):
    ref_arg: List[float] = _MP_PARAMS["ratio_avg_to_min_concentration"]
    operation: str = ["<=", ">="]
    reason = FailedTriageMessage.OOBAVGMIN


class min_packing_density(EmmetFilter):
    ref_arg: float = _MP_PARAMS["min_packing_density"]
    operation: str = "<="
    reason = FailedTriageMessage.LOWPACK


class max_packing_density(EmmetFilter):
    ref_arg: float = _MP_PARAMS["max_packing_density"]
    operation: str = ">="
    reason = FailedTriageMessage.HIPACK


class max_coordination_number(EmmetFilter):
    ref_arg: int = _MP_PARAMS["max_coordination_number"]
    operation: str = ">="
    reason = FailedTriageMessage.MAXCOORD


class coordination_environment(EmmetFilter):
    ref_arg: set[str] = set()
    operation: str = "issuperset"
    reason = FailedTriageMessage.UKNCHEM


class MPTriager(Triager):
    filters: tuple[EmmetFilter] = (
        potcar_titels,
        ratio_max_to_avg_concentration,
        ratio_max_to_min_concentration,
        ratio_avg_to_min_concentration,
        min_packing_density,
        max_packing_density,
        max_coordination_number,
    )
    coord_env: str = "CrystalNN"

    def get_filter_values_from_assessment(self):
        self._filter_values = {
            "potcar_titels": set(self.assessment["potcar_titels"]),
            "max_magmom": np.abs(np.array(self.assessment["magmom"])).max(),
            "ratio_max_to_avg_concentration": self.assessment["max pcomp"]
            / self.assessment["avg pcomp"],
            "ratio_max_to_min_concentration": self.assessment["max pcomp"]
            / self.assessment["min pcomp"],
            "ratio_avg_to_min_concentration": self.assessment["avg pcomp"]
            / self.assessment["min pcomp"],
            "min_packing_density": min(self.assessment["packing density"].values()),
            "max_packing_density": max(self.assessment["packing density"].values()),
            "max_coordination_number": self.assessment["max CN"],
        }

    @classmethod
    def from_task_doc(
        cls,
        task_doc: Union[TaskDoc, TaskDocument],
        coordination_numbers: list = None,
        calc_oxi_states: bool = False,
    ):
        structure = task_doc.output.structure
        if calc_oxi_states:
            try:
                oxi_list = BVAnalyzer().get_valences(structure)
                structure.add_oxidation_state_by_site(oxi_list)
            except ValueError:
                structure.add_oxidation_state_by_guess()

        if coordination_numbers is None:
            coordination_numbers = []
            CNN = CrystalNN()
            for isite in range(len(structure)):
                try:
                    NN = CNN.get_cn_dict(structure, isite)
                except ValueError:
                    NN = {}
                coordination_numbers.append(NN)

        if isinstance(task_doc, TaskDoc):
            potcars = [ps.titel for ps in task_doc.input.potcar_spec]
        elif isinstance(task_doc, TaskDocument):
            potcars = [ps["titel"] for ps in task_doc.input.potcar_spec]

        return cls(
            structure=structure,
            coordination_envs=coordination_numbers,
            potcars=potcars,
        )


class TriageDoc(EmmetBaseModel):
    """
    Triage document for a VASP calculation
    """

    task_id: MPID = Field(..., description="The task_id for this triage document")
    last_updated: datetime = Field(
        description="Last updated date for this document",
        default_factory=datetime.utcnow,
    )
    assessment: Dict[str, Any] = Field(
        {}, description="Assessment of the input structure"
    )
    triage: Dict[str, Any] = Field(
        {},
        description=("Dict of individual filter values and whether structure passed"),
    )
    reasons: List[Union[FailedTriageMessage, str]] = Field(
        [],
        description=(
            "Upon failing at least one filter, a list of all reasons "
            "why a structure failed to pass the filters"
        ),
    )
    valid: bool = Field(
        False, description="True if a calculation passed all filters; False otherwise."
    )

    @classmethod
    def from_task_doc(
        cls,
        task_doc: Union[TaskDoc, TaskDocument],
        coordination_numbers: list = None,
        calc_oxi_states: bool = False,
    ):
        triaged = MPTriager.from_task_doc(
            task_doc=task_doc,
            coordination_numbers=coordination_numbers,
            calc_oxi_states=calc_oxi_states,
        )

        doc = TriageDoc(
            task_id=task_doc.task_id,
            assessment=triaged.assessment,
            triage=triaged.triage,
            reasons=triaged.reasons,
            valid=triaged.valid,
        )

        return doc
