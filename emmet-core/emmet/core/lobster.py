"""Module defining lobster document schemas."""

from __future__ import annotations

import logging
import time
import orjson
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from monty.os.path import zpath
from monty.io import zopen
from monty.dev import requires
from monty.json import MontyDecoder

from pydantic import BaseModel, Field
from pymatgen.core import Structure
from pymatgen.electronic_structure.cohp import Cohp, CompleteCohp
from pymatgen.electronic_structure.dos import LobsterCompleteDos
from pymatgen.io.lobster import (
    Bandoverlaps,
    Charge,
    Doscar,
    Grosspop,
    Icohplist,
    Lobsterin,
    Lobsterout,
    MadelungEnergies,
    SitePotential,
)
from typing_extensions import Self

from emmet.core.structure import StructureMetadata
from emmet.core.utils import jsanitize, arrow_incompatible
from emmet.core.types.typing import DateTimeType

try:
    from lobsterpy.cohp.analyze import Analysis
    from lobsterpy.cohp.describe import Description
except ImportError:
    Analysis = None
    Description = None

if TYPE_CHECKING:
    from typing import Any, Literal

logger = logging.getLogger(__name__)


def aggregate_paths(
    dir_name: Path,
) -> dict[str, Path]:
    paths = {}
    for p in dir_name.glob("*.lobster*"):
        paths[p.name.split(".lobster")[0]] = p
    for file_name in (
        "POTCAR",
        "POSCAR",
        "vasprun.xml",
        "lobsterin",
        "lobsterout",
    ):
        paths[file_name] = Path(zpath(str(dir_name / file_name)))
    return paths


@arrow_incompatible
class LobsteroutModel(BaseModel):
    """Definition of computational settings from the LOBSTER computation."""

    restart_from_projection: bool | None = Field(
        None,
        description="Bool indicating if the run has been restarted from a projection",
    )
    lobster_version: str | None = Field(None, description="Lobster version")
    threads: int | None = Field(
        None, description="Number of threads that Lobster ran on"
    )
    dft_program: str | None = Field(
        None, description="DFT program was used for this run"
    )
    charge_spilling: list[float] = Field(description="Absolute charge spilling")
    total_spilling: list[float] = Field(description="Total spilling")
    elements: list[str] = Field(description="Elements in structure")
    basis_type: list[str] = Field(description="Basis set used in Lobster")
    basis_functions: list[list[str]] = Field(description="basis_functions")
    timing: dict[str, dict[str, str]] = Field(description="Dict with infos on timing")
    warning_lines: list | None = Field(None, description="Warnings")
    info_orthonormalization: list | None = Field(
        None, description="additional information on orthonormalization"
    )
    info_lines: list | None = Field(
        None, description="list of strings with additional info lines"
    )
    has_doscar: bool | None = Field(
        None, description="Bool indicating if DOSCAR is present."
    )
    has_doscar_lso: bool | None = Field(
        None, description="Bool indicating if DOSCAR.LSO is present."
    )
    has_cohpcar: bool | None = Field(
        None, description="Bool indicating if COHPCAR is present."
    )
    has_coopcar: bool | None = Field(
        None, description="Bool indicating if COOPCAR is present."
    )
    has_cobicar: bool | None = Field(
        None, description="Bool indicating if COBICAR is present."
    )
    has_charge: bool | None = Field(
        None, description="Bool indicating if CHARGE is present."
    )
    has_madelung: bool | None = Field(
        None,
        description="Bool indicating if Site Potentials and Madelung file is present.",
    )
    has_projection: bool | None = Field(
        None, description="Bool indicating if projection file is present."
    )
    has_bandoverlaps: bool | None = Field(
        None, description="Bool indicating if BANDOVERLAPS file is present"
    )
    has_fatbands: bool | None = Field(
        None, description="Bool indicating if Fatbands are present."
    )
    has_grosspopulation: bool | None = Field(
        None, description="Bool indicating if GROSSPOP file is present."
    )
    has_density_of_energies: bool | None = Field(
        None, description="Bool indicating if DensityofEnergies is present"
    )


class LobsterinModel(BaseModel):
    """Definition of input settings for the LOBSTER computation."""

    cohp_start_energy: float = Field(description="Start energy for COHP computation")
    cohp_end_energy: float = Field(description="End energy for COHP computation")

    gaussian_smearing_width: float | None = Field(
        None, description="Set the smearing width in eV,default is 0.2 (eV)"
    )
    use_decimal_places: int | None = Field(
        None,
        description="Set the decimal places to print in output files, default is 5",
    )
    cohp_steps: float | None = Field(
        None, description="Number steps in COHPCAR; similar to NEDOS of VASP"
    )
    basis_set: str = Field(description="basis set of computation")
    cohp_generator: str = Field(
        description="Build the list of atom pairs to be analyzed using given distance"
    )
    save_projection_to_file: bool | None = Field(
        None, description="Save the results of projections"
    )
    lso_dos: bool | None = Field(
        None, description="Writes DOS output from the orthonormalized LCAO basis"
    )
    basis_functions: list[str] = Field(
        description="Specify the basis functions for element"
    )


