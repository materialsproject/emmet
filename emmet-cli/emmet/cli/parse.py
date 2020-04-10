def get_timestamp_dir(prefix="launcher"):
    time_now = datetime.utcnow().strftime(FW_BLOCK_FORMAT)
    return "_".join([prefix, time_now])


def contains_vasp_dirs(list_of_files):
    for f in list_of_files:
        if f.startswith("INCAR"):
            return True


def clean_path(path):
    return os.path.join(os.path.abspath(os.path.realpath(path)), "")  # trailing slash


def make_block(base_path):
    block = get_timestamp_dir(prefix="block")
    block_dir = os.path.join(base_path, block)
    os.mkdir(block_dir)
    print("created", block_dir)
    return block_dir


# TODO move fake-block creation to separate command
def get_symlinked_path(root, base_path_index, insert):
    """organize directory in block_*/launcher_* via symbolic links"""
    root_split = root.split(os.sep)
    base_path = os.sep.join(root_split[:base_path_index])

    if not root_split[base_path_index].startswith("block_"):
        all_blocks = glob(os.path.join(base_path, "block_*/"))
        if all_blocks:
            for block_dir in all_blocks:
                nr_launchers = len(glob(os.path.join(block_dir, "launcher_*/")))
                if nr_launchers < 300:
                    break  # found an existing block with < 300 launchers
            else:
                block_dir = make_block(base_path)
        else:
            block_dir = make_block(base_path)
    else:
        block_dir = os.sep.join(root_split[: base_path_index + 1])

    if not root_split[-1].startswith("launcher_"):
        launch = get_timestamp_dir(prefix="launcher")
        launch_dir = os.path.join(block_dir, launch)
        if insert:
            os.rename(root, launch_dir)
            os.symlink(launch_dir, root)
        print(root, "->", launch_dir)
    else:
        launch_dir = os.path.join(block_dir, root_split[-1])
        if not os.path.exists(launch_dir):
            if insert:
                os.rename(root, launch_dir)
            print(root, "->", launch_dir)

    return launch_dir


def get_vasp_dirs(scan_path, base_path, max_dirs, insert):
    scan_path = clean_path(scan_path)
    base_path = clean_path(base_path)
    base_path_index = len(base_path.split(os.sep)) - 1  # account for abspath
    counter = 0

    # NOTE os.walk followlinks=False by default, as intended here
    for root, dirs, files in os.walk(scan_path, topdown=True):
        if contains_vasp_dirs(files):
            yield get_symlinked_path(root, base_path_index, insert)
            counter += 1
            if counter >= max_dirs:
                break
            dirs[:] = []  # don't descend further (i.e. ignore relax1/2)
        else:
            print(root, "does not contain INCAR!")
            # for f in files:
            #    if f.endswith('.tar.gz'):
            #        cwd = os.path.realpath(root)
            #        path = os.path.join(cwd, f)
            #        with tarfile.open(path, 'r:gz') as tf:
            #            tf.extractall(cwd)
            #        os.remove(path)
            #        for vaspdir in get_vasp_dirs(path.replace('.tar.gz', ''), base_path, max_dirs, insert):
            #            yield vaspdir
            #            counter += 1
            #            if counter >= max_dirs:
            #                break


