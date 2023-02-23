import os

from emmet.api.core.api import MAPI
from emmet.api.core.settings import MAPISettings
from maggma.stores import MongoURIStore

# from emmet.api.routes.mpcules.tasks.resources import (
#     task_resource,
#     task_deprecation_resource
# )
# from emmet.api.routes.mpcules.molecules.resources import (
#     find_molecule_resource,
#     find_molecule_connectivity_resource,
#     molecules_resource
# )
# from emmet.api.routes.mpcules.partial_charges.resources import charges_resource
# from emmet.api.routes.mpcules.partial_spins.resources import spins_resource
# from emmet.api.routes.mpcules.bonds.resources import bonds_resource
from emmet.api.routes.mpcules.summary.resources import summary_resource

from emmet.api.core.documentation import description, tags_meta


resources = {}

default_settings = MAPISettings()

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]
debug = default_settings.DEBUG

# allow db_uri to be set with a different protocol scheme
# but prepend with mongodb+srv:// if not otherwise specified
if len(db_uri.split("://", 1)) < 2:
    db_uri = "mongodb+srv://" + db_uri

if db_uri:

    # task_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="task_id", collection_name="mpcules_tasks",
    # )

    # assoc_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="molecule_id", collection_name="mpcules_assoc",
    # )

    # mol_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="molecule_id", collection_name="mpcules_molecules",
    # )

    # charges_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_charges",
    # )

    # spins_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_spins",
    # )

    # bonds_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_bonds",
    # )

    # orbital_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_orbitals",
    # )

    # redox_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_redox",
    # )

    # thermo_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_thermo",
    # )

    # vibes_store = MongoURIStore(
    #     uri=db_uri, database="mp_dev", key="property_id", collection_name="mpcules_vibes",
    # )

    summary_store = MongoURIStore(
        uri=db_uri, database="mp_dev", key="molecule_id", collection_name="mpcules_summary",
    )

else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")


mpcules_resources = list()

# TODO: transfer data to mp_dev so that these endpoints work
# # Tasks
# mpcules_resources.extend([task_resource(task_store), task_deprecation_resource(task_store)])

# # Molecules
# mpcules_resources.extend(
#     [
#         molecules_resource(mol_store),
#         find_molecule_resource(mol_store),
#         find_molecule_connectivity_resource(mol_store),
#     ]
# )

# # Partial charges
# mpcules_resources.extend([charges_resource(charges_store)])

# # Partial spins
# mpcules_resources.extend([spins_resource(spins_store)])

# # Bonds
# mpcules_resources.extend([bonds_resource(bonds_store)])

# Summary
mpcules_resources.extend([summary_resource(summary_store)])

resources.update({"mpcules": mpcules_resources})

# === MAPI setup

api = MAPI(resources=resources, debug=debug, description=description, tags_meta=tags_meta)
app = api.app