class Bonding(BaseModel):
    """Model describing bonding field of BondsInfo."""

    integral: float | None = Field(
        None, description="Integral considering only bonding contributions from COHPs"
    )
    perc: float | None = Field(None, description="Percentage of bonding contribution")


class BondsInfo(BaseModel):
    """Model describing bonds field of SiteInfo."""

    ICOHP_mean: str = Field(description="Mean of ICOHPs of relevant bonds")
    ICOHP_sum: str = Field(description="Sum of ICOHPs of relevant bonds")
    has_antibdg_states_below_Efermi: bool = Field(  # noqa: N815
        description="Indicates if antibonding interactions below efermi are detected",
    )
    number_of_bonds: int = Field(
        description="Number of bonds considered in the analysis"
    )
    bonding: Bonding = Field(description="Model describing bonding contributions")
    antibonding: Bonding = Field(
        description="Model describing anti-bonding contributions"
    )


class SiteInfo(BaseModel):
    """Outer model describing sites field of Sites model."""

    env: str = Field(
        description="The coordination environment identified from "
        "the LobsterPy analysis",
    )
    bonds: dict[str, BondsInfo] = Field(
        description="A dictionary with keys as atomic-specie as key "
        "and BondsInfo model as values",
    )
    ion: str = Field(description="Ion to which the atom is bonded")
    charge: float = Field(description="Mulliken charge of the atom")
    relevant_bonds: list[str] = Field(
        description="List of bond labels from the LOBSTER files i.e. for e.g. "
        " from ICOHPLIST.lobster/ COHPCAR.lobster",
    )


class Sites(BaseModel):
    """Model describing, sites field of CondensedBondingAnalysis."""

    sites: dict[int, SiteInfo] = Field(
        description="A dictionary with site index as keys and SiteInfo model as values",
    )


@arrow_incompatible
class CohpPlotData(BaseModel):
    """Model describing the cohp_plot_data field of CondensedBondingAnalysis."""

    data: dict[str, Cohp] = Field(
        description="A dictionary with plot labels from LobsterPy "
        "automatic analysis as keys and Cohp objects as values",
    )


class DictIons(BaseModel):
    """Model describing final_dict_ions field of CondensedBondingAnalysis."""

    data: dict[str, dict[str, int]] = Field(
        description="Dict consisting information on environments of cations "
        "and counts for them",
    )


# TODO extricate this from individual dicts
@arrow_incompatible  # union float | bool type
class DictBonds(BaseModel):
    """Model describing final_dict_bonds field of CondensedBondingAnalysis."""

    data: dict[str, dict[str, float | bool]] = Field(
        description="Dict consisting information on ICOHPs per bond type"
    )