def parse_vasp_dirs(vaspdirs, insert, drone, already_inserted_subdirs, delete):
    name = multiprocessing.current_process().name
    print(name, "starting")
    lpad = get_lpad()
    target = calcdb_from_mgrant(f"{lpad.host}/{lpad.name}")
    print(name, "connected to target db with", target.collection.count(), "tasks")
    input_structures = []

    for vaspdir in vaspdirs:
        if get_subdir(vaspdir) in already_inserted_subdirs:
            print(name, vaspdir, "already parsed")
            if delete:
                rmtree(vaspdir)
                print(name, "removed", vaspdir)
            continue
        print(name, "vaspdir:", vaspdir)

        if insert:
            try:
                for inp in ["INCAR", "KPOINTS", "POTCAR", "POSCAR"]:
                    input_path = os.path.join(vaspdir, inp)
                    if not glob(input_path + ".orig*"):
                        input_path = glob(input_path + "*")[0]
                        orig_path = input_path.replace(inp, inp + ".orig")
                        copyfile(input_path, orig_path)
                        print(name, "cp", input_path, "->", orig_path)
            except Exception as ex:
                print(str(ex))
                continue

            try:
                task_doc = drone.assimilate(vaspdir)
            except Exception as ex:
                err = str(ex)
                if err == "No VASP files found!":
                    rmtree(vaspdir)
                    print(name, "removed", vaspdir)
                continue

            s = Structure.from_dict(task_doc["input"]["structure"])
            input_structures.append(s)

            q = {"dir_name": {"$regex": get_subdir(vaspdir)}}
            # check completed_at timestamp to decide on re-parse (only relevant for --force)
            docs = list(
                target.collection.find(q, {"completed_at": 1})
                .sort([("_id", -1)])
                .limit(1)
            )
            if docs and docs[0]["completed_at"] == task_doc["completed_at"]:
                print(
                    "not forcing insertion of",
                    vaspdir,
                    "(matching completed_at timestamp)",
                )
                continue

            # make sure that task gets the same tags as the previously parsed task (only relevant for --force)
            tags = target.collection.distinct("tags", q)
            if tags:
                print("use existing tags:", tags)
                task_doc["tags"] = tags

            if task_doc["state"] == "successful":
                try:
                    target.insert_task(task_doc, use_gridfs=True)
                except DocumentTooLarge as ex:
                    print(name, "remove normalmode_eigenvecs and retry ...")
                    task_doc["calcs_reversed"][0]["output"].pop("normalmode_eigenvecs")
                    try:
                        target.insert_task(task_doc, use_gridfs=True)
                    except DocumentTooLarge as ex:
                        print(name, "also remove force_constants and retry ...")
                        task_doc["calcs_reversed"][0]["output"].pop("force_constants")
                        target.insert_task(task_doc, use_gridfs=True)

                if delete and target.collection.count(q):
                    print(name, "successfully parsed", vaspdir)
                    rmtree(vaspdir)
                    print(name, "removed", vaspdir)

    print(
        name,
        "processed",
        len(vaspdirs),
        "VASP directories -",
        len(input_structures),
        "structures",
    )
    return input_structures


