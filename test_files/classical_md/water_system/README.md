
# Creation Code for Water System

Executed on Perlmutter

```python
from atomate2.classical_md.core import generate_interchange
import numpy as np
from jobflow import run_locally, Flow
from atomate2.classical_md.openmm.flows.core import AnnealMaker, ProductionMaker
from atomate2.classical_md.openmm.jobs.core import (
    EnergyMinimizationMaker,
    NPTMaker,
    NVTMaker,
)

mol_specs_dicts = [
    {"smile": "O", "count": 200, "name": "H2O"},
    {"smile": "[Na+]", "count": 50, "name": "Na", "charge_scaling": 0.9},
    {"smile": "[Cl-]", "count": 50, "name": "Cl", "charge_scaling": 0.9},
    {"smile": "[K+]", "count": 50, "name": "K", "charge_scaling": 0.9},
    {"smile": "[Br-]", "count": 50, "name": "Br", "charge_scaling": 0.9}
]

setup = generate_interchange(mol_specs_dicts, 1.3)


production_maker = ProductionMaker(
    name="test_production",
    energy_maker=EnergyMinimizationMaker(
        platform_name="CUDA",
        platform_properties={"DeviceIndex": "1"},
    ),
    npt_maker=NPTMaker(n_steps=100000),
    anneal_maker=AnnealMaker.from_temps_and_steps(),
    nvt_maker=NVTMaker(n_steps=2000000),
)

production_flow = production_maker.make(
    setup.output.interchange,
    prev_task=setup.output,
    output_dir="/pscratch/sd/o/oac/water_test_dcd"
)

run_locally(Flow([setup, production_flow]), ensure_success=True)
```


Then we reduced the trajectory length with

```python
# Create a writer for the output DCD file
with mda.Writer("every_10th_frame.dcd", u.atoms.n_atoms) as writer:

    # Iterate over the trajectory with a step size of 10
    for ts in u.trajectory[::10]:
        # Write the current frame to the output DCD file
        writer.write(u.atoms)
```