@arrow_incompatible
class CondensedBondingAnalysis(BaseModel):
    """Definition of condensed bonding analysis data from LobsterPy ICOHP."""

    formula: str = Field(description="Pretty formula of the structure")
    max_considered_bond_length: float = Field(
        description="Maximum bond length considered in bonding analysis"
    )
    # TODO: limit_icohp is only str for float("inf"), handled by bson
    limit_icohp: list[str | float] = Field(
        description="ICOHP range considered in co-ordination environment analysis"
    )
    number_of_considered_ions: int = Field(
        description="number of ions detected based on Mulliken/Löwdin Charges"
    )
    sites: Sites = Field(
        description="Bonding information at inequivalent sites in the structure",
    )
    type_charges: str = Field(
        description="Charge type considered for assigning valences in bonding analysis"
    )
    cutoff_icohp: float = Field(
        description="Percent limiting the ICOHP values to be considered"
        " relative to strongest ICOHP",
    )
    summed_spins: bool = Field(
        description="Bool that states if the spin channels in the "
        "cohp_plot_data are summed.",
    )
    start: float | None = Field(
        None,
        description="Sets the lower limit of energy relative to Fermi for evaluating"
        " bonding/anti-bonding percentages in the bond"
        " if set to None, all energies up-to the Fermi is considered",
    )
    cohp_plot_data: CohpPlotData = Field(
        description="Plotting data for the relevant bonds from LobsterPy analysis",
    )
    which_bonds: str = Field(
        description="Specifies types of bond considered in LobsterPy analysis",
    )
    final_dict_bonds: DictBonds = Field(
        description="Dict consisting information on ICOHPs per bond type",
    )
    final_dict_ions: DictIons = Field(
        description="Model that describes final_dict_ions field",
    )
    run_time: float = Field(
        description="Time needed to run Lobsterpy condensed bonding analysis"
    )

    @classmethod
    def from_directory(
        cls,
        dir_name: str | Path,
        save_cohp_plots: bool = False,
        lobsterpy_kwargs: dict | None = None,
        plot_kwargs: dict | None = None,
        which_bonds: Literal["cation-anion", "all"] = "all",
    ) -> tuple:
        """Create a task document from a directory containing LOBSTER files.

        Parameters
        ----------
        dir_name : path or str
            The path to the folder containing the calculation outputs.
        save_cohp_plots : bool.
            Bool to indicate whether automatic cohp plots and jsons
            from lobsterpy will be generated.
        lobsterpy_kwargs : dict.
            kwargs to change default lobsterpy automatic analysis parameters.
        plot_kwargs : dict.
            kwargs to change plotting options in lobsterpy.
        which_bonds: str.
            mode for condensed bonding analysis: "cation-anion" and "all".
        """
        plot_kwargs = plot_kwargs or {}
        lobsterpy_kwargs = lobsterpy_kwargs or {}
        dir_name = Path(dir_name)
        file_paths = aggregate_paths(dir_name)

        # Update lobsterpy analysis parameters with user supplied parameters
        lobsterpy_kwargs_updated = {
            "are_cobis": False,
            "are_coops": False,
            "cutoff_icohp": 0.10,
            "noise_cutoff": 0.1,
            "orbital_cutoff": 0.05,
            "orbital_resolved": False,
            "start": None,
            "summed_spins": False,  # we will always use spin polarization here
            "type_charge": None,
            **lobsterpy_kwargs,
        }

        try:
            start = time.time()
            analyse = Analysis(
                path_to_poscar=file_paths["POSCAR"],
                path_to_icohplist=file_paths["ICOHPLIST"],
                path_to_cohpcar=file_paths["COHPCAR"],
                path_to_charge=file_paths["CHARGE"],
                which_bonds=which_bonds,
                **lobsterpy_kwargs_updated,
            )
            cba_run_time = time.time() - start
            # initialize lobsterpy condensed bonding analysis
            cba = analyse.condensed_bonding_analysis

            cba_cohp_plot_data = {}  # Initialize dict to store plot data

            seq_cohps = analyse.seq_cohps
            seq_labels_cohps = analyse.seq_labels_cohps
            seq_ineq_cations = analyse.seq_ineq_ions
            struct = analyse.structure

            for ication, labels, cohps in zip(
                seq_ineq_cations, seq_labels_cohps, seq_cohps, strict=True
            ):
                label_str = f"{struct[ication].specie!s}{ication + 1!s}: "
                for label, cohp in zip(labels, cohps, strict=True):
                    if label is not None:
                        cba_cohp_plot_data[label_str + label] = cohp

            describe = Description(analysis_object=analyse)
            limit_icohp_val = list(cba["limit_icohp"])
            # TODO replace this with bson rep of float("inf")
            _replace_inf_values(limit_icohp_val)

            condensed_bonding_analysis = CondensedBondingAnalysis(  # type: ignore[call-arg]
                formula=cba["formula"],
                max_considered_bond_length=cba["max_considered_bond_length"],
                limit_icohp=limit_icohp_val,
                number_of_considered_ions=cba["number_of_considered_ions"],
                sites=Sites(**cba),
                type_charges=analyse.type_charge,
                cohp_plot_data=CohpPlotData(data=cba_cohp_plot_data),
                cutoff_icohp=analyse.cutoff_icohp,
                summed_spins=lobsterpy_kwargs_updated.get("summed_spins", False),
                which_bonds=analyse.which_bonds,
                final_dict_bonds=DictBonds(data=analyse.final_dict_bonds),
                final_dict_ions=DictIons(data=analyse.final_dict_ions),
                run_time=cba_run_time,
            )
            if save_cohp_plots:
                describe.plot_cohps(
                    save=True,
                    filename=f"automatic_cohp_plots_{which_bonds}.pdf",
                    hide=True,
                    **plot_kwargs,
                )

                filename = dir_name / f"condensed_bonding_analysis_{which_bonds}"
                with open(f"{filename}.json", "wb") as fp:
                    fp.write(orjson.dumps(analyse.condensed_bonding_analysis))
                with open(f"{filename}.txt", "w") as fp:
                    fp.write("\n".join(describe.text))

            # Read in strongest icohp values
            sb = _identify_strongest_bonds(
                analyse=analyse,
                **{
                    f"{k.lower()}_path": file_paths.get(k, Path(k))
                    for k in ("ICOBILIST", "ICOHPLIST", "ICOOPLIST")
                },
            )

        except ValueError:
            return None, None, None
        else:
            return condensed_bonding_analysis, describe, sb


class DosComparisons(BaseModel):
    """Model describing the DOS comparisons field in the CalcQualitySummary model."""

    tanimoto_orb_s: float | None = Field(
        None,
        description="Tanimoto similarity index between s orbital of "
        "VASP and LOBSTER DOS",
    )
    tanimoto_orb_p: float | None = Field(
        None,
        description="Tanimoto similarity index between p orbital of "
        "VASP and LOBSTER DOS",
    )
    tanimoto_orb_d: float | None = Field(
        None,
        description="Tanimoto similarity index between d orbital of "
        "VASP and LOBSTER DOS",
    )
    tanimoto_orb_f: float | None = Field(
        None,
        description="Tanimoto similarity index between f orbital of "
        "VASP and LOBSTER DOS",
    )
    tanimoto_summed: float | None = Field(
        None,
        description="Tanimoto similarity index for summed PDOS between "
        "VASP and LOBSTER",
    )
    e_range: list[float | None] = Field(
        description="Energy range used for evaluating the Tanimoto similarity index"
    )
    n_bins: int | None = Field(
        None,
        description="Number of bins used for discretizing the VASP and LOBSTER PDOS"
        "(Affects the Tanimoto similarity index)",
    )