def copy(target_spec, tag, insert, copy_snls, sbxn, src, force):

    # fix year tags before copying tasks
    counter = Counter()
    source_tasks = source.collection.find(
        {"$and": [{"tags": {"$in": tags}}, {"tags": {"$nin": year_tags}}]},
        {"_id": 0, "dir_name": 1},
    )
    for idx, doc in enumerate(source_tasks):
        print(idx, doc["dir_name"])
        # check whether I copied it over to production already -> add tag for previous year
        # anything not copied is tagged with the current year
        prod_task = target.collection.find_one(
            {"dir_name": doc["dir_name"]}, {"dir_name": 1, "tags": 1}
        )
        year_tag = year_tags[-1]
        if prod_task:
            print(prod_task["tags"])
            for t in prod_task["tags"]:
                if t in year_tags:
                    year_tag = t
        r = source.collection.update(
            {"dir_name": doc["dir_name"]}, {"$addToSet": {"tags": year_tag}}
        )
        counter[year_tag] += r["nModified"]
    if counter:
        print(counter, "year tags fixed.")

    target_snls = target.db.snls_user

    def insert_snls(snls_list):
        if snls_list:
            print("copy", len(snls_list), "SNLs")
            if insert:
                result = target_snls.insert_many(snls_list)
                print("#SNLs inserted:", len(result.inserted_ids))
            snls_list.clear()
        else:
            print("no SNLs to insert")

    table = PrettyTable()
    table.field_names = ["Tag", "Source", "Target", "Skipped", "Insert"]
    sums = ["total"] + [0] * (len(table.field_names) - 1)

    for t in tags:

        print("- {}".format(t))
        row = [t]
        query = {"$and": [{"tags": t}, task_base_query]}
        source_count = source.collection.count(query)
        row += [source_count, target.collection.count(query)]

        # get list of SNLs to copy over
        # only need to check tagged SNLs in source and target; dup-check across SNL collections already done in add_snls
        # also only need to check about.projects; add_snls adds tag to about.projects and not remarks
        # TODO only need to copy if author not Materials Project!?
        if copy_snls:
            snls = lpad.db.snls.find({"about.projects": t})
            nr_snls = snls.count()
            if nr_snls:
                snls_to_copy, index, prefix = [], None, "snl"
                for idx, doc in enumerate(snls):
                    snl = StructureNL.from_dict(doc)
                    formula = snl.structure.composition.reduced_formula
                    snl_copied = False
                    try:
                        q = {
                            "about.projects": t,
                            "$or": [{k: formula} for k in aggregation_keys],
                        }
                        group = aggregate_by_formula(
                            target_snls, q
                        ).next()  # only one formula
                        for dct in group["structures"]:
                            existing_structure = Structure.from_dict(dct)
                            if structures_match(snl.structure, existing_structure):
                                snl_copied = True
                                print("SNL", doc["snl_id"], "already added.")
                                break
                    except StopIteration:
                        pass
                    if snl_copied:
                        continue
                    snl_dct = snl.as_dict()
                    if index is None:
                        index = (
                            max(
                                [
                                    int(snl_id[len(prefix) + 1 :])
                                    for snl_id in target_snls.distinct("snl_id")
                                ]
                            )
                            + 1
                        )
                    else:
                        index += 1
                    snl_id = "{}-{}".format(prefix, index)
                    snl_dct["snl_id"] = snl_id
                    snl_dct.update(get_meta_from_structure(snl.structure))
                    snls_to_copy.append(snl_dct)
                    if idx and not idx % 100 or idx == nr_snls - 1:
                        insert_snls(snls_to_copy)
            else:
                print("No SNLs available for", t)

        # skip tasks with task_id existing in target and with matching dir_name (have to be a string [mp-*, mvc-*])
        nr_source_mp_tasks, skip_task_ids = 0, []
        for doc in source.collection.find(query, ["task_id", "dir_name"]):
            if isinstance(doc["task_id"], str):
                nr_source_mp_tasks += 1
                task_query = {
                    "task_id": doc["task_id"],
                    "$or": [
                        {"dir_name": doc["dir_name"]},
                        {"_mpworks_meta": {"$exists": 0}},
                    ],
                }
                if target.collection.count(task_query):
                    skip_task_ids.append(doc["task_id"])
        # if len(skip_task_ids):
        #    print('skip', len(skip_task_ids), 'existing MP task ids out of', nr_source_mp_tasks)
        row.append(len(skip_task_ids))

        query.update({"task_id": {"$nin": skip_task_ids}})
        already_inserted_subdirs = [
            get_subdir(dn) for dn in target.collection.find(query).distinct("dir_name")
        ]
        subdirs = []
        # NOTE make sure it's latest task if re-parse forced
        fields = ["task_id", "retired_task_id"]
        project = dict((k, True) for k in fields)
        project["subdir"] = {
            "$let": {  # gets launcher from dir_name
                "vars": {"dir_name": {"$split": ["$dir_name", "/"]}},
                "in": {"$arrayElemAt": ["$$dir_name", -1]},
            }
        }
        group = dict((k, {"$last": f"${k}"}) for k in fields)  # based on ObjectId
        group["_id"] = "$subdir"
        group["count"] = {"$sum": 1}
        pipeline = [{"$match": query}, {"$project": project}, {"$group": group}]
        if force:
            pipeline.append(
                {"$match": {"count": {"$gt": 1}}}
            )  # only re-insert if duplicate parse exists
        for doc in source.collection.aggregate(pipeline):
            subdir = doc["_id"]
            if (
                force
                or subdir not in already_inserted_subdirs
                or doc.get("retired_task_id")
            ):
                entry = dict((k, doc[k]) for k in fields)
                entry["subdir"] = subdir
                subdirs.append(entry)
        if len(subdirs) < 1:
            print("no tasks to copy.")
            continue

        row.append(len(subdirs))
        table.add_row(row)
        for idx, e in enumerate(row):
            if isinstance(e, int):
                sums[idx] += e
        # if not insert: # avoid uncessary looping
        #    continue

        for subdir_doc in subdirs:
            subdir_query = {"dir_name": {"$regex": "/{}$".format(subdir_doc["subdir"])}}
            doc = target.collection.find_one(
                subdir_query, {"task_id": 1, "completed_at": 1}
            )

            if (
                doc
                and subdir_doc.get("retired_task_id")
                and subdir_doc["task_id"] != doc["task_id"]
            ):
                # overwrite integer task_id (see wflows subcommand)
                # in this case, subdir_doc['task_id'] is the task_id the task *should* have
                print(subdir_doc["subdir"], "already inserted as", doc["task_id"])
                if insert:
                    target.collection.remove(
                        {"task_id": subdir_doc["task_id"]}
                    )  # remove task with wrong task_id if necessary
                    target.collection.update(
                        {"task_id": doc["task_id"]},
                        {
                            "$set": {
                                "task_id": subdir_doc["task_id"],
                                "retired_task_id": doc["task_id"],
                                "last_updated": datetime.utcnow(),
                            },
                            "$addToSet": {"tags": t},
                        },
                    )
                print(
                    "replace(d) task_id", doc["task_id"], "with", subdir_doc["task_id"]
                )
                continue

            if not force and doc:
                print(subdir_doc["subdir"], "already inserted as", doc["task_id"])
                continue

            # NOTE make sure it's latest task if re-parse forced
            source_task_id = (
                subdir_doc["task_id"]
                if force
                else source.collection.find_one(subdir_query, {"task_id": 1})["task_id"]
            )
            print("retrieve", source_task_id, "for", subdir_doc["subdir"])
            task_doc = source.retrieve_task(source_task_id)

            if doc:  # NOTE: existing dir_name (re-parse forced)
                if task_doc["completed_at"] == doc["completed_at"]:
                    print(
                        "re-parsed",
                        subdir_doc["subdir"],
                        "already re-inserted into",
                        target.collection.full_name,
                    )
                    table._rows[-1][-1] -= 1  # update Insert count in table
                    continue
                task_doc["task_id"] = doc["task_id"]
                if insert:
                    target.collection.remove(
                        {"task_id": doc["task_id"]}
                    )  # TODO VaspCalcDb.remove_task to also remove GridFS entries
                print("REMOVE(d) existing task", doc["task_id"])
            elif isinstance(task_doc["task_id"], int):  # new task
                if insert:
                    next_tid = (
                        max(
                            [
                                int(tid[len("mp") + 1 :])
                                for tid in target.collection.distinct("task_id")
                            ]
                        )
                        + 1
                    )
                    task_doc["task_id"] = "mp-{}".format(next_tid)
            else:  # NOTE replace existing SO task with new calculation (different dir_name)
                task = target.collection.find_one(
                    {"task_id": task_doc["task_id"]},
                    ["orig_inputs", "output.structure"],
                )
                if task:
                    task_label = task_type(task["orig_inputs"], include_calc_type=False)
                    if task_label == "Structure Optimization":
                        s1 = Structure.from_dict(task["output"]["structure"])
                        s2 = Structure.from_dict(task_doc["output"]["structure"])
                        if structures_match(s1, s2):
                            if insert:
                                target.collection.remove(
                                    {"task_id": task_doc["task_id"]}
                                )  # TODO VaspCalcDb.remove_task
                            print("INFO: removed old task!")
                        else:
                            print("ERROR: structures do not match!")
                            # json.dump({'old': s1.as_dict(), 'new': s2.as_dict()}, open('{}.json'.format(task_doc['task_id']), 'w'))
                            continue
                    else:
                        print("ERROR: not a SO task!")
                        continue

            task_doc["sbxn"] = sbxn

            if insert:
                target.insert_task(task_doc, use_gridfs=True)

    table.align["Tag"] = "r"
    if tag is None:
        sfmt = "\033[1;32m{}\033[0m"
        table.add_row([sfmt.format(s if s else "-") for s in sums])
    if table._rows:
        print(table)


