import os
from emmet.api.core.settings import MAPISettings
from maggma.stores import MongoURIStore

from emmet.api.routes.molecules.tasks.resources import (
    task_resource,
    task_deprecation_resource,
    trajectory_resource,
)
from emmet.api.routes.molecules.association.resources import (
    find_molecule_assoc_resource,
    mol_assoc_resource,
)
from emmet.api.routes.molecules.molecules.resources import (
    find_molecule_resource,
    molecules_resource,
)
from emmet.api.routes.molecules.partial_charges.resources import charges_resource
from emmet.api.routes.molecules.partial_spins.resources import spins_resource
from emmet.api.routes.molecules.bonds.resources import bonding_resource
from emmet.api.routes.molecules.metal_binding.resources import metal_binding_resource
from emmet.api.routes.molecules.orbitals.resources import orbitals_resource
from emmet.api.routes.molecules.redox.resources import redox_resource
from emmet.api.routes.molecules.thermo.resources import thermo_resource
from emmet.api.routes.molecules.vibrations.resources import vibration_resource
from emmet.api.routes.molecules.summary.resources import summary_resource
from emmet.api.routes.legacy.jcesr.resources import jcesr_resource


resources = {}

default_settings = MAPISettings()

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]

if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    task_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="task_id",
        collection_name="molecules_tasks",
    )

    assoc_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="molecule_id",
        collection_name="molecules_assoc",
    )

    mol_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="molecule_id",
        collection_name="molecules_molecules",
    )

    charges_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_charges",
    )

    spins_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_spins",
    )

    bonds_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_bonds",
    )

    metal_binding_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_metal_binding",
    )

    orbitals_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_orbitals",
    )

    redox_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_redox",
    )

    thermo_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_thermo",
    )

    vibes_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="property_id",
        collection_name="molecules_vibes",
    )

    summary_store = MongoURIStore(
        uri=db_uri,
        database="mp_molecules",
        key="molecule_id",
        collection_name="molecules_summary",
    )

    jcesr_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="molecules"
    )

else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")


mp_molecules_resources = list()

# Tasks
mp_molecules_resources.extend(
    [
        task_resource(task_store),
        task_deprecation_resource(task_store),
        trajectory_resource(task_store),
    ]
)

# Assoc
mp_molecules_resources.extend(
    [mol_assoc_resource(assoc_store), find_molecule_assoc_resource(assoc_store)]
)

# Molecules
mp_molecules_resources.extend(
    [
        molecules_resource(mol_store),
        find_molecule_resource(mol_store),
    ]
)

# Partial charges
mp_molecules_resources.extend([charges_resource(charges_store)])

# Partial spins
mp_molecules_resources.extend([spins_resource(spins_store)])

# Bonds
mp_molecules_resources.extend([bonding_resource(bonds_store)])

# Metal binding
mp_molecules_resources.extend([metal_binding_resource(metal_binding_store)])

# Orbitals
mp_molecules_resources.extend([orbitals_resource(orbitals_store)])

# Redox
mp_molecules_resources.extend([redox_resource(redox_store)])

# Thermo
mp_molecules_resources.extend([thermo_resource(thermo_store)])

# Vibes
mp_molecules_resources.extend([vibration_resource(vibes_store)])

# Summary
mp_molecules_resources.extend([summary_resource(summary_store)])

# Legacy JCESR
mp_molecules_resources.extend([jcesr_resource(jcesr_store)])

resources.update({"molecules": mp_molecules_resources})