class ChargeComparisons(BaseModel):
    """Model describing the charges field in the CalcQualitySummary model."""

    bva_mulliken_agree: bool | None = Field(
        None,
        description="Bool indicating whether atoms classification as cation "
        "or anion based on Mulliken charge signs of LOBSTER "
        "agree with BVA analysis",
    )
    bva_loewdin_agree: bool | None = Field(
        None,
        description="Bool indicating whether atoms classification as cations "
        "or anions based on Loewdin charge signs of LOBSTER "
        "agree with BVA analysis",
    )


class BandOverlapsComparisons(BaseModel):
    """Model describing the Band overlaps field in the CalcQualitySummary model."""

    file_exists: bool = Field(
        description="Boolean indicating whether the bandOverlaps.lobster "
        "file is generated during the LOBSTER run",
    )
    limit_maxDeviation: float | None = Field(  # noqa: N815
        None,
        description="Limit set for maximal deviation in pymatgen parser",
    )
    has_good_quality_maxDeviation: bool | None = Field(  # noqa: N815
        None,
        description="Boolean indicating whether the deviation at each k-point "
        "is within the threshold set using limit_maxDeviation "
        "for analyzing the bandOverlaps.lobster file data",
    )
    max_deviation: float | None = Field(
        None,
        description="Maximum deviation from ideal identity matrix from the observed in "
        "the bandOverlaps.lobster file",
    )
    percent_kpoints_abv_limit: float | None = Field(
        None,
        description="Percent of k-points that show deviations above "
        "the limit_maxDeviation threshold set in pymatgen parser.",
    )


class ChargeSpilling(BaseModel):
    """Model describing the Charge spilling field in the CalcQualitySummary model."""

    abs_charge_spilling: float = Field(
        description="Absolute charge spilling value from the LOBSTER calculation.",
    )
    abs_total_spilling: float = Field(
        description="Total charge spilling percent from the LOBSTER calculation.",
    )


@arrow_incompatible
class CalcQualitySummary(BaseModel):
    """Model describing the calculation quality of lobster run."""

    minimal_basis: bool = Field(
        description="Denotes whether the calculation used the minimal basis for the "
        "LOBSTER computation",
    )
    charge_spilling: ChargeSpilling = Field(
        description="Model describing the charge spilling from the LOBSTER runs",
    )
    charge_comparisons: ChargeComparisons | None = Field(
        None,
        description="Model describing the charge sign comparison results",
    )
    band_overlaps_analysis: BandOverlapsComparisons | None = Field(
        None,
        description="Model describing the band overlap file analysis results",
    )
    dos_comparisons: DosComparisons | None = Field(
        None,
        description="Model describing the VASP and LOBSTER PDOS comparisons results",
    )

    @classmethod
    @requires(
        Analysis,
        "lobsterpy must be installed to create an CalcQualitySummary from a directory.",
    )
    def from_directory(
        cls,
        dir_name: str | Path,
        calc_quality_kwargs: dict | None = None,
    ) -> Self:
        """Make a LOBSTER calculation quality summary from directory with LOBSTER files.

        Parameters
        ----------
        dir_name : path or str
            The path to the folder containing the calculation outputs.
        calc_quality_kwargs : dict
            kwargs to change calc quality analysis options in lobsterpy.

        Returns
        -------
        CalcQualitySummary
            A task document summarizing quality of the lobster calculation.
        """
        dir_name = Path(dir_name)
        calc_quality_kwargs = calc_quality_kwargs or {}

        file_paths = aggregate_paths(dir_name)
        doscar_path = file_paths.get("DOSCAR.LSO") or file_paths.get("DOSCAR")

        # Update calc quality kwargs supplied by user
        calc_quality_kwargs_updated = {
            "e_range": [-20, 0],
            "dos_comparison": True,
            "n_bins": 256,
            "bva_comp": True,
            **calc_quality_kwargs,
        }
        cal_quality_dict = Analysis.get_lobster_calc_quality_summary(
            path_to_poscar=file_paths["POSCAR"],
            path_to_vasprun=file_paths["vasprun.xml"],
            path_to_charge=file_paths["CHARGE"],
            path_to_potcar=file_paths.get("POTCAR"),
            path_to_doscar=doscar_path,
            path_to_lobsterin=file_paths["lobsterin"],
            path_to_lobsterout=file_paths["lobsterout"],
            path_to_bandoverlaps=file_paths.get("bandOverlaps"),
            **calc_quality_kwargs_updated,
        )
        return cls(**cal_quality_dict)


@arrow_incompatible
class StrongestBonds(BaseModel):
    """Strongest bonds extracted from ICOHPLIST/ICOOPLIST/ICOBILIST from LOBSTER.

    LobsterPy is used for the extraction.
    """

    which_bonds: str | None = Field(
        None,
        description="Denotes whether the information "
        "is for cation-anion pairs or all bonds",
    )
    strongest_bonds_icoop: dict | None = Field(
        None,
        description="Dict with infos on bond strength and bond length based on ICOOP.",
    )
    strongest_bonds_icohp: dict | None = Field(
        None,
        description="Dict with infos on bond strength and bond length based on ICOHP.",
    )
    strongest_bonds_icobi: dict | None = Field(
        None,
        description="Dict with infos on bond strength and bond length based on ICOBI.",
    )