@cli.command()
@click.argument("base_path", type=click.Path(exists=True))
# @click.argument('target_spec')
@click.option(
    "--insert/--no-insert", default=False, help="actually execute task insertion"
)
@click.option(
    "--nproc",
    "-n",
    type=int,
    default=1,
    help="number of processes for parallel parsing",
)
@click.option(
    "--max-dirs",
    "-m",
    type=int,
    default=10,
    help="maximum number of directories to parse",
)
@click.option("--force/--no-force", default=False, help="force re-parsing of task")
@click.option(
    "--add_snlcolls",
    "-a",
    type=click.Path(exists=True),
    help="YAML config file with multiple documents defining additional SNLs collections to scan",
)
@click.option(
    "--make-snls/--no-make-snls",
    default=False,
    help="also create SNLs for parsed tasks",
)
@click.option(
    "--delete/--no-delete",
    default=False,
    help="delete directory after successful parse",
)
@click.option(
    "--copy-snls/--no-copy-snls", default=False, help="also copy SNLs"
)  # TODO
@click.option("--sbxn", multiple=True, help="add task to sandbox")
def parse(
    base_path,
    insert,
    nproc,
    max_dirs,
    force,
    add_snlcolls,
    make_snls,
    delete,
    copy_snls,
    sbxn,
):
    """parse VASP output directories in base_path into tasks and tag (incl. SNLs if available)"""

    if not insert:
        print("DRY RUN: add --insert flag to actually insert tasks")

    lpad = get_lpad()
    # target = calcdb_from_mgrant(target_spec)
    target = calcdb_from_mgrant(f"{lpad.host}/{lpad.name}")
    print("connected to target db with", target.collection.count(), "tasks")
    base_path = os.path.join(base_path, "")
    base_path_split = base_path.split(os.sep)
    tag = base_path_split[-1] if base_path_split[-1] else base_path_split[-2]
    drone = VaspDrone(
        parse_dos="auto", additional_fields={"tags": [tag, year_tags[-1]]}
    )
    already_inserted_subdirs = [
        get_subdir(dn)
        for dn in target.collection.find({"tags": tag}).distinct("dir_name")
    ]
    print(
        len(already_inserted_subdirs),
        "unique VASP directories already inserted for",
        tag,
    )
    if force:
        already_inserted_subdirs = []
        print("FORCING directory re-parse and overriding tasks!")

    # sbxn = list(sbxn) if sbxn else target.collection.distinct('sbxn')
    # ensure_indexes(['task_id', 'tags', 'dir_name', 'retired_task_id'], [target.collection])

    chunk_size = math.ceil(max_dirs / nproc)
    if nproc > 1 and max_dirs <= chunk_size:
        nproc = 1
        print(
            "max_dirs =",
            max_dirs,
            "but chunk size =",
            chunk_size,
            "-> parsing sequentially",
        )

    pool = multiprocessing.Pool(processes=nproc)
    iterator_vaspdirs = get_vasp_dirs(base_path, base_path, max_dirs, insert)
    iterator = iterator_slice(iterator_vaspdirs, chunk_size)  # process in chunks
    queue = deque()
    input_structures = []

    while iterator or queue:
        try:
            args = [next(iterator), insert, drone, already_inserted_subdirs, delete]
            queue.append(pool.apply_async(parse_vasp_dirs, args))
        except (StopIteration, TypeError):
            iterator = None
        while queue and (len(queue) >= pool._processes or not iterator):
            process = queue.pop()
            process.wait(1)
            if not process.ready():
                queue.append(process)
            else:
                input_structures += process.get()

    pool.close()
    print("DONE:", len(input_structures), "structures")

    fn = os.path.join(base_path, "launchdir_to_taskid.json")
    if os.path.exists(fn):
        print("updating task ids...")
        with open(fn, "r") as f:
            launchdir_to_taskid = json.load(f)
        for doc in target.collection.find(
            {"tags": tag}, {"dir_name": 1, "task_id": 1, "_id": 0}
        ):
            task_id = launchdir_to_taskid[get_subdir(doc["dir_name"])]
            if doc["task_id"] != task_id:
                target.collection.update_one(
                    {"task_id": doc["task_id"]}, {"$set": {"task_id": task_id}}
                )
                print(doc["dir_name"], doc["task_id"], task_id)

    if insert and make_snls:
        print("add SNLs for", len(input_structures), "structures")
        add_snls(tag, input_structures, add_snlcolls, insert)
