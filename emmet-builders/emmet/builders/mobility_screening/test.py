from migration_graph import MigrationGraphBuilder
from maggma.stores.advanced_stores import MongograntStore
from maggma.stores.compound_stores import ConcatStore
from maggma.stores import MongoStore

acrt_store = MongograntStore("ro:mongodb07-ext.nersc.gov/fw_acr_mv","tasks",key="task_id")
acrt_store.connect()

jst_store = MongograntStore("ro:mongodb07-ext.nersc.gov/fw_acr_mv","js_tasks",key="task_id")
jst_store.connect()

tasks_store = ConcatStore(stores=[acrt_store,jst_store],key="task_id")
tasks_store.connect()

electrodes_store = MongograntStore("ro:mongodb07-ext.nersc.gov/fw_acr_mv","insertion_electrodes_vw2",key="battery_id")
electrodes_store.connect()

sandbox_store = MongoStore(database= "local_dev",collection_name= "sandbox", key="battery_id")
sandbox_store.connect()

battery_ids = ["js-47173_Mg","js-43005_Mg","js-18_Mg"] # "good” candidates from 1st iteration
battery_ids.extend(["11221_Mg","11823_Mg","9167_Mg","8697_Mg","9006_Mg"]) #  stable, variety of voltages
battery_ids.extend(["22355_Mg","21312_Mg","24083_Mg","22142_Mg","8861_Mg"])# unstable, varierty of voltages
mapbuilder = MigrationGraphBuilder(
    electrodes=electrodes_store,
    tasks=tasks_store,
    migration_graphs=sandbox_store,
    query= {"battery_id":{"$in":battery_ids}}
)

mapbuilder.run()