@arrow_incompatible
class LobsterTaskDocument(StructureMetadata):
    """Definition of LOBSTER task document."""

    structure: Structure = Field(description="The structure used in this task")
    dir_name: str = Field(description="The directory for this Lobster task")
    last_updated: DateTimeType
    charges: Charge | None = Field(
        None,
        description="pymatgen Charge obj. Contains atomic charges based on Mulliken "
        "and Loewdin charge analysis",
    )
    lobsterout: LobsteroutModel = Field(description="Lobster out data")
    lobsterin: LobsterinModel = Field(description="Lobster calculation inputs")
    lobsterpy_data: CondensedBondingAnalysis | None = Field(
        None, description="Model describing the LobsterPy data"
    )
    lobsterpy_text: str | None = Field(
        None, description="Stores LobsterPy automatic analysis summary text"
    )
    calc_quality_summary: CalcQualitySummary | None = Field(
        None,
        description="Model summarizing results of lobster runs like charge spillings, "
        "band overlaps, DOS comparisons with VASP runs and quantum chemical LOBSTER "
        "charge sign comparisons with BVA method",
    )
    calc_quality_text: str | None = Field(
        None, description="Stores calculation quality analysis summary text"
    )
    strongest_bonds: StrongestBonds | None = Field(
        None,
        description="Describes the strongest cation-anion ICOOP, ICOBI and ICOHP bonds",
    )
    lobsterpy_data_cation_anion: CondensedBondingAnalysis | None = Field(
        None, description="Model describing the LobsterPy data"
    )
    lobsterpy_text_cation_anion: str | None = Field(
        None,
        description="Stores LobsterPy automatic analysis summary text",
    )
    strongest_bonds_cation_anion: StrongestBonds | None = Field(
        None,
        description="Describes the strongest cation-anion ICOOP, ICOBI and ICOHP bonds",
    )
    dos: LobsterCompleteDos | None = Field(
        None, description="pymatgen pymatgen.io.lobster.Doscar.completedos data"
    )
    lso_dos: LobsterCompleteDos | None = Field(
        None, description="pymatgen pymatgen.io.lobster.Doscar.completedos data"
    )
    madelung_energies: MadelungEnergies | None = Field(
        None,
        description="pymatgen Madelung energies obj. Contains madelung energies"
        "based on Mulliken and Loewdin charges",
    )
    site_potentials: SitePotential | None = Field(
        None,
        description="pymatgen Site potentials obj. Contains site potentials "
        "based on Mulliken and Loewdin charges",
    )
    gross_populations: Grosspop | None = Field(
        None,
        description="pymatgen Grosspopulations obj. Contains gross populations "
        " based on Mulliken and Loewdin charges ",
    )
    band_overlaps: Bandoverlaps | None = Field(
        None,
        description="pymatgen Bandoverlaps obj for each k-point from"
        " bandOverlaps.lobster file if it exists",
    )
    cohp_data: CompleteCohp | None = Field(
        None, description="pymatgen CompleteCohp object with COHP data"
    )
    coop_data: CompleteCohp | None = Field(
        None, description="pymatgen CompleteCohp object with COOP data"
    )
    cobi_data: CompleteCohp | None = Field(
        None, description="pymatgen CompleteCohp object with COBI data"
    )
    icohp_list: Icohplist | None = Field(
        None, description="pymatgen Icohplist object with ICOHP data"
    )
    icoop_list: Icohplist | None = Field(
        None, description="pymatgen Icohplist object with ICOOP data"
    )
    icobi_list: Icohplist | None = Field(
        None, description="pymatgen Icohplist object with ICOBI data"
    )

    @classmethod
    @requires(
        Analysis,
        "LobsterTaskDocument.from_directory requires lobsterpy.",
    )
    def from_directory(
        cls,
        dir_name: str | Path,
        additional_fields: dict | None = None,
        add_coxxcar_to_task_document: bool = False,
        analyze_outputs: bool = True,
        calc_quality_kwargs: dict | None = None,
        lobsterpy_kwargs: dict | None = None,
        plot_kwargs: dict | None = None,
        store_lso_dos: bool = False,
        save_cohp_plots: bool = True,
        save_cba_jsons: str | None = "cba.jsonl.gz",
        save_computational_data_jsons: str | None = "computational_data.jsonl.gz",
    ) -> Self:
        """Create a task document from a directory containing LOBSTER files.

        Parameters
        ----------
        dir_name : path or str.
            The path to the folder containing the calculation outputs.
        additional_fields : dict.
            Dictionary of additional fields to add to output document.
        add_coxxcar_to_task_document : bool.
            Bool to indicate whether to add COHPCAR, COOPCAR, COBICAR data objects
            to the task document.
        analyze_outputs: bool.
            If True, will enable lobsterpy analysis.
        calc_quality_kwargs : dict.
            kwargs to change calc quality summary options in lobsterpy.
        lobsterpy_kwargs : dict.
            kwargs to change default lobsterpy automatic analysis parameters.
        plot_kwargs : dict.
            kwargs to change plotting options in lobsterpy.
        store_lso_dos : bool.
            Whether to store the LSO DOS.
        save_cohp_plots : bool.
            Bool to indicate whether automatic cohp plots and jsons
            from lobsterpy will be generated.
        save_cba_jsons : str | None = "cba.jsonl.gz"
            If a str, the name of the JSON lines file to save condensed bonding analysis,
            consisting of outputs from lobsterpy analysis,
            calculation quality summary, lobster dos, charges and madelung energies
        save_computational_data_jsons : str | None = "computational_data.jsonl.gz"
            Name of the JSON lines file to save computational data to.

        Returns
        -------
        LobsterTaskDocument
            A task document for the lobster calculation.
        """
        additional_fields = {} if additional_fields is None else additional_fields
        dir_name = Path(dir_name)

        # Read in lobsterout and lobsterin
        file_paths = aggregate_paths(dir_name)
        lobsterout_doc = Lobsterout(file_paths["lobsterout"]).get_doc()
        lobster_out = LobsteroutModel(**lobsterout_doc)

        lobster_in_dict = Lobsterin.from_file(file_paths["lobsterin"])
        # convert keys to snake case
        lobster_in = LobsterinModel(
            **{
                k: lobster_in_dict.get(k.strip("_"))
                for k in LobsterinModel.model_fields
            }
        )

        # Do automatic bonding analysis with LobsterPy
        struct = Structure.from_file(file_paths["POSCAR"])

        # will perform two condensed bonding analysis computations
        condensed_bonding_analysis = None
        condensed_bonding_analysis_ionic = None
        sb_all = None
        sb_ionic = None
        calc_quality_summary = None
        calc_quality_text = None
        describe = None
        describe_ionic = None
        if analyze_outputs:
            if all(file_paths.get(k) for k in ("ICOHPLIST", "COHPCAR", "CHARGE")):
                (
                    condensed_bonding_analysis,
                    describe,
                    sb_all,
                ) = CondensedBondingAnalysis.from_directory(
                    dir_name,
                    save_cohp_plots=save_cohp_plots,
                    plot_kwargs=plot_kwargs,
                    lobsterpy_kwargs=lobsterpy_kwargs,
                    which_bonds="all",
                )
                (
                    condensed_bonding_analysis_ionic,
                    describe_ionic,
                    sb_ionic,
                ) = CondensedBondingAnalysis.from_directory(
                    dir_name,
                    save_cohp_plots=save_cohp_plots,
                    plot_kwargs=plot_kwargs,
                    lobsterpy_kwargs=lobsterpy_kwargs,
                    which_bonds="cation-anion",
                )
            # Get lobster calculation quality summary data

            calc_quality_summary = CalcQualitySummary.from_directory(
                dir_name,
                calc_quality_kwargs=calc_quality_kwargs,
            )

            calc_quality_text = Description.get_calc_quality_description(
                calc_quality_summary.model_dump()
            )

        # Read in COHPCAR, COBICAR, COOPCAR
        cohp_data = {
            "cohp_data": (
                CompleteCohp.from_file(
                    fmt="LOBSTER",
                    structure_file=file_paths["POSCAR"],
                    filename=file_paths["COHPCAR"],
                    are_coops=False,
                    are_cobis=False,
                )
                if file_paths.get("COHPCAR")
                else None
            ),
            "coop_data": (
                CompleteCohp.from_file(
                    fmt="LOBSTER",
                    structure_file=file_paths["POSCAR"],
                    filename=file_paths["COOPCAR"],
                    are_coops=True,
                    are_cobis=False,
                )
                if file_paths.get("COOPCAR")
                else None
            ),
            "cobi_data": (
                CompleteCohp.from_file(
                    fmt="LOBSTER",
                    structure_file=file_paths["POSCAR"],
                    filename=file_paths["COBICAR"],
                    are_coops=False,
                    are_cobis=True,
                )
                if file_paths.get("COBICAR")
                else None
            ),
        }

        doc = cls.from_structure(
            structure=struct,
            meta_structure=struct,
            dir_name=str(dir_name),
            lobsterin=lobster_in,
            lobsterout=lobster_out,
            # include additional fields for cation-anion
            lobsterpy_data=condensed_bonding_analysis,
            lobsterpy_text=" ".join(describe.text) if describe is not None else None,
            strongest_bonds=sb_all,
            lobsterpy_data_cation_anion=condensed_bonding_analysis_ionic,
            lobsterpy_text_cation_anion=(
                " ".join(describe_ionic.text) if describe_ionic is not None else None
            ),
            strongest_bonds_cation_anion=sb_ionic,
            calc_quality_summary=calc_quality_summary,
            calc_quality_text=(
                " ".join(calc_quality_text) if calc_quality_text is not None else None
            ),
            dos=(
                Doscar(
                    doscar=file_paths["DOSCAR"], structure_file=file_paths["POSCAR"]
                ).completedos
                if file_paths.get("DOSCAR")
                else None
            ),
            lso_dos=(
                Doscar(
                    doscar=file_paths["DOSCAR.LSO"], structure_file=file_paths["POSCAR"]
                ).completedos
                if (store_lso_dos and file_paths.get("DOSCAR.LSO"))
                else None
            ),
            charges=(
                Charge(filename=file_paths["CHARGE"])
                if file_paths.get("CHARGE")
                else None
            ),
            madelung_energies=(
                MadelungEnergies(filename=file_paths["MadelungEnergies"])
                if file_paths.get("MadelungEnergies")
                else None
            ),
            site_potentials=(
                SitePotential(filename=file_paths["SitePotentials"])
                if file_paths.get("SitePotentials")
                else None
            ),
            gross_populations=(
                Grosspop(filename=file_paths["GROSSPOP"])
                if file_paths.get("GROSSPOP")
                else None
            ),
            band_overlaps=(
                Bandoverlaps(filename=file_paths["bandOverlaps"])
                if file_paths.get("bandOverlaps")
                else None
            ),
            # include additional fields for all bonds
            **(cohp_data if add_coxxcar_to_task_document else {}),
            **{
                k: Icohplist(
                    filename=file_paths[v],
                    are_coops=(v == "ICOOPLIST"),
                    are_cobis=(v == "ICOBILIST"),
                )
                for k, v in {
                    "icohp_list": "ICOHPLIST",
                    "icoop_list": "ICOOPLIST",
                    "icobi_list": "ICOBILIST",
                }.items()
            },
        )

        if save_cba_jsons and analyze_outputs:
            if (
                doc.lobsterpy_data_cation_anion is not None
            ):  # check if cation-anion analysis failed
                data: list[dict[str, Any]] = [
                    {
                        f"{doc.lobsterpy_data_cation_anion.which_bonds.replace('-', '_')}_bonds": {
                            "lobsterpy_data": doc.lobsterpy_data_cation_anion,
                            "lobsterpy_text": [
                                "".join(doc.lobsterpy_text_cation_anion)
                            ],
                            "strongest_bonds": doc.strongest_bonds_cation_anion,
                        }
                    }
                ]
            else:
                data = [{"cation_anion_bonds": {}}]

            data.extend(
                [
                    {
                        f"{doc.lobsterpy_data.which_bonds}_bonds": {
                            "lobsterpy_data": doc.lobsterpy_data,
                            "lobsterpy_text": ["".join(doc.lobsterpy_text)],
                            "strongest_bonds": doc.strongest_bonds,
                        }
                    },
                    {"madelung_energies": doc.madelung_energies},
                    {"charges": doc.charges},
                    {"calc_quality_summary": doc.calc_quality_summary},
                    {"calc_quality_text": ["".join(doc.calc_quality_text)]},
                    {"dos": doc.dos},
                    {"lso_dos": doc.lso_dos},
                ]
            )

            with zopen(dir_name / save_cba_jsons, "wb") as file:
                # Write the json in iterable format
                # (Necessary to load large JSON files via ijson)

                for obj in data:
                    file.write(
                        orjson.dumps(
                            jsanitize(
                                obj, allow_bson=False, strict=True, enum_values=True
                            )
                        )
                        + "\n".encode("UTF-8")
                    )
                del data

        if save_computational_data_jsons:
            fields_to_exclude = [
                "nsites",
                "elements",
                "nelements",
                "formula_anonymous",
                "chemsys",
                "volume",
                "density",
                "density_atomic",
                "symmetry",
            ]
            doc_data = {
                k: v for k, v in doc.model_dump().items() if k not in fields_to_exclude
            }

            # Always add cohp, cobi and coop data to the jsons if files exists
            for k, v in cohp_data.items():
                if doc_data.get(k) is None and v is not None:
                    doc_data[k] = v

            with zopen(
                dir_name / save_computational_data_jsons,
                "wb",
            ) as file:

                for k, v in doc_data.items():
                    # Use monty encoder to automatically convert pymatgen
                    # objects and other data json compatible dict format
                    file.write(
                        orjson.dumps(
                            {
                                k: jsanitize(
                                    v,
                                    allow_bson=False,
                                    strict=True,
                                    enum_values=True,
                                )
                            },
                        )
                        + "\n".encode("UTF-8")
                    )

        return doc.model_copy(update=additional_fields)


