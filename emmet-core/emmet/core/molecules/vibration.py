import warnings
from itertools import groupby
from typing import List
from datetime import datetime

import numpy as np
from pydantic import Field

from pymatgen.core.periodic_table import Element

from emmet.core.mpid import MPID
from emmet.core.structure import MoleculeMetadata
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


class SpectrumDoc(MoleculeMetadata):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    spectrum_name: str

    material_id: MPID = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    spectrum_id: str = Field(
        ...,
        title="Spectrum Document ID",
        description="The unique ID for this spectrum document",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    warnings: List[str] = Field([], description="Any warnings related to this property")


class VibSpectrumDoc(SpectrumDoc):

    spectrum_name = "IR Vibrational"

    frequencies: List[float] = Field(..., title="Vibrational Frequencies",
                                     description="List of vibrational frequencies in the molecules' spectrum")

    intensities: List[float] = Field(..., title="IR intensities",
                                     description="Intensities for IR vibrational spectrum peaks")

    task_id: MPID = Field(..., title="Calculation ID", description="Task ID used to make this IR spectrum")

    @classmethod
    def from_task(cls, task: TaskDocument, molecule_id: MPID, **kwargs):
        """
        Construct a vibrational spectrum document

        task document from which bonding properties can be extracted
        :param molecule_id: mpid
        :param kwargs: to pass to SpectrumDoc
        :return:
        """

        if task.output.frequencies is None:
            raise Exception("No frequencies in task!")

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        frequencies = task.output.frequencies
        intensities = None
        for calc in task.calcs_reversed:
            if calc.get("IR_intens", None) is not None:
                intensities = calc.get("IR_intens")
                break

        if intensities is None:
            raise Exception("No IR intensities in task!")

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            frequencies=frequencies,
            intensities=intensities,
            spectrum_id=f"{molecule_id}-IR",
            task_id=task.task_id,
            **kwargs,
        )

class VibrationalModesDoc(PropertyDoc):
    pass