from emmet.api.routes.molecules.metal_binding.query_operators import BindingDataQuery
from monty.tempfile import ScratchDir
from monty.serialization import loadfn, dumpfn


def test_binding_data_query():
    op = BindingDataQuery()
    assert op.query(
        metal_element="Li",
        min_metal_partial_charge=0.4,
        max_metal_partial_charge=1.2,
        min_metal_partial_spin=-0.2,
        max_metal_partial_spin=0.2,
        min_metal_assigned_charge=1.0,
        max_metal_assigned_charge=1.0,
        min_metal_assigned_spin=1.0,
        max_metal_assigned_spin=1.0,
        min_number_coordinate_bonds=1,
        max_number_coordinate_bonds=2,
        min_binding_energy=0.8,
        max_binding_energy=1.5,
        min_binding_enthalpy=-0.25,
        max_binding_enthalpy=0.25,
        min_binding_entropy=-0.002,
        max_binding_entropy=0.002,
        min_binding_free_energy=0.8,
        max_binding_free_energy=1.5,
    ) == {
        "criteria": {
            "binding_data.metal_element": "Li",
            "binding_data.metal_partial_charge": {"$gte": 0.4, "$lte": 1.2},
            "binding_data.metal_partial_spin": {"$gte": -0.2, "$lte": 0.2},
            "binding_data.metal_assigned_charge": {"$gte": 1.0, "$lte": 1.0},
            "binding_data.metal_assigned_spin": {"$gte": 1.0, "$lte": 1.0},
            "binding_data.number_coordinate_bonds": {"$gte": 1, "$lte": 2},
            "binding_data.binding_energy": {"$gte": 0.8, "$lte": 1.5},
            "binding_data.binding_enthalpy": {"$gte": -0.25, "$lte": 0.25},
            "binding_data.binding_entropy": {"$gte": -0.002, "$lte": 0.002},
            "binding_data.binding_free_energy": {"$gte": 0.8, "$lte": 1.5},
        }
    }

    with ScratchDir("."):
        dumpfn(op, "temp.json")
        new_op = loadfn("temp.json")
        assert new_op.query(
            metal_element="Li",
            min_metal_partial_charge=0.4,
            max_metal_partial_charge=1.2,
            min_metal_partial_spin=-0.2,
            max_metal_partial_spin=0.2,
            min_metal_assigned_charge=1.0,
            max_metal_assigned_charge=1.0,
            min_metal_assigned_spin=1.0,
            max_metal_assigned_spin=1.0,
            min_number_coordinate_bonds=1,
            max_number_coordinate_bonds=2,
            min_binding_energy=0.8,
            max_binding_energy=1.5,
            min_binding_enthalpy=-0.25,
            max_binding_enthalpy=0.25,
            min_binding_entropy=-0.002,
            max_binding_entropy=0.002,
            min_binding_free_energy=0.8,
            max_binding_free_energy=1.5,
        ) == {
            "criteria": {
                "binding_data.metal_element": "Li",
                "binding_data.metal_partial_charge": {"$gte": 0.4, "$lte": 1.2},
                "binding_data.metal_partial_spin": {"$gte": -0.2, "$lte": 0.2},
                "binding_data.metal_assigned_charge": {"$gte": 1.0, "$lte": 1.0},
                "binding_data.metal_assigned_spin": {"$gte": 1.0, "$lte": 1.0},
                "binding_data.number_coordinate_bonds": {"$gte": 1, "$lte": 2},
                "binding_data.binding_energy": {"$gte": 0.8, "$lte": 1.5},
                "binding_data.binding_enthalpy": {"$gte": -0.25, "$lte": 0.25},
                "binding_data.binding_entropy": {"$gte": -0.002, "$lte": 0.002},
                "binding_data.binding_free_energy": {"$gte": 0.8, "$lte": 1.5},
            }
        }