def _replace_inf_values(data: dict[Any, Any] | list[Any]) -> None:
    """
    Replace the -inf value in dictionary and with the string representation '-Infinity'.

    Parameters
    ----------
    data : dict
        dictionary to recursively iterate over

    Returns
    -------
    data
        Dictionary with replaced -inf values.

    """
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict | list):
                _replace_inf_values(
                    value
                )  # Recursively process nested dictionaries and lists
            elif value == float("-inf"):
                data[key] = "-Infinity"  # Replace -inf with a string representation
    elif isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, dict | list):
                _replace_inf_values(
                    item
                )  # Recursively process nested dictionaries and lists
            elif item == float("-inf"):
                data[index] = "-Infinity"  # Replace -inf with a string representation


def _identify_strongest_bonds(
    analyse: Analysis,
    icobilist_path: Path,
    icohplist_path: Path,
    icooplist_path: Path,
) -> StrongestBonds:
    """
    Identify the strongest bonds and convert them into StrongestBonds objects.

    Parameters
    ----------
    analyse : .Analysis
        Analysis object from lobsterpy automatic analysis
    icobilist_path : Path or str
        Path to ICOBILIST.lobster
    icohplist_path : Path or str
        Path to ICOHPLIST.lobster
    icooplist_path : Path or str
        Path to ICOOPLIST.lobster

    Returns
    -------
    StrongestBonds
    """
    data = [
        (icohplist_path, False, False, "icohp"),
        (icobilist_path, True, False, "icobi"),
        (icooplist_path, False, True, "icoop"),
    ]
    model_data = {"which_bonds": analyse.which_bonds}
    for file, are_cobis, are_coops, prop in data:
        if file.exists():
            icohplist = Icohplist(
                filename=file,
                are_cobis=are_cobis,
                are_coops=are_coops,
            )
            bond_dict = _get_strong_bonds(
                getattr(icohplist.icohpcollection, "as_dict", dict)(),
                relevant_bonds=analyse.final_dict_bonds,
                are_cobis=are_cobis,
                are_coops=are_coops,
            )
            model_data[f"strongest_bonds_{prop}"] = bond_dict
        else:
            model_data[f"strongest_bonds_{prop}"] = {}
    return StrongestBonds(**model_data)


