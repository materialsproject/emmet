
# Creation Code for Water System

Executed on Perlmutter

```python
from atomate2.openff.core import generate_interchange
import numpy as np
from jobflow import run_locally, Flow
from atomate2.openmm.flows.core import AnnealMaker, ProductionMaker
from atomate2.openmm.jobs.core import (
    EnergyMinimizationMaker,
    NPTMaker,
    NVTMaker,
)

charges = np.array([1.34, -0.39, -0.39, -0.39, -0.39, -0.39, -0.39])

mol_specs_dicts = [
    {"smile": "C1COC(=O)O1", "count": 100, "name": "EC"},
    {"smile": "CCOC(=O)OC", "count": 100, "name": "EMC"},
    {
        "smile": "F[P-](F)(F)(F)(F)F",
        "count": 50,
        "name":  "PF6",
        "partial_charges": charges,
        "geometry": "pf6.xyz",
        "charge_scaling": 0.8,
        "charge_method": "RESP",
    },
    {"smile": "[Li+]", "count": 50, "name": "Li", "charge_scaling": 0.8}
]

setup = generate_interchange(mol_specs_dicts, 1.3)


production_maker = ProductionMaker(
    name="test_production",
    energy_maker=EnergyMinimizationMaker(
        platform_name="CUDA",
        platform_properties={"DeviceIndex": "0"},
    ),
    npt_maker=NPTMaker(n_steps=50000),
    anneal_maker=AnnealMaker.from_temps_and_steps(n_steps=1000000),
    nvt_maker=NVTMaker(n_steps=500000),
)

production_flow = production_maker.make(
    setup.output.interchange,
    prev_task=setup.output,
    output_dir="/pscratch/sd/o/oac/ec_emc_test_dcd"
)

run_locally(Flow([setup, production_flow]), ensure_success=True)

```


We did not yet reduce the trajectory length but could with

```python
# Create a writer for the output DCD file
with mda.Writer("every_10th_frame.dcd", u.atoms.n_atoms) as writer:

    # Iterate over the trajectory with a step size of 10
    for ts in u.trajectory[::10]:
        # Write the current frame to the output DCD file
        writer.write(u.atoms)
```
