"""Test Lobster document class."""

from pathlib import Path
import pytest
from pymatgen.core.structure import Structure
from pymatgen.electronic_structure.cohp import Cohp, CompleteCohp
from pymatgen.electronic_structure.dos import LobsterCompleteDos
from pymatgen.io.lobster import (
    Bandoverlaps,
    Charge,
    Grosspop,
    Icohplist,
    MadelungEnergies,
    SitePotential,
)
from emmet.core.lobster import (
    LobsterTaskDocument, 
    CohpPlotData,
    CondensedBondingAnalysis,
    LobsterinModel,
    LobsteroutModel,
    LobsterTaskDocument,
    StrongestBonds
)

@pytest.fixture(scope="module")
def lobster_test_dir(test_dir: Path) -> Path:
    return test_dir / "lobster"

@pytest.mark.parametrize("save_cohp_plots", [True, False])
@pytest.mark.parametrize("store_lso_dos", [True, False])
@pytest.mark.parametrize("add_coxxcar_to_task_document", [True, False])
def test_lobster_task_doc(lobster_test_dir,  save_cohp_plots, store_lso_dos, add_coxxcar_to_task_document, tmp_path):
    lobster_doc = LobsterTaskDocument.from_directory(
        dir_name=lobster_test_dir / "mp-2534",
        save_cohp_plots=save_cohp_plots,
        store_lso_dos=store_lso_dos,
        add_coxxcar_to_task_document=add_coxxcar_to_task_document,
        save_cba_jsons=tmp_path /  "cba.json.gz",
        save_computational_data_jsons=tmp_path / "computational_data.json.gz",
    )
    assert isinstance(lobster_doc, LobsterTaskDocument)
    if add_coxxcar_to_task_document:
        assert {*map(type, (lobster_doc.cohp_data, lobster_doc.cobi_data, lobster_doc.coop_data))} == {CompleteCohp}
    else:
        assert {*map(type, (lobster_doc.cohp_data, lobster_doc.cobi_data, lobster_doc.coop_data))} == {type(None)}
    assert Path(tmp_path / "cba.json.gz").is_file()
    assert Path(tmp_path / "computational_data.json.gz").is_file()

    assert isinstance(lobster_doc.structure, Structure)
    assert isinstance(lobster_doc.lobsterout, LobsteroutModel)
    assert lobster_doc.lobsterout.charge_spilling[0] == pytest.approx(0.00989999, abs=1e-7)

    assert isinstance(lobster_doc.lobsterin, LobsterinModel)
    assert lobster_doc.lobsterin.cohp_start_energy == -5
    assert isinstance(lobster_doc.strongest_bonds, StrongestBonds)
    assert lobster_doc.strongest_bonds.strongest_bonds_icohp["As-Ga"] == pytest.approx(
        {"bond_strength": -4.32971, "length": 2.4899}
    )
    assert lobster_doc.strongest_bonds.strongest_bonds_icobi["As-Ga"] == pytest.approx(
        {"bond_strength": 0.82707, "length": 2.4899}
    )
    assert lobster_doc.strongest_bonds.strongest_bonds_icoop["As-Ga"] == pytest.approx(
        {"bond_strength": 0.31405, "length": 2.4899}
    )
    assert lobster_doc.strongest_bonds.which_bonds == "all"
    assert lobster_doc.strongest_bonds_cation_anion.strongest_bonds_icohp[
        "As-Ga"
    ] == pytest.approx({"bond_strength": -4.32971, "length": 2.4899})
    assert lobster_doc.strongest_bonds_cation_anion.strongest_bonds_icobi[
        "As-Ga"
    ] == pytest.approx({"bond_strength": 0.82707, "length": 2.4899})
    assert lobster_doc.strongest_bonds_cation_anion.strongest_bonds_icoop[
        "As-Ga"
    ] == pytest.approx({"bond_strength": 0.31405, "length": 2.4899})
    assert lobster_doc.strongest_bonds_cation_anion.which_bonds == "cation-anion"
    assert isinstance(lobster_doc.lobsterpy_data.cohp_plot_data.data["Ga1: 4 x As-Ga"], Cohp)
    assert lobster_doc.lobsterpy_data.which_bonds == "all"
    assert lobster_doc.lobsterpy_data_cation_anion.which_bonds == "cation-anion"
    assert lobster_doc.lobsterpy_data.number_of_considered_ions == 2
    assert isinstance(
        lobster_doc.lobsterpy_data_cation_anion.cohp_plot_data.data["Ga1: 4 x As-Ga"], Cohp
    )
    assert isinstance(lobster_doc.lobsterpy_text, str)
    assert isinstance(lobster_doc.lobsterpy_text_cation_anion, str)

    assert isinstance(lobster_doc.dos, LobsterCompleteDos)
    assert isinstance(lobster_doc.charges, Charge)
    assert isinstance(lobster_doc.madelung_energies, MadelungEnergies)
    assert isinstance(lobster_doc.site_potentials, SitePotential)
    assert isinstance(lobster_doc.band_overlaps, Bandoverlaps)
    assert {*map(type, (lobster_doc.icohp_list, lobster_doc.icobi_list, lobster_doc.icoop_list))} == {Icohplist}
    assert isinstance(lobster_doc.gross_populations, Grosspop)
    assert lobster_doc.chemsys == "As-Ga"