# Don't we have this in pymatgen somewhere?
def _get_strong_bonds(
    bondlist: dict, are_cobis: bool, are_coops: bool, relevant_bonds: dict
) -> dict:
    """
    Identify the strongest bonds from a list of bonds.

    Parameters
    ----------
    bondlist : dict.
        dict including bonding information
    are_cobis : bool.
        True if these are cobis
    are_coops : bool.
        True if these are coops
    relevant_bonds : dict.
        Dict include all bonds that are considered.

    Returns
    -------
    dict
        Dictionary including the strongest bonds.
    """
    bonds = []
    icohp_all = []
    lengths = []
    for a, b, c, length in zip(
        bondlist["list_atom1"],
        bondlist["list_atom2"],
        bondlist["list_icohp"],
        bondlist["list_length"],
        strict=True,
    ):
        bonds.append(f"{a.rstrip('0123456789')}-{b.rstrip('0123456789')}")
        icohp_all.append(sum(c.values()))
        lengths.append(length)

    bond_labels_unique = list(set(bonds))
    sep_icohp: list[list[float]] = [[]] * len(bond_labels_unique)
    sep_lengths: list[list[float]] = [[]] * len(bond_labels_unique)

    for idx, val in enumerate(bond_labels_unique):
        for j, val2 in enumerate(bonds):
            if val == val2:
                sep_icohp[idx].append(icohp_all[j])
                sep_lengths[idx].append(lengths[j])

    if are_cobis and not are_coops:
        prop = "icobi"
    elif not are_cobis and are_coops:
        prop = "icoop"
    else:
        prop = "icohp"

    bond_dict: dict[str, dict[str, float | str]] = {}
    for idx, lab in enumerate(bond_labels_unique):
        label = lab.split("-")
        label.sort()
        for rel_bnd in relevant_bonds:
            rel_bnd_list = rel_bnd.split("-")
            rel_bnd_list.sort()
            if label == rel_bnd_list:
                if prop == "icohp":
                    index = np.argmin(sep_icohp[idx])
                    bond_dict |= {
                        rel_bnd: {
                            "bond_strength": min(sep_icohp[idx]),
                            "length": sep_lengths[idx][index],
                        }
                    }
                else:
                    index = np.argmax(sep_icohp[idx])
                    bond_dict |= {
                        rel_bnd: {
                            "bond_strength": max(sep_icohp[idx]),
                            "length": sep_lengths[idx][index],
                        }
                    }
    return bond_dict


