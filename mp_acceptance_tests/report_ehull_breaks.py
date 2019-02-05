import itertools
import re
import time

from mongogrant import Client
import numpy as np
from tqdm import tqdm

from emmet.common.utils import get_chemsys_space

print("Connecting to databases and retrieving on-hull materials...")
client = Client()
db_stag = client.db("ro:staging/mp_core")
db_prod = client.db("ro:production/mp_emmet_prod")

onhull_prod = db_prod.materials.distinct("task_id", {"e_above_hull": 0})
onhull_stag = db_stag.materials.distinct("task_id", {"e_above_hull": 0})
onhull_prod_but_not_stag = set(onhull_prod) - set(onhull_stag)
print(f"{len(onhull_prod_but_not_stag)} on hull in production but not in staging")

print(f"Retrieving provenance of hull breaks...")
cursor = db_stag.materials.find({"task_id": {"$in": list(onhull_prod_but_not_stag)}}, ["task_id", "chemsys"])
breaks_via_new_mats = []
breaks_via_old_mats_lower_e = []
breaks_via_old_mats_higher_e = []
for i, doc in tqdm(enumerate(cursor), total=cursor.count()):
    broken = doc["task_id"]
    chemsys = doc["chemsys"]
    chemsys_space = get_chemsys_space(chemsys)
    to_be_on_hull = list(db_stag.materials.find(
        {'chemsys': {"$in": chemsys_space}, "e_above_hull": 0},
        ["task_id", "e_above_hull", "final_energy_per_atom"]))
    existing_mats = list(db_prod.materials.find(
        {'task_id': {"$in": [d["task_id"] for d in to_be_on_hull]}},
        ["task_id", "e_above_hull", "final_energy_per_atom"]))
    new_materials = {d["task_id"] for d in to_be_on_hull} - {d["task_id"] for d in existing_mats}
    for m in itertools.chain(to_be_on_hull, existing_mats):
        m["e_above_hull"] = round(m["e_above_hull"], 4)
        m["final_energy_per_atom"] = round(m["final_energy_per_atom"], 4)
    if not new_materials:
        changed = []
        for mat in existing_mats:
            new_final_e_per_atom = next(
                m["final_energy_per_atom"] for m in to_be_on_hull if m["task_id"] == mat["task_id"])
            if (not np.allclose([mat["final_energy_per_atom"]], [new_final_e_per_atom], atol=0.0005)  # 0.5 meV
                    and new_final_e_per_atom < mat["final_energy_per_atom"]):
                changed.append(
                    f'{mat["task_id"]} '
                    f'(ehull={mat["e_above_hull"]}, final_e_per_atom={mat["final_energy_per_atom"]}) '
                    f'now with lower final_e_per_atom={new_final_e_per_atom} '
                    f'(decrease of {round(mat["final_energy_per_atom"] - new_final_e_per_atom, 4)})'
                )
        if len(changed) == 0:
            for m in existing_mats:
                m.pop("_id")
            broken_old_final_e_per_atom = db_prod.materials.find_one(
                {"task_id": broken}, ["final_energy_per_atom"]) ["final_energy_per_atom"]
            broken_new_final_e_per_atom = db_stag.materials.find_one(
                {"task_id": broken}, ["final_energy_per_atom"]) ["final_energy_per_atom"]
            breaks_via_old_mats_higher_e.append(
                f"existing materials {existing_mats} kicked {broken} "
                f"(going from {round(broken_old_final_e_per_atom, 4)} to "
                f"{round(broken_new_final_e_per_atom, 4)} final e per atom) off {chemsys} hull!\n\n"
            )
        else:
            breaks_via_old_mats_lower_e.append(f"old materials {changed} kicked {broken} off {chemsys} hull!")
    breaks_via_new_mats.append(f"({i+1}) {broken} kicked off {chemsys} hull by new materials {new_materials}.")

breaks_via_old_mats_lower_e = sorted(
    breaks_via_old_mats_lower_e,
    key=lambda b: float(re.match(r".*decrease of ([^\)]+).*", b).group(1)),
    reverse=True
)

print("Done. Generating report...\n")
time.sleep(2)

print(f"{len(breaks_via_new_mats)} hull breaks due to new materials\n")
print(f"{len(breaks_via_old_mats_lower_e)} hull breaks due to now-lower-energy existing materials\n")
if breaks_via_old_mats_higher_e:
    print(f"In decreasing order of energy change:")
    for line in breaks_via_old_mats_lower_e:
        print(line)
    print()

print(f"{len(breaks_via_old_mats_higher_e)} hull breaks due to now-higher-energy existing materials\n")
if breaks_via_old_mats_higher_e:
    print(f"These should concern you:\n")
    for line in breaks_via_old_mats_higher_e:
        print(line)
