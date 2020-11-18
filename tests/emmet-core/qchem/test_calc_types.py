import pytest

from pymatgen.core.periodic_table import Element
from pymatgen.analysis.graphs import MoleculeGraph
from pymatgen.analysis.local_env import OpenBabelNN

from emmet.stubs import Molecule
from emmet.core.qchem.bonding import Bonding
from emmet.core.qchem.calc_types import (
    TaskType,
    task_type,
    LevelOfTheory,
    calc_type
)
from emmet.core.qchem.solvent import SolventModel


@pytest.fixture
def input_dict():
    return {"rem": {"method": "b3lyp",
                    "basis": "def2-svpd",
                    "dft_d": "d3_bj",
                    "solvent_method": "smd",
                    "job_type": "sp"
                    },
            "smx": {"solvent": "other"}
            }


@pytest.fixture
def metadata():
    return {"custom_smd": "7.23,1.4097,0.0,0.859,36.83,0.0,0.0"}


def test_task_type():
    # TODO: Switch this to actual inputs?
    input_types = [
        ("single point", {"rem": {"job_type": "sp"}}, dict()),
        ("geometry optimization", {"rem": {"job_type": "opt"}}, dict()),
        ("frequency analysis", {"rem": {"job_type": "freq"}}, dict()),
        ("transition state optimization", {"rem": {"job_type": "ts"}}, dict()),
        ("frequency flattening optimization",
         {"rem": {"job_type": "opt"}},
         {"special_run_type": "frequency_flattener"}),
        ("frequency flattening transition state optimization",
         {"rem": {"job_type": "ts"}},
         {"special_run_type": "ts_frequency_flattener"}),
        ("critical point analysis",
         {"rem": {"job_type": "sp"}},
         {"critic2": {"bonding": dict(),
                      "YT": dict(),
                      "CP": dict(),
                      "processed": dict()}}),
    ]

    for _type, inputs, meta in input_types:
        assert task_type(inputs, meta) == TaskType(_type)


def test_lot(input_dict, metadata):
    lot = LevelOfTheory.from_inputs(input_dict, metadata)
    assert lot.functional == "b3lyp-d3"
    assert lot.basis == "def2-svpd"
    assert lot.solvent_model == SolventModel("SMX")
    assert lot.solvent_data.smx_string == "7.23,1.4097,0.0,0.859,36.83,0.0,0.0"
    assert lot.solvent_data.name == "Diglyme"


def test_calc_type(input_dict, metadata):
    assert calc_type(input_dict, metadata) == "single point : b3lyp-d3/def2-svpd/SMX(Diglyme)"

