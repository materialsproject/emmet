from datetime import datetime
import io
from monty.dev import deprecated

import pytest
from pymatgen.core import Lattice, Structure
from emmet.core.polar import DielectricDoc, PiezoelectricDoc


@pytest.fixture
def dielectric_structure():
    test_latt = Lattice.cubic(3.0)
    test_struc = Structure(lattice=test_latt, species=["Fe"], coords=[[0, 0, 0]])
    return test_struc


def test_dielectric(dielectric_structure):

    epsilon_static = [
        [10.81747665, -0.00378371, 0.0049036],
        [-0.00373185, 10.82629335, -0.00432847],
        [0.0036548, -0.00479139, 8.68204827],
    ]

    epsilon_ionic = [
        [30.98960925, -0.09107371, 0.00226948],
        [-0.09107371, 31.44264572, -0.00427919],
        [0.00226948, -0.00427919, 29.21747234],
    ]

    doc = DielectricDoc.from_ionic_and_electronic(
        material_id="mp-149",
        structure=dielectric_structure,
        electronic=epsilon_static,
        ionic=epsilon_ionic,
        deprecated=False,
    )

    print(doc.dict())

    assert isinstance(doc, DielectricDoc)
    assert doc.property_name == "dielectric"
    assert doc.material_id == "mp-149"
    assert doc.n == pytest.approx(3.17940376590938)
    assert doc.e_total == pytest.approx(40.6585061611482)
    assert doc.e_ionic == pytest.approx(30.5498978544694)


@pytest.fixture
def piezoelectric_structure():
    d = {
        "@module": "pymatgen.core.structure",
        "@class": "Structure",
        "charge": None,
        "lattice": {
            "matrix": [
                [5.463395, 0.079911, 0.053683],
                [3.078361, 4.516413, 0.054681],
                [3.077876, 1.656664, 4.202015],
            ],
            "a": 5.46424309108178,
            "b": 5.4660116030476,
            "c": 5.46578323211752,
            "alpha": 54.8815130437112,
            "beta": 54.8993054969752,
            "gamma": 54.8809763844894,
            "volume": 101.696886946191,
        },
        "sites": [
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.289733, 0.289723, 0.289754],
                "xyz": [3.366624690042, 1.811686598018, 1.248946734312],
                "label": "Li",
                "properties": {"magmom": 0.0},
            },
            {
                "species": [{"element": "V", "occu": 1}],
                "abc": [0.002829, 0.002889, 0.002583],
                "xyz": [0.032299483092, 0.017553148488, 0.011163647361],
                "label": "V",
                "properties": {"magmom": 1.822},
            },
            {
                "species": [{"element": "V", "occu": 1}],
                "abc": [0.497023, 0.497129, 0.496949],
                "xyz": [5.775322898978, 3.108235001366, 2.142052348793],
                "label": "V",
                "properties": {"magmom": 0.291},
            },
            {
                "species": [{"element": "Cr", "occu": 1}],
                "abc": [0.800992, 0.801121, 0.800921],
                "xyz": [9.307410854317, 5.009058358229, 3.452287806752],
                "label": "Cr",
                "properties": {"magmom": 2.948},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.104164, 0.717562, 0.396711],
                "xyz": [3.999031218498, 3.906347026614, 1.711814416399],
                "label": "O",
                "properties": {"magmom": -0.038},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.396728, 0.104138, 0.717446],
                "xyz": [4.696265954074, 1.690600108346, 3.041710772892],
                "label": "O",
                "properties": {"magmom": -0.038},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.71749, 0.396745, 0.104174],
                "xyz": [5.461890267919, 2.021780934611, 0.497952139625],
                "label": "O",
                "properties": {"magmom": -0.038},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.224799, 0.614334, 0.852489],
                "xyz": [5.743162992543, 4.204837813527, 3.627831847506],
                "label": "O",
                "properties": {"magmom": -0.039},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.614494, 0.852548, 0.224618],
                "xyz": [6.673020312326, 4.27168025471, 1.02345426386],
                "label": "O",
                "properties": {"magmom": -0.039},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.852549, 0.22461, 0.614354],
                "xyz": [7.240148040169, 2.100337722125, 2.639574010687],
                "label": "O",
                "properties": {"magmom": -0.039},
            },
        ],
    }
    test_struc = Structure.from_dict(d)
    return test_struc


def test_piezoelectric(piezoelectric_structure):

    piezo_static = [
        [0.27293, -0.27421, 0.00012, 0.32803, 0.12232, -0.08524],
        [0.29368, -0.29275, -0.00089, -0.28907, -0.0855, -0.12493],
        [-0.07653, -0.07875, 0.40994, 2e-05, -0.0012, -0.00083],
    ]

    piezo_ionic = [
        [0.34729, -0.36294, 0.00278, -0.57694, 0.6715, 0.97319],
        [-0.70181, 0.71666, 0.0057, -0.48873, 0.97987, -0.69311],
        [-0.15085, -0.16454, -0.14807, 0.00377, 0.01359, -0.00901],
    ]

    doc = PiezoelectricDoc.from_ionic_and_electronic(
        material_id="mp-149",
        structure=piezoelectric_structure,
        electronic=piezo_static,
        ionic=piezo_ionic,
        deprecated=False,
    )

    assert isinstance(doc, PiezoelectricDoc)
    assert doc.property_name == "piezoelectric"
    assert doc.material_id == "mp-149"
    assert doc.e_ij_max == pytest.approx(0.996797793183558)
    assert doc.strain_for_max == pytest.approx(
        [
            -0.430961014268001,
            -0.429606982527507,
            0.793542786483642,
            0.000388277044098721,
            0.000360213865028141,
            -0.000101249156585586,
        ]
    )

    total = [
        [
            -0.225596069393555,
            0.225265242692339,
            0.0,
            0.174554076170215,
            -0.133862660084444,
            0.409914022217545,
        ],
        [
            0.409753356720894,
            -0.409550646983409,
            0.0,
            -0.133492637969194,
            -0.174762236604771,
            0.225355751381697,
        ],
        [-0.429174669616753, -0.428637624953701, 0.791002009116969, 0.0, 0.0, 0.0],
    ]

    for i in range(3):
        assert doc.total[i] == pytest.approx(total[i])
