from pathlib import Path
import pytest
import numpy as np


@pytest.fixture(scope="session")
def test_dir():
    return Path(__file__).parent.parent.parent.joinpath("test_files").resolve()


def assert_schemas_equal(test_schema, valid_schema):
    """
    Recursively test all items in valid_schema are present and equal in test_schema.

    While test_schema can be a pydantic schema or dictionary, the valid schema must
    be a (nested) dictionary. This function automatically handles accessing the
    attributes of classes in the test_schema.

    Args:
        test_schema: A pydantic schema or dictionary of the schema.
        valid_schema: A (nested) dictionary specifying the key and values that must be
            present in test_schema. This is what the generated test_schema will be tested against
    """
    from pydantic import BaseModel

    if isinstance(valid_schema, dict):
        for key, sub_valid_schema in valid_schema.items():
            if isinstance(key, str) and hasattr(test_schema, key):
                sub_test_schema = getattr(test_schema, key)
                if key == "initial_molecule":
                    sub_test_schema = sub_test_schema.as_dict()
                elif key == "optimized_molecule":
                    sub_test_schema = (
                        sub_test_schema.as_dict() if sub_test_schema else {}
                    )
            elif not isinstance(test_schema, BaseModel):
                sub_test_schema = test_schema[key]
            else:
                raise ValueError(f"{type(test_schema)} does not have field: {key}")
            return assert_schemas_equal(sub_test_schema, sub_valid_schema)

    elif isinstance(valid_schema, list):
        for i, sub_valid_schema in enumerate(valid_schema):
            return assert_schemas_equal(test_schema[i], sub_valid_schema)

    elif isinstance(valid_schema, np.ndarray):
        assert np.array_equal(test_schema, valid_schema)

    elif isinstance(valid_schema, float):
        assert test_schema == pytest.approx(valid_schema)
    else:
        assert test_schema == valid_schema


class SchemaTestData:
    """Dummy class to be used to contain all test data information"""


class SinglePointTest(SchemaTestData):
    folder = "qchem_sp_test"
    task_files = {
        "standard": {
            "qcinput_file": "mol.qin.gz",
            "qcoutput_file": "mol.qout.gz",
        }
    }

    objects = {"standard": []}
    task_doc = {
        "calcs_reversed": [
            {
                "output": {
                    "mulliken": [np.array([-0.713178, 0.357278, 0.3559])],
                    "resp": [np.array([-0.872759, 0.436379, 0.436379])],
                    "final_energy": -76.4493700739,
                },
                "input": {
                    "charge": 0,
                    "rem": {
                        "job_type": "sp",
                        "basis": "def2-qzvppd",
                        "max_scf_cycles": "100",
                        "gen_scfman": "true",
                        "xc_grid": "3",
                        "thresh": "14",
                        "s2thresh": "16",
                        "scf_algorithm": "diis",
                        "resp_charges": "true",
                        "symmetry": "false",
                        "sym_ignore": "true",
                        "method": "wb97mv",
                        "solvent_method": "smd",
                        "ideriv": "1",
                    },
                    "job_type": "sp",
                },
            }
        ],
        "input": {
            "initial_molecule": {
                "@module": "pymatgen.core.structure",
                "@class": "Molecule",
                "charge": 0.0,
                "spin_multiplicity": 1,
                "sites": [
                    {
                        "name": "O",
                        "species": [{"element": "O", "occu": 1}],
                        "xyz": [-0.80595, 2.22952, -0.01914],
                        "properties": {},
                        "label": "O",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [0.18338, 2.20176, 0.01351],
                        "properties": {},
                        "label": "H",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [-1.09531, 1.61602, 0.70231],
                        "properties": {},
                        "label": "H",
                    },
                ],
            },
            "rem": {
                "job_type": "sp",
                "basis": "def2-qzvppd",
                "max_scf_cycles": "100",
                "gen_scfman": "true",
                "xc_grid": "3",
                "thresh": "14",
                "s2thresh": "16",
                "scf_algorithm": "diis",
                "resp_charges": "true",
                "symmetry": "false",
                "sym_ignore": "true",
                "method": "wb97mv",
                "solvent_method": "smd",
                "ideriv": "1",
            },
            "level_of_theory": "wB97M-V/def2-QZVPPD/SMD",
            "task_type": "Single Point",
            "calc_type": "wB97M-V/def2-QZVPPD/SMD Single Point",
            "solvation_lot_nfo": "wB97M-V/def2-QZVPPD/SMD(SOLVENT=WATER)",
        },
        "output": {
            "mulliken": [np.array([-0.713178, 0.357278, 0.3559])],
            "resp": [np.array([-0.872759, 0.436379, 0.436379])],
            "final_energy": -76.4493700739,
            "dipoles": {
                "total": 2.4648,
                "dipole": [np.array([1.4227, -1.3039, 1.5333])],
                "RESP_total": 2.5411,
                "RESP_dipole": [np.array([1.4672, -1.3441, 1.5806])],
            },
        },
        "custodian": [
            {
                "job": {
                    "@module": "custodian.qchem.jobs",
                    "@class": "QCJob",
                    "@version": "2022.5.26",
                    "qchem_command": ["qchem"],
                    "max_cores": "40",
                    "multimode": "openmp",
                    "input_file": "mol.qin",
                    "output_file": "mol.qout",
                    "qclog_file": "mol.qclog",
                    "suffix": "",
                    "calc_loc": "/tmp",
                    "nboexe": None,
                    "save_scratch": False,
                    "backup": "true",
                },
                "corrections": [],
            }
        ],
    }


