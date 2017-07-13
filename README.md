# Emmet

> Be a master builder of databases of material properties. Avoid the Kragle.

The purpose of Emmet is to 'build' collections of materials properties from the output of computational materials calculations. Currently, the effective purpose of Emmet is to take the output of [VASP](http://vasp.at) electronic structure calculations to build MongoDB collections that back the [Materials Project](https://materialsproject.org) website and its apps.

Emmet uses [Maggma](https://github.com/materialsproject/maggma), our more general aggregation framework which abstracts away the behind-the-scenes machinery: Maggma provides our `Builder` class and a general interface to Stores, which can be MongoDB collections or plain JSON files.

The `Builder` takes `source` Store(s), processes items in that store, and then builds results to `target` Store(s). 

To ease debugging, in Emmet data flows in *one direction* only: this means that each Store is only built by a specific builder, and will not then be modified by successive builders.

Builders are designed to be run periodically and automatically: as such, Stores have a 'last updated' filter (`lu_filter`) so that we only attempt to process new entries in the Store.

Emmet is currently primarily an internal Materials Project tool so if you're reading this you might have just joined the group, in which case: welcome! :-)

## Table of Contents

1. [Installation](#installation)
2. [VASP Builders](#vasp-builders) 
3. [Running a Builder](#running-a-builder)
4. [Writing a New Builder](#writing-a-new-builder)

## Installation

Emmet is on PyPI, so `pip install emmet` should work. However, it is currently in very active development, so cloning the git repo and `python setup.py develop` is recommended for now.

## VASP Builders


### Overview

![Overview Flowchart: Vasp Output Directory leads to Tasks Store (via VaspDrone, atomate.vasp.drones), Tasks Store with Materials Setting Store and StructureNLs Store leads to Materials Store (via MaterialsBuilder, emmet.vasp.builders.materials), Materials Store leads to Thermo Store (via ThermoBuilder, emmet.vasp.builders.thermo), Materials Store leads to Elastic Store (via ElasticBuidler, emmet.vasp.builders.elastic), Materials Store leads to Diffraction Store (via DiffractionBuilder, emmet.vasp.builders.diffraction), Materials Store leads to Dielectric Store (via DielectricStore, emmet.vasp.builders.dielectric)](docs/images/EmmetBuilders.png)

### MaterialsBuilder

**Source(s)** `tasks` (typically `tasks` collection), `material_settings` (typically [`mat.json`](vasp/builders/mat.json)), `snls` (optional)

**Target(s)** `materials` (typically `materials` collection)

##### What MaterialsBuilder does:

1. Filters to only include tasks that completed successfuly.

2. Groups tasks into those for the same structure.

	Structure matching first only selects materials that have the same chemical formula, and then uses pymatgen's `StructureMatcher` to perform symmetry analysis.
	
3. For each property, ranks tasks for a given structure according to those that are expected to predict the property more accurately (for example, a band gap from a band structure calculation is ranked higher than a band gap from a generic calculation). This value is then picked as the canonical value for that property.

	The `task_type` is already determined and comes from the tasks store, and the rankings are specified in [`mat.json`](vasp/builders/mat.json). No attempt is made to rank which task of the same `task_type` is best; in this case it is assumed that the most recent calculation takes precendence.
	
4. *(Optional)* The [Structure Notation Language](http://pymatgen.org/pymatgen.matproj.snl.html#pymatgen.matproj.snl.StructureNL) (or 'SNLs') provide a way to bundle a structure and its metadata (such as bibtex references for where the structure came from) within the Materials Project. This will lookup if there are existing SNL(s) for the structure, and assign an SNL accordingly.


##### Sample MaterialsBuilder output:

Property | Key Path | Example | Validation | Comment
-------- | -------- | ------- | ---------- | -------
anonymous formula | `anonymous_formula` | | str, required | 
band gap / eV | `bandstructure.band_gap` | | float, > 0, required | Always from GGA calculation
conduction band minimum / eV  | `bandstructure.cbm` | | float, optional |
etc. (to add) |

### ThermoBuilder

**Source(s)** `materials`

**Target(s)** `thermo`

##### What ThermoBuilder does:

1. Groups materials into those in the same chemical system (that is, materials whose crystal structure contain the same elements).

2. Filters out materials that can not be directly compared to each other, e.g. they've been calculated by different methods such that their total energies are on different scales.

	By default, this is done by using [`MaterialsProjectCompatibility('Advanced')`](http://pymatgen.org/pymatgen.entries.compatibility.html#pymatgen.entries.compatibility.MaterialsProjectCompatibility) in pymatgen, which intelligently mixes GGA and GGA+U calculations depending on the elements present, and performs corrections to the total energy as appropriate.
	
3. Uses pymatgen's [`phasediagram`](http://pymatgen.org/pymatgen.phasediagram.html) package to calculate the [energy above hull](https://materialsproject.org/wiki/index.php/Glossary_of_Terms#Energetics) for each material and, if the material is unstable, its decomposition pathway. 
 
##### Sample ThermoBuilder output:

Property | Key Path | Example | Validation | Comment
-------- | -------- | ------- | ---------- | -------
material id | `material_id` | | | matches `material_id` from `materials`
formation energy per atom / eV | `formation_energy_per_atom`
energy above hull / eV | `thermo.e_above_hull` | 
is stable | `thermo.is_stable` | true | bool, required
equilibrium reaction energy | `thermo.eq_reaction_e`
decomposition pathway | `thermo.decomposes_to` | | list, can be empty | each element of list is dictionary with `material_id`, `formula`, `amount` where `amount` is float in interval [0,1] 


### ElasticBuilder

**Source(s)** `materials`

**Target(s)** `elastic`

##### What ElasticBuilder does:

1. Selects an initial structure from materials
2. Finds deformed instances of this initial structure from materials, and calculates the deformation matrix
3. If 6 independent deformations are found, calculates the elastic tensor using pymatgen's [`ElasticTensor`](http://pymatgen.org/pymatgen.analysis.elasticity.elastic.html#pymatgen.analysis.elasticity.elastic.ElasticTensor)

##### Sample ElasticBuilder output:

Property | Key Path | Example | Validation | Comment
-------- | -------- | ------- | ---------- | -------
material id | `material_id` | | | material id for initial structure, matches `material_id` from `materials`
elastic tensor | `elasticity.elastic_tensor` | | list | in Voigt notation
material ids for deformed structures | `elasticity.material_ids` | | list | material ids for deformed structures

### Diffraction Builder

**Source(s)** `materials`, `xrd_settings` (typically [`xrd.json`](vasp/builders/xrd.json))

**Target(s)** `diffraction`

##### What DiffractionBuilder does:

1. For each structure, calculates its ideal X-ray diffraction pattern for a variety of X-ray targets (specified in [`xrd.json`](vasp/builders/xrd.json))

##### Sample DiffractionBuilder output:
Property | Key Path | Example | Validation | Comment
-------- | -------- | ------- | ---------- | -------
material id | `material_id` | | | matches `material_id` from `materials`
to add |


## Running a Builder

Here is a sample script for running the MaterialsBuilder. Replace `"..."` as appropriate.

```python
#!/usr/bin/env python

from maggma.runner import Runner
from maggma.stores import MongoStore, JSONStore
from emmet.vasp.builders.materials import MaterialsBuilder

tasks_store = MongoStore(database="...",
                         collection="materials",
                         host="...",
                         port=27017,
                         username="...",
                         password="...")
materials_settings_store = JSONStore("mat.json")
materials_store = MongoStore(database="...",
                             collection="tasks",
                             port=27017,
                             username="...",
                             password="...")

builder = MaterialsBuilder(tasks_store,
                           materials_settings_store,
                           materials_store)

runner = Runner([builder])

runner.run()

```

## Writing a New Builder

Sub-class the [`Builder`](https://github.com/materialsproject/maggma/blob/master/maggma/builder.py) base class and implement its methods. The [`DiffractionBuilder`](https://github.com/materialsproject/emmet/blob/master/emmet/vasp/builders/diffraction.py) is a nice simple builder to copy from to get started.