from emmet.api.routes.molecules.metal_binding.query_operators import BindingDataQuery


def test_binding_data_query():
    op = BindingDataQuery()
    assert op.query(
        metal_element="Li",
        metal_partial_charge_min=0.4,
        metal_partial_charge_max=1.2,
        metal_partial_spin_min=-0.2,
        metal_partial_spin_max=0.2,
        metal_assigned_charge_min=1.0,
        metal_assigned_charge_max=1.0,
        metal_assigned_spin_min=1.0,
        metal_assigned_spin_max=1.0,
        number_coordinate_bonds_min=1,
        number_coordinate_bonds_max=2,
        binding_energy_min=0.8,
        binding_energy_max=1.5,
        binding_enthalpy_min=-0.25,
        binding_enthalpy_max=0.25,
        binding_entropy_min=-0.002,
        binding_entropy_max=0.002,
        binding_free_energy_min=0.8,
        binding_free_energy_max=1.5,
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