# Should probably live in atomate2 instead, not used here
def read_saved_jsonl(
    filename: str, pymatgen_objs: bool = True, query: str = "structure"
) -> dict[str, Any]:
    r"""
    Read the data from  \*.jsonl.gz files corresponding to query.

    Parameters
    ----------
    filename: str.
        name of the JSON lines file to read
    pymatgen_objs: bool.
        if True will convert structure,coop, cobi, cohp and dos to pymatgen objects
    query: str or None.
        field name to query from the JSON lines file. If None, all data will be returned.

    Returns
    -------
    dict
        Returns a dictionary with lobster task JSON data corresponding to query.
    """
    lobster_data: dict[str, Any] = {}
    with zopen(filename, "rb") as file:
        for line in file:
            data = orjson.loads(line)
            if query is None:
                lobster_data.update(data)
            elif query in data:
                lobster_data[query] = data[query]

    if not lobster_data:
        raise ValueError(
            "Please recheck the query argument. "
            f"No data associated to the requested 'query={query}' "
            f"found in the JSON lines file."
        )
    if pymatgen_objs:
        for query_key, value in lobster_data.items():
            if isinstance(value, dict):
                lobster_data[query_key] = MontyDecoder().process_decoded(value)
            elif "lobsterpy_data" in query_key:
                for field in lobster_data[query_key].__fields__:
                    val = MontyDecoder().process_decoded(
                        getattr(lobster_data[query_key], field)
                    )
                    setattr(lobster_data[query_key], field, val)

    return lobster_data
