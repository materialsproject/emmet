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
                [0.0, 5.077586, 0.0],
                [8.769167, 0.0, 0.0],
                [0.0, -1.7206, -4.819114],
            ],
            "a": 5.077586,
            "b": 8.769167,
            "c": 5.11706205795826,
            "alpha": 90.0,
            "beta": 109.648423669999,
            "gamma": 90.0,
            "volume": 214.576831815117,
        },
        "sites": [
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.5, 0.997223, 0.0],
                "xyz": [8.744815023241, 2.538793, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.0, 0.007335, 0.5],
                "xyz": [0.064321839945, -0.8603, -2.409557],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.5, 0.673599, 0.0],
                "xyz": [5.906902122033, 2.538793, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.0, 0.848636, 0.0],
                "xyz": [7.441830806212, 0.0, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.0, 0.497223, 0.0],
                "xyz": [4.360231523241, 0.0, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.5, 0.507335, 0.5],
                "xyz": [4.448905339945, 1.678493, -2.409557],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.0, 0.173599, 0.0],
                "xyz": [1.522318622033, 0.0, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Li", "occu": 1}],
                "abc": [0.5, 0.348636, 0.0],
                "xyz": [3.057247306212, 2.538793, 0.0],
                "label": "Li",
                "properties": {},
            },
            {
                "species": [{"element": "Fe", "occu": 1}],
                "abc": [0.5, 0.840139, 0.5],
                "xyz": [7.367319194213, 1.678493, -2.409557],
                "label": "Fe",
                "properties": {},
            },
            {
                "species": [{"element": "Fe", "occu": 1}],
                "abc": [0.0, 0.674037, 0.5],
                "xyz": [5.910743017179, -0.8603, -2.409557],
                "label": "Fe",
                "properties": {},
            },
            {
                "species": [{"element": "Fe", "occu": 1}],
                "abc": [0.0, 0.340139, 0.5],
                "xyz": [2.982735694213, -0.8603, -2.409557],
                "label": "Fe",
                "properties": {},
            },
            {
                "species": [{"element": "Fe", "occu": 1}],
                "abc": [0.5, 0.174037, 0.5],
                "xyz": [1.526159517179, 1.678493, -2.409557],
                "label": "Fe",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.779705, 0.500278, 0.268671],
                "xyz": [4.387021328426, 3.49674386953, -1.294756177494],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.720295, 0.000278, 0.731329],
                "xyz": [0.002437828426, 2.39903513047, -3.524357822506],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.755993, 0.189934, 0.270851],
                "xyz": [1.665562964978, 3.372593242298, -1.305261846014],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.744007, 0.689934, 0.729149],
                "xyz": [6.050146464978, 2.523185757702, -3.513852153986],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.766434, 0.333483, 0.723505],
                "xyz": [2.924368118661, 2.646771845324, -3.48665307457],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.733566, 0.833483, 0.276495],
                "xyz": [7.308951618661, 3.249007154676, -1.33246092543],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.279705, 0.000278, 0.268671],
                "xyz": [0.002437828426, 0.95795086953, -1.294756177494],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.220295, 0.500278, 0.731329],
                "xyz": [4.387021328426, -0.13975786953, -3.524357822506],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.255993, 0.689934, 0.270851],
                "xyz": [6.050146464978, 0.833800242298, -1.305261846014],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.244007, 0.189934, 0.729149],
                "xyz": [1.665562964978, -0.015607242298, -3.513852153986],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.266434, 0.833483, 0.723505],
                "xyz": [7.308951618661, 0.107978845324, -3.48665307457],
                "label": "O",
                "properties": {},
            },
            {
                "species": [{"element": "O", "occu": 1}],
                "abc": [0.233566, 0.333483, 0.276495],
                "xyz": [2.924368118661, 0.710214154676, -1.33246092543],
                "label": "O",
                "properties": {},
            },
        ],
    }
    test_struc = Structure.from_dict(d)
    return test_struc


def test_piezoelectric(piezoelectric_structure):
    piezo_static = [
        [0.07886, -0.07647, -0.01902, 0.0, -0.18077, 0.0],
        [0.0, 0.0, 0.0, -0.10377, 0.0, 0.18109],
        [0.0, 0.0, 0.0, -0.07831, 0.0, 0.04849],
    ]

    piezo_ionic = [
        [-0.53096, 0.12789, -0.01236, 0.0, 0.09352, 0.0],
        [-0.00013, 9e-05, 3e-05, 0.2681, 0.00042, -0.09373],
        [-0.00018, -9e-05, -0.00029, 0.15863, 0.0001, -0.22751],
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
    assert doc.e_ij_max == pytest.approx(0.464365904540805)
    assert [abs(n) for n in doc.strain_for_max] == pytest.approx(
        [
            0.0675760207481869,
            0.97358569089405,
            0.110731643941102,
            0.0,
            0.187890624929232,
            0.0,
        ]
    )

    total = [
        [0.0, 0.0, 0.0, 0.08032, 0.0, -0.17902],
        [-0.03138, -0.4521, 0.05142, 0.0, -0.08725, 0.0],
        [0.0, 0.0, 0.0, 0.16433, 0.0, 0.08736],
    ]

    for i in range(3):
        assert doc.total[i] == pytest.approx(total[i])