class OptimizationTest(SchemaTestData):
    folder = "qchem_opt_test"
    task_files = {
        "standard": {
            "qcinput_file": "mol.qin.gz",
            "qcoutput_file": "mol.qout.gz",
        }
    }

    objects = {"standard": []}
    task_doc = {
        "calcs_reversed": [
            {
                "output": {
                    "optimized_molecule": {
                        "@module": "pymatgen.core.structure",
                        "@class": "Molecule",
                        "charge": 0,
                        "spin_multiplicity": 1,
                        "sites": [
                            {
                                "name": "O",
                                "species": [{"element": "O", "occu": 1}],
                                "xyz": [-0.8008592596, 2.2248298937, -0.0136245943],
                                "properties": {},
                                "label": "O",
                            },
                            {
                                "name": "H",
                                "species": [{"element": "H", "occu": 1}],
                                "xyz": [0.1637955748, 2.1962925542, 0.0199393927],
                                "properties": {},
                                "label": "H",
                            },
                            {
                                "name": "H",
                                "species": [{"element": "H", "occu": 1}],
                                "xyz": [-1.0808163152, 1.6261775521, 0.6903652017],
                                "properties": {},
                                "label": "H",
                            },
                        ],
                    },
                    "mulliken": [-0.373491, 0.186964, 0.186527],
                    "resp": [-0.89522, 0.44761, 0.44761],
                    "final_energy": -76.358341626913,
                },
                "input": {
                    "charge": 0,
                    "rem": {
                        "job_type": "sp",
                        "basis": "def2-qzvppd",
                        "max_scf_cycles": "100",
                        "gen_scfman": "true",
                        "xc_grid": "3",
                        "thresh": "14",
                        "s2thresh": "16",
                        "scf_algorithm": "diis",
                        "resp_charges": "true",
                        "symmetry": "false",
                        "sym_ignore": "true",
                        "method": "wb97mv",
                        "solvent_method": "smd",
                        "ideriv": "1",
                    },
                    "job_type": "sp",
                },
            }
        ],
        "input": {
            "initial_molecule": {
                "@module": "pymatgen.core.structure",
                "@class": "Molecule",
                "charge": 0.0,
                "spin_multiplicity": 1,
                "sites": [
                    {
                        "name": "O",
                        "species": [{"element": "O", "occu": 1}],
                        "xyz": [-0.80595, 2.22952, -0.01914],
                        "properties": {},
                        "label": "O",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [0.18338, 2.20176, 0.01351],
                        "properties": {},
                        "label": "H",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [-1.09531, 1.61602, 0.70231],
                        "properties": {},
                        "label": "H",
                    },
                ],
            },
            "rem": {
                "job_type": "opt",
                "basis": "def2-svpd",
                "max_scf_cycles": "100",
                "gen_scfman": "true",
                "xc_grid": "3",
                "thresh": "14",
                "s2thresh": "16",
                "scf_algorithm": "diis",
                "resp_charges": "true",
                "symmetry": "false",
                "sym_ignore": "true",
                "method": "wb97mv",
                "solvent_method": "smd",
                "ideriv": "1",
                "geom_opt2": "3",
            },
            "level_of_theory": "wB97M-V/def2-SVPD/SMD",
            "task_type": "Geometry Optimization",
            "calc_type": "wB97M-V/def2-SVPD/SMD Geometry Optimization",
            "solvation_lot_nfo": "wB97M-V/def2-SVPD/SMD(SOLVENT=WATER)",
        },
        "output": {
            "initial_molecule": {
                "@module": "pymatgen.core.structure",
                "@class": "Molecule",
                "charge": 0.0,
                "spin_multiplicity": 1,
                "sites": [
                    {
                        "name": "O",
                        "species": [{"element": "O", "occu": 1}],
                        "xyz": [-0.80595, 2.22952, -0.01914],
                        "properties": {},
                        "label": "O",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [0.18338, 2.20176, 0.01351],
                        "properties": {},
                        "label": "H",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [-1.09531, 1.61602, 0.70231],
                        "properties": {},
                        "label": "H",
                    },
                ],
            },
            "optimized_molecule": {
                "@module": "pymatgen.core.structure",
                "@class": "Molecule",
                "charge": 0,
                "spin_multiplicity": 1,
                "sites": [
                    {
                        "name": "O",
                        "species": [{"element": "O", "occu": 1}],
                        "xyz": [-0.8008592596, 2.2248298937, -0.0136245943],
                        "properties": {},
                        "label": "O",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [0.1637955748, 2.1962925542, 0.0199393927],
                        "properties": {},
                        "label": "H",
                    },
                    {
                        "name": "H",
                        "species": [{"element": "H", "occu": 1}],
                        "xyz": [-1.0808163152, 1.6261775521, 0.6903652017],
                        "properties": {},
                        "label": "H",
                    },
                ],
            },
            "mulliken": [-0.373491, 0.186964, 0.186527],
            "resp": [-0.89522, 0.44761, 0.44761],
            "final_energy": -76.358341626913,
        },
        "custodian": [
            {
                "job": {
                    "@module": "custodian.qchem.jobs",
                    "@class": "QCJob",
                    "@version": "2022.5.26",
                    "qchem_command": ["qchem"],
                    "max_cores": "40",
                    "multimode": "openmp",
                    "input_file": "mol.qin",
                    "output_file": "mol.qout",
                    "qclog_file": "mol.qclog",
                    "suffix": "",
                    "calc_loc": "/tmp",
                    "nboexe": "null",
                    "save_scratch": "false",
                    "backup": "true",
                },
                "corrections": [],
            }
        ],
    }


objects = {cls.__name__: cls for cls in SchemaTestData.__subclasses__()}


def get_test_object(object_name):
    """Get the schema test data object from the class name."""
    return objects[object_name]
