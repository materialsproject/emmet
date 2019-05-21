import itertools
import json
import sys
import time
from operator import itemgetter
from urllib.parse import quote

from mongogrant import Client
import numpy as np
from tqdm import tqdm

from emmet.common.utils import get_chemsys_space


html_out = len(sys.argv) > 1 and sys.argv[1] == 'html'
if html_out:
    sys_print = print

    def print(s=None):
        s = s or ""
        sys_print(s+"<br>")


print("Connecting to databases and retrieving on-hull materials...")
client = Client()
db_stag = client.db("ro:staging/mp_core")
db_prod = client.db("ro:production/mp_emmet_prod")

onhull_prod = db_prod.materials.distinct("task_id", {"e_above_hull": 0, "deprecated": {"$ne": True}})
onhull_stag = db_stag.materials.distinct("task_id", {"e_above_hull": 0, "deprecated": False})
onhull_prod_but_not_stag = set(onhull_prod) - set(onhull_stag)
print(f"{len(onhull_prod_but_not_stag)} on hull in production but not in staging")

print(f"Retrieving provenance of hull breaks...")
criteria = {"task_id": {"$in": list(onhull_prod_but_not_stag)}, "error": {"$exists": False}}
cursor = db_stag.materials.find(criteria, ["task_id", "chemsys"])
breaks_via_new_mats = []
breaks_via_old_mats_lower_e = []
breaks_via_old_mats_higher_e = []
for i, doc in tqdm(enumerate(cursor), total=db_stag.materials.count_documents(criteria)):
    broken = doc["task_id"]
    chemsys = doc["chemsys"]
    chemsys_space = get_chemsys_space(chemsys)
    to_be_on_hull = list(db_stag.materials.find(
        {'chemsys': {"$in": chemsys_space}, "e_above_hull": 0, "deprecated": False},
        ["task_id", "final_energy_per_atom"]))
    existing_mats = list(db_prod.materials.find(
        {'task_id': {"$in": [d["task_id"] for d in to_be_on_hull]}},
        ["task_id", "final_energy_per_atom"]))
    new_materials = {d["task_id"] for d in to_be_on_hull} - {d["task_id"] for d in existing_mats}
    for m in itertools.chain(to_be_on_hull, existing_mats):
        m["final_energy_per_atom"] = round(m["final_energy_per_atom"], 4)
    if not new_materials:
        lower_e = []
        for mat in existing_mats:
            new_final_e_per_atom = next(
                m["final_energy_per_atom"] for m in to_be_on_hull if m["task_id"] == mat["task_id"])
            if (not np.allclose([mat["final_energy_per_atom"]], [new_final_e_per_atom], atol=0.0005)  # 0.5 meV
                    and new_final_e_per_atom < mat["final_energy_per_atom"]):
                lower_e.append(dict(
                    mat=mat["task_id"],
                    e_change=round(mat["final_energy_per_atom"] - new_final_e_per_atom, 4)

                ))
        higher_e = []
        if len(lower_e) == 0:
            for m in existing_mats:
                m.pop("_id")
            broken_old_final_epa = db_prod.materials.find_one(
                {"task_id": broken, "deprecated": {"$ne": True}}, ["final_energy_per_atom"]) ["final_energy_per_atom"]
            try:
                broken_new_final_epa = db_stag.materials.find_one(
                    {"task_id": broken, "deprecated": False}, ["final_energy_per_atom"]) ["final_energy_per_atom"]
            except TypeError: # Newly deprecated
                continue
            higher_e = dict(old_mat=broken, e_change=round(broken_new_final_epa - broken_old_final_epa, 4))
            breaks_via_old_mats_higher_e.append(dict(
                mat=broken,
                e_change_higher=round(broken_new_final_epa - broken_old_final_epa, 4),
                chemsys=chemsys,
                existing_mats=existing_mats,
            ))
        else:
            breaks_via_old_mats_lower_e.append(dict(
                lower_e=sorted(lower_e, key=itemgetter("e_change"), reverse=True),
                mat=broken,
                chemsys=chemsys,
            ))
    else:
        try:
            new_hull_e = db_stag.materials.find_one({"task_id": broken, "deprecated": False}, ["e_above_hull"])["e_above_hull"]
        except TypeError: # Newly deprecated
            continue
        breaks_via_new_mats.append(dict(
            mat=broken,
            chemsys=chemsys,
            lower_e=list(new_materials),
            new_hull_e=round(new_hull_e, 4),
        ))

print("Done. Generating report...")
print()
time.sleep(2)


def as_html(b):
    mat_url = "https://zola.lbl.gov/materials/"
    pd_url = "https://zola.lbl.gov#apps/phasediagram/"

    def mat_link(mid):
        return f"<a href='{mat_url}{mid}'>{mid}</a>"

    def pd_link(chemsys):
        return f'<a href="{pd_url}{quote(json.dumps({"chemsys": chemsys.split("-")}))}">{chemsys}</a>'

    if "new_hull_e" in b:
        return (
            f'{mat_link(b["mat"])} ({pd_link(b["chemsys"])}) kicked off hull (now {b["new_hull_e"]} eV/a) '
            f'by new materials {[mat_link(mid) for mid in b["lower_e"]]}.'
        )
    elif "lower_e" in b:
        old_mats = ["{} (e_change={})".format(mat_link(changed["mat"]), changed["e_change"])
                    for changed in b["lower_e"]]
        return (
            f'{mat_link(b["mat"])} ({pd_link(b["chemsys"])}) kicked off hull '
            f'by old materials {old_mats}'
        )
    elif "e_change_higher" in b:
        return (
            f'{mat_link(b["mat"])} ({pd_link(b["chemsys"])}) kicked off hull '
            f'by self (e_change={b["e_change_higher"]})'
        )


format_output = as_html if html_out else lambda b: b

print(f"{len(breaks_via_old_mats_lower_e)} hull breaks due to now-lower-energy existing materials\n")
if breaks_via_old_mats_lower_e:
    print(f"In decreasing order of energy change:")
    breaks_via_old_mats_lower_e = sorted(
        breaks_via_old_mats_lower_e, key=lambda b: b['lower_e'][0]['e_change'], reverse=True)
    for b in breaks_via_old_mats_lower_e:
        print(format_output(b))
    print()

print(f"{len(breaks_via_old_mats_higher_e)} hull breaks due to now-higher-energy existing materials\n")
if breaks_via_old_mats_higher_e:
    print(f"These should concern you:\n")
    breaks_via_old_mats_higher_e = sorted(
        breaks_via_old_mats_higher_e, key=lambda b: b["e_change_higher"], reverse=True)
    for b in breaks_via_old_mats_higher_e:
        print(format_output(b))
    print()

print(f"{len(breaks_via_new_mats)} hull breaks due to new materials\n")
if breaks_via_new_mats:
    print(f"In decreasing order of hull energy change:")
    breaks_via_new_mats = sorted(
        breaks_via_new_mats, key=itemgetter('new_hull_e'), reverse=True)
    for b in breaks_via_new_mats:
        print(format_output(b))
    print()
