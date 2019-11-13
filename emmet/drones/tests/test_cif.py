import pytest
from pathlib import Path
from datetime import datetime
from emmet.drones import CIFDrone
from pymatgen.io.cif import CifParser


@pytest.fixture
def test_dir():
    return Path(__file__).parent / ".." / ".." / ".." / "test_files"


def test_read_cif(test_dir):
    drone = CIFDrone()
    doc = drone._read_cif(test_dir / "icsd/999999999/999999999.cif")
    for k in ["structures", "reference", "cif_data", "nstructures", "warnings"]:
        assert k in doc


def _analyze_cif_dict():
    test_cif_data = {
        "_chemical_name_mineral": "temp_min",
        "_chemical_name_systematic": "temp_chem",
        "_cell_measurement_pressure": 1000,
    }
    drone = CIFDrone()

    doc = drone._analyze_cif_dict(test_cif_data)
    assert doc["min_name"] == "temp_min"
    assert doc["chem_name"] == "temp_chem"
    assert doc["pressure"] == 1.0


def test_get_db_history():

    drone = CIFDrone()

    test_docs = [
        {"_database_code_icsd": 1},
        {"cod_database_code": 2},
        {"_database_code_icsd": 3, "cod_database_code": 4},
    ]

    test_history = drone._get_db_history(test_docs[0])
    assert test_history[0]["name"] == "ICSD"
    assert test_history[0]["description"]["id"] == 1

    test_history = drone._get_db_history(test_docs[1])
    assert test_history[0]["name"] == "Crystallography Open Database"
    assert test_history[0]["description"]["id"] == 2

    test_history = drone._get_db_history(test_docs[2])
    assert test_history[0]["name"] == "ICSD"
    assert test_history[0]["description"]["id"] == 3
    assert test_history[1]["name"] == "Crystallography Open Database"
    assert test_history[1]["description"]["id"] == 4


def test_analye_struc(test_dir):
    parser = CifParser(test_dir / "icsd/5656565656/5656565656.cif")
    struc = parser.get_structures()[0]

    drone = CIFDrone()
    assert drone._analyze_struc(struc)["contains_H_isotopes"]
    assert drone._analyze_struc(struc, actual_composition="D1 Al1 O2")[
        "consistent_composition"
    ]
    assert (
        drone._analyze_struc(struc, actual_composition="D2 Al2 O2")[
            "consistent_composition"
        ]
        is False
    )

    assert drone._analyze_struc(struc, actual_composition="H1 Al1 O2")[
        "implicit_hydrogen"
    ]
    struc.replace_species({"D+": "H"})
    assert (
        drone._analyze_struc(struc, actual_composition="H1 Al1 O2")["implicit_hydrogen"]
        is False
    )


def test_get_user_meta(test_dir):

    drone = CIFDrone()

    assert len(drone._get_user_meta(test_dir / "icsd/5656565656/5656565656.cif")) > 0


def test_fix_H_isotopes(test_dir):
    parser = CifParser(test_dir / "icsd/5656565656/5656565656.cif")
    struc = parser.get_structures()[0]

    drone = CIFDrone()

    # D in place of H before
    assert struc.composition["H"] == 0
    assert struc.composition["D+"] > 0

    # It says it fixed it
    assert drone._fix_H_isotopes(struc)

    # H in place of D now
    assert struc.composition["D+"] == 0
    assert struc.composition["H"] > 0

    # Nothign to fix now
    assert not drone._fix_H_isotopes(struc)


def test_find_authors():

    drone = CIFDrone()
    assert len(drone._find_authors({})) == 0
    assert len(drone._find_authors({"_publ_author_name": ["Test"]})) == 1
    assert drone._find_authors({"_publ_author_name": ["Test"]})[0]["name"] == "Test"
    assert drone._find_authors({"_publ_author_name": ["Test"]})[0]["email"] == ""


def test_get_created_date():
    drone = CIFDrone()

    assert drone._get_created_date({}).year == datetime.now().year
    date_fields = [
        "_audit_creation_date",
        "_audit_update_record",
        "_citation_year",
        "_journal_year",
    ]
    for k in date_fields:
        assert drone._get_created_date({k: "2018-11-01"}).year == 2018


def test_determine_experimetnal():
    drone = CIFDrone()

    assert drone._determine_experimental({}) is False
    assert drone._determine_experimental({"experimental": True})
    assert drone._determine_experimental({"experimental_PDF_number": True})
