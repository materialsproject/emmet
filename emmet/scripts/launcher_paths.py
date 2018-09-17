import json
from atomate.vasp.database import VaspCalcDb

target_db_file = '../dbfiles/db_atomate.json'
target = VaspCalcDb.from_db_file(target_db_file, admin=True)
print('connected to target db with', target.collection.count(), 'tasks')
print(target.db.materials.count(), 'materials')

splits = ['block_', 'aflow_']
mpids = json.load(open('KRao_Li_FullList.txt', 'r'))
print(len(mpids), 'mpids')
query = {'task_id': {'$in': mpids}}

# {'mp-1002': [{'task_id': ..., 'task_type': ..., 'launcher_path': ...}, ...], ...}
out = {}

for idx, doc in enumerate(target.db.materials.find(query, {'task_id': 1, 'blessed_tasks': 1})):
    mp_id = doc['task_id']
    out[mp_id] = []
    print(idx, mp_id)
    for task_type, task_id in doc['blessed_tasks'].items():
        dir_name = target.collection.find_one({'task_id': task_id}, {'dir_name': 1})['dir_name']
        if 'maarten_piezo' in dir_name:
            continue
        for s in splits:
            ds = dir_name.split(s)
            if len(ds) == 2:
                launcher = s + ds[-1]
                print(task_id, task_type, launcher)
                out[mp_id].append({'task_id': task_id, 'task_type': task_type, 'launcher_path': launcher})
                break

with open('launcher_paths.json', 'w') as f:
    json.dump(out, f)

with open('launcher_paths.txt', 'w') as f:
    for mp_id, tasks in out.items():
        for task in tasks:
            f.write(task['launcher_path']+'\n')
