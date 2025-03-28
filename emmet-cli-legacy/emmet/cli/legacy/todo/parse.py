#     # fix year tags before copying tasks
#     counter = Counter()
#     source_tasks = source.collection.find(
#         {"$and": [{"tags": {"$in": tags}}, {"tags": {"$nin": year_tags}}]},
#         {"_id": 0, "dir_name": 1},
#     )
#     for idx, doc in enumerate(source_tasks):
#         print(idx, doc["dir_name"])
#         # check whether I copied it over to production already -> add tag for previous year
#         # anything not copied is tagged with the current year
#         prod_task = target.collection.find_one(
#             {"dir_name": doc["dir_name"]}, {"dir_name": 1, "tags": 1}
#         )
#         year_tag = year_tags[-1]
#         if prod_task:
#             print(prod_task["tags"])
#             for t in prod_task["tags"]:
#                 if t in year_tags:
#                     year_tag = t
#         r = source.collection.update(
#             {"dir_name": doc["dir_name"]}, {"$addToSet": {"tags": year_tag}}
#         )
#         counter[year_tag] += r["nModified"]
#     if counter:
#         print(counter, "year tags fixed.")


#         query = {"$and": [{"tags": t}, task_base_query]}
#         source_count = source.collection.count(query)
#         row += [source_count, target.collection.count(query)]
#

#         # skip tasks with task_id existing in target and with matching dir_name (have to be a string [mp-*, mvc-*])
#         nr_source_mp_tasks, skip_task_ids = 0, []
#         for doc in source.collection.find(query, ["task_id", "dir_name"]):
#             if isinstance(doc["task_id"], str):
#                 nr_source_mp_tasks += 1
#                 task_query = {
#                     "task_id": doc["task_id"],
#                     "$or": [
#                         {"dir_name": doc["dir_name"]},
#                         {"_mpworks_meta": {"$exists": 0}},
#                     ],
#                 }
#                 if target.collection.count(task_query):
#                     skip_task_ids.append(doc["task_id"])
#         # if len(skip_task_ids):
#         #    print('skip', len(skip_task_ids), 'existing MP task ids out of', nr_source_mp_tasks)

#         query.update({"task_id": {"$nin": skip_task_ids}})
#         already_inserted_subdirs = [
#             get_subdir(dn) for dn in target.collection.find(query).distinct("dir_name")
#         ]

#         subdirs = []
#         # NOTE make sure it's latest task if re-parse forced
#         fields = ["task_id", "retired_task_id"]
#         project = dict((k, True) for k in fields)
#         project["subdir"] = {
#             "$let": {  # gets launcher from dir_name
#                 "vars": {"dir_name": {"$split": ["$dir_name", "/"]}},
#                 "in": {"$arrayElemAt": ["$$dir_name", -1]},
#             }
#         }
#         group = dict((k, {"$last": f"${k}"}) for k in fields)  # based on ObjectId
#         group["_id"] = "$subdir"
#         group["count"] = {"$sum": 1}
#         pipeline = [{"$match": query}, {"$project": project}, {"$group": group}]
#         if force:
#             pipeline.append(
#                 {"$match": {"count": {"$gt": 1}}}
#             )  # only re-insert if duplicate parse exists

#         for doc in source.collection.aggregate(pipeline):
#             subdir = doc["_id"]
#             if (
#                 force
#                 or subdir not in already_inserted_subdirs
#                 or doc.get("retired_task_id")
#             ):
#                 entry = dict((k, doc[k]) for k in fields)
#                 entry["subdir"] = subdir
#                 subdirs.append(entry)
#         if len(subdirs) < 1:
#             print("no tasks to copy.")
#             continue

#         for subdir_doc in subdirs:
#             subdir_query = {"dir_name": {"$regex": "/{}$".format(subdir_doc["subdir"])}}
#             doc = target.collection.find_one(
#                 subdir_query, {"task_id": 1, "completed_at": 1}
#             )
#
#             if (
#                 doc
#                 and subdir_doc.get("retired_task_id")
#                 and subdir_doc["task_id"] != doc["task_id"]
#             ):
#                 # overwrite integer task_id (see wflows subcommand)
#                 # in this case, subdir_doc['task_id'] is the task_id the task *should* have
#                 print(subdir_doc["subdir"], "already inserted as", doc["task_id"])
#                 if insert:
#                     target.collection.remove(
#                         {"task_id": subdir_doc["task_id"]}
#                     )  # remove task with wrong task_id if necessary
#                     target.collection.update(
#                         {"task_id": doc["task_id"]},
#                         {
#                             "$set": {
#                                 "task_id": subdir_doc["task_id"],
#                                 "retired_task_id": doc["task_id"],
#                                 "last_updated": datetime.utcnow(),
#                             },
#                             "$addToSet": {"tags": t},
#                         },
#                     )
#                 print(
#                     "replace(d) task_id", doc["task_id"], "with", subdir_doc["task_id"]
#                 )
#                 continue

#             if not force and doc:
#                 print(subdir_doc["subdir"], "already inserted as", doc["task_id"])
#                 continue

#             # NOTE make sure it's latest task if re-parse forced
#             source_task_id = (
#                 subdir_doc["task_id"]
#                 if force
#                 else source.collection.find_one(subdir_query, {"task_id": 1})["task_id"]
#             )
#             print("retrieve", source_task_id, "for", subdir_doc["subdir"])
#             task_doc = source.retrieve_task(source_task_id)

#             if doc:  # NOTE: existing dir_name (re-parse forced)
#                 if task_doc["completed_at"] == doc["completed_at"]:
#                     print(
#                         "re-parsed",
#                         subdir_doc["subdir"],
#                         "already re-inserted into",
#                         target.collection.full_name,
#                     )
#                     continue
#                 task_doc["task_id"] = doc["task_id"]
#                 if insert:
#                     target.collection.remove(
#                         {"task_id": doc["task_id"]}
#                     )  # TODO VaspCalcDb.remove_task to also remove GridFS entries
#                 print("REMOVE(d) existing task", doc["task_id"])
#             elif isinstance(task_doc["task_id"], int):  # new task
#                 if insert:
#                     next_tid = (
#                         max(
#                             [
#                                 int(tid[len("mp") + 1 :])
#                                 for tid in target.collection.distinct("task_id")
#                             ]
#                         )
#                         + 1
#                     )
#                     task_doc["task_id"] = "mp-{}".format(next_tid)
#             else:  # NOTE replace existing SO task with new calculation (different dir_name)
#                 task = target.collection.find_one(
#                     {"task_id": task_doc["task_id"]},
#                     ["orig_inputs", "output.structure"],
#                 )
#                 if task:
#                     task_label = task_type(task["orig_inputs"], include_calc_type=False)
#                     if task_label == "Structure Optimization":
#                         s1 = Structure.from_dict(task["output"]["structure"])
#                         s2 = Structure.from_dict(task_doc["output"]["structure"])
#                         if structures_match(s1, s2):
#                             if insert:
#                                 target.collection.remove(
#                                     {"task_id": task_doc["task_id"]}
#                                 )  # TODO VaspCalcDb.remove_task
#                             print("INFO: removed old task!")
#                         else:
#                             print("ERROR: structures do not match!")
#                             # json.dump({'old': s1.as_dict(), 'new': s2.as_dict()}, open('{}.json'.format(task_doc['task_id']), 'w'))
#                             continue
#                     else:
#                         print("ERROR: not a SO task!")
#                         continue
#
#
#             if insert:
#                 target.insert_task(task_doc, use_gridfs=True)
