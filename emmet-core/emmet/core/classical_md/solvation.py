from typing import Optional

import pandas as pd
from pydantic import Field, BaseModel


# class SolvationDoc(ClassicalMDDoc, arbitrary_types_allowed=True):
class SolvationDoc(BaseModel, arbitrary_types_allowed=True):
    solute_name: Optional[str] = Field(None, description="Name of the solute")

    solvent_names: Optional[list[str]] = Field(
        None, description="Names of the solvents"
    )

    is_electrolyte: Optional[bool] = Field(
        None, description="Whether system is an electrolyte"
    )

    # Solute.coordination

    coordination_numbers: Optional[dict[str, float]] = Field(
        None,
        description="A dictionary where keys are residue names and values are "
        "the mean coordination number of that residue.",
    )

    # coordination_numbers_by_frame: Optional[pd.DataFrame] = Field(
    #     None,
    #     description="Coordination number in each frame of the trajectory.",
    # )

    coordinating_atoms: Optional[pd.DataFrame] = Field(
        None,
        description="Fraction of each atom_type participating in solvation, "
        "calculated for each solvent.",
    )

    coordination_vs_random: Optional[dict[str, float]] = Field(
        None,
        description="Coordination number relative to random coordination.",
    )

    # Solute.networking

    # TODO: In the worst case, this could be extremely large.
    #       Need to consider what else we might want from this object.
    # network_df: Optional[pd.DataFrame] = Field(
    #     None,
    #     description="All solute-solvent networks in the system, indexed by the `frame` "
    #     "and a 'network_ix'. Columns are the species name and res_ix.",
    # )

    network_sizes: Optional[pd.DataFrame] = Field(
        None,
        description="Sizes of all networks, indexed by frame. Column headers are "
        "network sizes, e.g. the integer number of solutes + solvents in the network."
        "The values in each column are the number of networks with that size in each "
        "frame.",
    )

    solute_status: Optional[dict[str, float]] = Field(
        None,
        description="A dictionary where the keys are the “status” of the "
        "solute and the values are the fraction of solute with that "
        "status, averaged over all frames. “isolated” means that the solute not "
        "coordinated with any of the networking solvents, network size is 1. "
        "“paired” means the solute and is coordinated with a single networking "
        "solvent and that solvent is not coordinated to any other solutes, "
        "network size is 2. “networked” means that the solute is coordinated to "
        "more than one solvent or its solvent is coordinated to more than one "
        "solute, network size >= 3.",
    )

    # solute_status_by_frame: Optional[pd.DataFrame] = Field(
    #     None, description="Solute status in each frame of the trajectory."
    # )

    # Solute.pairing

    solvent_pairing: Optional[dict[str, float]] = Field(
        None, description="Fraction of each solvent coordinated to the solute."
    )

    # pairing_by_frame: Optional[pd.DataFrame] = Field(
    #     None, description="Solvent pairing in each frame."
    # )

    fraction_free_solvents: Optional[dict[str, float]] = Field(
        None, description="Fraction of each solvent not coordinated to solute."
    )

    diluent_composition: Optional[dict[str, float]] = Field(
        None, description="Fraction of diluent constituted by each solvent."
    )

    # diluent_composition_by_frame: Optional[pd.DataFrame] = Field(
    #     None, description="Diluent composition in each frame."
    # )

    diluent_counts: Optional[pd.DataFrame] = Field(
        None, description="Solvent counts in each frame."
    )

    # Solute.residence

    residence_times: Optional[dict[str, float]] = Field(
        None,
        description="Average residence time of each solvent."
        "Calculated by 1/e cutoff on autocovariance function.",
    )

    residence_times_fit: Optional[dict[str, float]] = Field(
        None,
        description="Average residence time of each solvent."
        "Calculated by fitting the autocovariance function to an exponential decay.",
    )

    # Solute.speciation

    speciation_fraction: Optional[pd.DataFrame] = Field(
        None, description="Fraction of shells of each type."
    )

    solvent_co_occurrence: Optional[pd.DataFrame] = Field(
        None,
        description="The actual co-occurrence of solvents divided by "
        "the expected co-occurrence in randomly distributed solvation shells."
        "i.e. given a molecule of solvent i in the shell, the probability of "
        "solvent j's presence relative to choosing a solvent at random "
        "from the pool of all coordinated solvents. ",
    )

    job_uuid: Optional[str] = Field(
        None, description="The UUID of the flow that generated this data."
    )

    @classmethod
    def from_solute(cls, solute, job_uuid) -> "SolvationDoc":
        return SolvationDoc(
            solute_name=solute.solute_name,
            solvent_names=list(solute.solvents.keys()),
            is_electrolyte=True,
            coordination_numbers=solute.coordination.coordination_numbers,
            # coordination_numbers_by_frame=solute.coordination.coordination_numbers_by_frame,
            coordinating_atoms=solute.coordination.coordinating_atoms,
            coordination_vs_random=solute.coordination.coordination_vs_random,
            network_sizes=solute.networking.network_sizes,
            solute_status=solute.networking.solute_status,
            # solute_status_by_frame=solute.networking.solute_status_by_frame,
            solvent_pairing=solute.pairing.solvent_pairing,
            # pairing_by_frame=solute.pairing.pairing_by_frame,
            fraction_free_solvents=solute.pairing.fraction_free_solvents,
            diluent_composition=solute.pairing.diluent_composition,
            # diluent_composition_by_frame=solute.pairing.diluent_composition_by_frame,
            diluent_counts=solute.pairing.diluent_counts,
            residence_times=solute.residence.residence_times_cutoff,
            residence_times_fit=solute.residence.residence_times_fit,
            speciation_fraction=solute.speciation.speciation_fraction,
            solvent_co_occurrence=solute.speciation.solvent_co_occurrence,
            flow_uuid=job_uuid,
        )
