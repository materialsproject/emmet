import gzip
import logging
import os
import struct
import tarfile
from collections import defaultdict
from fnmatch import fnmatch
from zipfile import ZipFile

import bson
import click
from pymatgen.alchemy.materials import TransformedStructure
from pymatgen.core import Structure
from pymatgen.util.provenance import Author, StructureNL

from emmet.cli import SETTINGS
from emmet.cli.utils import (
    EmmetCliError,
    StorageGateway,
    aggregate_by_formula,
    get_meta_from_structure,
    load_structure,
    structures_match,
)
from emmet.core.utils import get_sg, group_structures

_UNPACK_INT = struct.Struct("<i").unpack
logger = logging.getLogger("emmet")
canonical_structures = defaultdict(dict)  # type: ignore[var-annotated]


def get_format(fname):
    if fnmatch(fname, "*.cif*") or fnmatch(fname, "*.mcif*"):
        return "cif"
    elif fnmatch(fname, "*.json*") or fnmatch(fname, "*.mson*"):
        return "json"
    else:
        raise EmmetCliError(f"reading {fname} not supported (yet)")


def load_canonical_structures(ctx, full_name, formula):
    from emmet.core.vasp.calc_types import task_type  # TODO import error

    collection = ctx.obj["COLLECTIONS"][full_name]

    if formula not in canonical_structures[full_name]:
        canonical_structures[full_name][formula] = {}
        structures = defaultdict(list)

        if "tasks" in full_name:
            query = {"formula_pretty": formula}
            query.update(SETTINGS.task_base_query)
            projection = {"input.structure": 1, "task_id": 1, "orig_inputs": 1}
            tasks = collection.find(query, projection)

            for task in tasks:
                task_label = task_type(task["orig_inputs"], include_calc_type=False)
                if task_label == "Structure Optimization":
                    s = load_structure(task["input"]["structure"])
                    s.id = task["task_id"]
                    structures[get_sg(s)].append(s)

        elif "snl" in full_name:
            query = {"$or": [{k: formula} for k in SETTINGS.aggregation_keys]}
            query.update(SETTINGS.exclude)
            query.update(SETTINGS.base_query)

            for group in aggregate_by_formula(collection, query):
                for dct in group["structures"]:
                    s = load_structure(dct)
                    s.id = dct["snl_id"] if "snl_id" in dct else dct["task_id"]
                    structures[get_sg(s)].append(s)

        if structures:
            for sg, slist in structures.items():
                canonical_structures[full_name][formula][sg] = [
                    g[0] for g in group_structures(slist)
                ]

        total = sum([len(x) for x in canonical_structures[full_name][formula].values()])
        logger.debug(f"{total} canonical structure(s) for {formula} in {full_name}")


def save_logs(ctx):
    handler = ctx.obj["MONGO_HANDLER"]
    cnt = len(handler.buffer)
    handler.flush_to_mongo()
    logger.debug(f"{cnt} log messages saved.")


def insert_snls(ctx, snls):
    if ctx.obj["RUN"] and snls:
        logger.info(f"add {len(snls)} SNLs ...")
        result = ctx.obj["GATEWAY"].db.snls.insert_many(snls)
        logger.info(
            click.style(f"#SNLs inserted: {len(result.inserted_ids)}", fg="green")
        )

    snls.clear()
    save_logs(ctx)


# https://stackoverflow.com/a/39279826
def count_file_documents(file_obj):
    """Counts how many documents provided BSON file contains"""
    cnt = 0
    while True:
        # Read size of next object.
        size_data = file_obj.read(4)
        if len(size_data) == 0:
            break  # Finished with file normally.
        elif len(size_data) != 4:
            raise EmmetCliError("Invalid BSON: cut off in middle of objsize")
        obj_size = _UNPACK_INT(size_data)[0] - 4
        file_obj.seek(obj_size, os.SEEK_CUR)
        cnt += 1
    file_obj.seek(0)
    return cnt


@click.group()
@click.option(
    "-s",
    "specs",
    multiple=True,
    metavar="SPEC",
    help="Add DB(s) with SNL/task collection(s) to dupe-check.",
)
@click.option(
    "-m", "nmax", default=1000, show_default=True, help="Maximum #structures to scan."
)
@click.option(
    "--skip/--no-skip",
    default=True,
    show_default=True,
    help="Skip already scanned structures.",
)
@click.pass_context
def calc(ctx, specs, nmax, skip):
    """Set up calculations to optimize structures using VASP"""
    if "GATEWAY" not in ctx.obj:
        raise EmmetCliError("--spec option required with calc sub-command!")

    collections = {}
    for coll in [ctx.obj["GATEWAY"].db.snls, ctx.obj["GATEWAY"].db.tasks]:
        collections[coll.full_name] = coll  # user collections

    for spec in specs:
        storage_gateway = StorageGateway.from_db_file(spec)
        names = storage_gateway.database.list_collection_names(
            filter={"name": {"$regex": r"(snl|tasks)"}}
        )
        for name in names:
            collections[storage_gateway.db[name].full_name] = storage_gateway.db[name]

    for full_name, coll in collections.items():
        logger.debug(f"{coll.count()} docs in {full_name}")

    ctx.obj["COLLECTIONS"] = collections
    ctx.obj["NMAX"] = nmax
    ctx.obj["SKIP"] = skip


@calc.command()
@click.argument("archive", type=click.Path(exists=True))
@click.option(
    "-a",
    "authors",
    multiple=True,
    show_default=True,
    metavar="AUTHOR",
    default=["Materials Project <feedback@materialsproject.org>"],
    help="Author to assign to all structures.",
)
@click.pass_context
def prep(ctx, archive, authors):  # noqa: C901
    """prep structures from an archive for submission"""
    run = ctx.obj["RUN"]
    collections = ctx.obj["COLLECTIONS"]
    snl_collection = ctx.obj["GATEWAY"].database.snls
    handler = ctx.obj["MONGO_HANDLER"]
    nmax = ctx.obj["NMAX"]
    skip = ctx.obj["SKIP"]
    # TODO no_dupe_check flag

    fname, ext = os.path.splitext(os.path.basename(archive))
    tag, sec_ext = fname.rsplit(".", 1) if "." in fname else [fname, ""]
    logger.info(click.style(f"tag: {tag}", fg="cyan"))
    if sec_ext:
        ext = "".join([sec_ext, ext])
    exts = ["tar.gz", ".tgz", "bson.gz", ".zip"]
    if ext not in exts:
        raise EmmetCliError(f"{ext} not supported (yet)! Please use one of {exts}.")

    meta = {"authors": [Author.parse_author(a) for a in authors]}
    references = meta.get("references", "").strip()
    source_ids_scanned = handler.collection.distinct("source_id", {"tags": tag})

    # TODO add archive of StructureNL files
    input_structures, source_total = [], None
    if ext == "bson.gz":
        input_bson = gzip.open(archive)
        source_total = count_file_documents(input_bson)
        for doc in bson.decode_file_iter(input_bson):
            if len(input_structures) >= nmax:
                break
            if skip and doc["db_id"] in source_ids_scanned:
                continue
            elements = set(
                [
                    specie["element"]
                    for site in doc["structure"]["sites"]
                    for specie in site["species"]
                ]
            )
            for l in SETTINGS.skip_labels:
                if l in elements:
                    logger.log(
                        logging.ERROR if run else logging.INFO,
                        f'Skip structure {doc["db_id"]}: unsupported element {l}!',
                        extra={"tags": [tag], "source_id": doc["db_id"]},
                    )
                    break
            else:
                s = TransformedStructure.from_dict(doc["structure"])
                s.source_id = doc["db_id"]
                input_structures.append(s)
    elif ext == ".zip":
        input_zip = ZipFile(archive)
        namelist = input_zip.namelist()
        source_total = len(namelist)
        for fname in namelist:
            if len(input_structures) >= nmax:
                break
            if skip and fname in source_ids_scanned:
                continue
            contents = input_zip.read(fname)
            fmt = get_format(fname)
            s = Structure.from_str(contents, fmt=fmt)
            s.source_id = fname
            input_structures.append(s)
    else:
        tar = tarfile.open(archive, "r:gz")
        members = tar.getmembers()
        source_total = len(members)
        for member in members:
            if os.path.basename(member.name).startswith("."):
                continue
            if len(input_structures) >= nmax:
                break
            fname = member.name.lower()
            if skip and fname in source_ids_scanned:
                continue
            f = tar.extractfile(member)
            if f:
                contents = f.read().decode("utf-8")
                fmt = get_format(fname)
                s = Structure.from_str(contents, fmt=fmt)
                s.source_id = fname
                input_structures.append(s)

    total = len(input_structures)
    logger.info(
        f"{total} of {source_total} structure(s) loaded "
        f"({len(source_ids_scanned)} unique structures already scanned)."
    )

    save_logs(ctx)
    snls, index = [], None
    for istruct in input_structures:
        # number of log messages equals number of structures processed if --run
        # only logger.warning goes to DB if --run
        if run and len(handler.buffer) >= handler.buffer_size:
            insert_snls(ctx, snls)

        struct = (
            istruct.final_structure
            if isinstance(istruct, TransformedStructure)
            else istruct
        )
        struct.remove_oxidation_states()
        struct = struct.get_primitive_structure()
        formula = struct.composition.reduced_formula
        sg = get_sg(struct)

        if not (struct.is_ordered and struct.is_valid()):
            logger.log(
                logging.WARNING if run else logging.INFO,
                f"Skip structure {istruct.source_id}: disordered or invalid!",
                extra={
                    "formula": formula,
                    "spacegroup": sg,
                    "tags": [tag],
                    "source_id": istruct.source_id,
                },
            )
            continue

        for full_name, coll in collections.items():
            # load canonical structures in collection for current formula and
            # duplicate-check them against current structure
            load_canonical_structures(ctx, full_name, formula)
            for canonical_structure in canonical_structures[full_name][formula].get(
                sg, []
            ):
                if structures_match(struct, canonical_structure):
                    logger.log(
                        logging.WARNING if run else logging.INFO,
                        f"Duplicate for {istruct.source_id} ({formula}/{sg}): {canonical_structure.id}",
                        extra={
                            "formula": formula,
                            "spacegroup": sg,
                            "tags": [tag],
                            "source_id": istruct.source_id,
                            "duplicate_dbname": full_name,
                            "duplicate_id": canonical_structure.id,
                        },
                    )
                    break
            else:
                continue  # no duplicate found -> continue to next collection

            break  # duplicate found
        else:
            # no duplicates in any collection
            prefix = snl_collection.database.name
            if index is None:
                # get start index for SNL id
                snl_ids = snl_collection.distinct("snl_id")
                index = max([int(snl_id[len(prefix) + 1 :]) for snl_id in snl_ids])

            index += 1
            snl_id = "{}-{}".format(prefix, index)
            kwargs = {"references": references, "projects": [tag]}
            if isinstance(istruct, TransformedStructure):
                snl = istruct.to_snl(meta["authors"], **kwargs)
            else:
                snl = StructureNL(istruct, meta["authors"], **kwargs)

            snl_dct = snl.as_dict()
            snl_dct.update(get_meta_from_structure(struct))
            snl_dct["snl_id"] = snl_id
            snls.append(snl_dct)
            logger.log(
                logging.WARNING if run else logging.INFO,
                f"SNL {snl_id} created for {istruct.source_id} ({formula}/{sg})",
                extra={
                    "formula": formula,
                    "spacegroup": sg,
                    "tags": [tag],
                    "source_id": istruct.source_id,
                },
            )

    # final save
    if run:
        insert_snls(ctx, snls)


@calc.command()
@click.argument("tag")
def add(tag):
    """Add workflows for structures with tag in SNL collection"""
    pass


#
#        query = {'$and': [{'$or': [{'about.remarks': tag}, {'about.projects': tag}]}, exclude]}
#        query.update(base_query)
#        cnts = [snl_coll.count(query) for snl_coll in snl_collections]
#        total = sum(cnts)
#        if total:
#            q = {'tags': tag}
#            if not skip_all_scanned:
#                q['level'] = 'WARNING'
#            to_scan = total - lpad.database.add_wflows_logs.count(q)
#            tags[tag] = [total, to_scan, [snl_coll for idx, snl_coll in enumerate(snl_collections) if cnts[idx]]]
#
#    print('\n'.join(['{} ({}) --> {} TO SCAN'.format(k, v[0], v[1]) for k, v in tags.items()]))
#
#    grouped_workflow_structures = {}
#    canonical_workflow_structures = {}
#
#    def find_matching_canonical_task_structures(formula, struct, full_name):
#        matched_task_ids = []
#        if sgnum in canonical_task_structures[full_name][formula] and canonical_task_structures[full_name][formula][sgnum]:
#            for s in canonical_task_structures[full_name][formula][sgnum]:
#                if structures_match(struct, s):
#                    print('Structure for SNL', struct.snl_id, 'already added in task', s.task_id, 'in', full_name)
#                    matched_task_ids.append(s.task_id)
#        return matched_task_ids
#
#    for tag, value in tags.items():
#
#        if skip_all_scanned and not value[1]:
#            continue
#
#        print(value[0], 'structures for', tag, '...')
#        for coll in value[-1]:
#            print('aggregate structures in', coll.full_name,  '...')
#            structure_groups = aggregate_by_formula(coll, {'$or': [{'about.remarks': tag}, {'about.projects': tag}]})
#
#            print('loop formulas for', tag, '...')
#            counter = Counter()
#            structures, canonical_structures = {}, {}
#
#            try:
#                for idx_group, group in enumerate(structure_groups):
#
#                    counter['formulas'] += 1
#                    formula = group['_id']
#                    if formula not in structures:
#                        structures[formula] = {}
#                    if formula not in canonical_structures:
#                        canonical_structures[formula] = {}
#                    if idx_group and not idx_group%1000:
#                        print(idx_group, '...')
#
#                    for dct in group['structures']:
#                        q = {'level': 'WARNING', 'formula': formula, 'snl_id': dct['snl_id']}
#                        log_entries = list(mongo_handler.collection.find(q)) # log entries for already inserted workflows
#                        if log_entries:
#                            if force_new:
#                                q['tags'] = tag # try avoid duplicate wf insertion for same tag even if forced
#                                log_entry = mongo_handler.collection.find_one(q, {'_id': 0, 'message': 1, 'canonical_snl_id': 1, 'fw_id': 1})
#                                if log_entry:
#                                    print('WF already inserted for SNL {} with tag {}'.format(dct['snl_id'], tag))
#                                    print(log_entry)
#                                    continue
#                            else:
#                                lpad.database.add_wflows_logs.update(q, {'$addToSet': {'tags': tag}})
#                                continue # already checked
#                        q = {'level': 'ERROR', 'formula': formula, 'snl_id': dct['snl_id']}
#                        if skip_all_scanned and mongo_handler.collection.find_one(q):
#                            lpad.database.add_wflows_logs.update(q, {'$addToSet': {'tags': tag}})
#                            continue
#                        mongo_handler.collection.remove(q) # avoid dups
#                        counter['structures'] += 1
#                        s = Structure.from_dict(dct).get_primitive_structure()
#                        s.snl_id = dct['snl_id']
#                        s.task_id = dct.get('task_id')
#                        try:
#                            s.remove_oxidation_states()
#                        except Exception as ex:
#                            msg = 'SNL {}: {}'.format(s.snl_id, ex)
#                            print(msg)
#                            logger.error(msg, extra={'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'error': str(ex)})
#                            continue
#                        try:
#                            sgnum = get_sg(s)
#                        except Exception as ex:
#                            s.to(fmt='json', filename='sgnum_{}.json'.format(s.snl_id))
#                            msg = 'SNL {}: {}'.format(s.snl_id, ex)
#                            print(msg)
#                            logger.error(msg, extra={'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'error': str(ex)})
#                            continue
#                        if sgnum not in structures[formula]:
#                            structures[formula][sgnum] = []
#                        structures[formula][sgnum].append(s)
#
#                    for sgnum, slist in structures[formula].items():
#                        for g in group_structures(slist):
#                            if sgnum not in canonical_structures[formula]:
#                                canonical_structures[formula][sgnum] = []
#                            canonical_structures[formula][sgnum].append(g[0])
#                            if len(g) > 1:
#                                for s in g[1:]:
#                                    logger.warning('duplicate structure', extra={
#                                        'formula': formula, 'snl_id': s.snl_id, 'tags': [tag], 'canonical_snl_id': g[0].snl_id
#                                    })
#
#                    if not canonical_structures[formula]:
#                        continue
#                    canonical_structures_list = [x for sublist in canonical_structures[formula].values() for x in sublist]
#
#                    if not force_new and formula not in canonical_workflow_structures:
#                        canonical_workflow_structures[formula], grouped_workflow_structures[formula] = {}, {}
#                        workflows = lpad.workflows.find({'metadata.formula_pretty': formula}, {'metadata.structure': 1, 'nodes': 1, 'parent_links': 1})
#                        if workflows.count() > 0:
#                            workflow_structures = {}
#                            for wf in workflows:
#                                s = Structure.from_dict(wf['metadata']['structure'])
#                                s.remove_oxidation_states()
#                                sgnum = get_sg(s)
#                                if sgnum in canonical_structures[formula]:
#                                    if sgnum not in workflow_structures:
#                                        workflow_structures[sgnum] = []
#                                    s.fw_id = [n for n in wf['nodes'] if str(n) not in wf['parent_links']][0] # first node = SO firework
#                                    workflow_structures[sgnum].append(s)
#                            if workflow_structures:
#                                for sgnum, slist in workflow_structures.items():
#                                    grouped_workflow_structures[formula][sgnum] = [g for g in group_structures(slist)]
#                                    canonical_workflow_structures[formula][sgnum] = [g[0] for g in grouped_workflow_structures[formula][sgnum]]
#                                #print(sum([len(x) for x in canonical_workflow_structures[formula].values()]), 'canonical workflow structure(s) for', formula)
#
#                    for idx_canonical, (sgnum, slist) in enumerate(canonical_structures[formula].items()):
#
#                        for struc in slist:
#
#                            #try:
#                            #    struct = vp.get_predicted_structure(struc)
#                            #    struct.snl_id, struct.task_id = struc.snl_id, struc.task_id
#                            #except Exception as ex:
#                            #    print('Structure for SNL', struc.snl_id, '--> VP error: use original structure!')
#                            #    print(ex)
#                            #    struct = struc
#
#                            #if not structures_match(struct, struc):
#                            #    print('Structure for SNL', struc.snl_id, '--> VP mismatch: use original structure!')
#                            #    struct = struc
#                            struct = struc
#
#                            wf_found = False
#                            if not force_new and sgnum in canonical_workflow_structures[formula] and canonical_workflow_structures[formula][sgnum]:
#                                for sidx, s in enumerate(canonical_workflow_structures[formula][sgnum]):
#                                    if structures_match(struct, s):
#                                        msg = 'Structure for SNL {} already added in WF {}'.format(struct.snl_id, s.fw_id)
#                                        print(msg)
#                                        if struct.task_id is not None:
#                                            task_query = {'task_id': struct.task_id}
#                                            task_query.update(task_base_query)
#                                            for full_name in reversed(tasks_collections):
#                                                task = tasks_collections[full_name].find_one(task_query, ['input.structure'])
#                                                if task:
#                                                    break
#                                            if task:
#                                                s_task = Structure.from_dict(task['input']['structure'])
#                                                s_task.remove_oxidation_states()
#                                                if not structures_match(struct, s_task):
#                                                    msg = '  --> ERROR: Structure for SNL {} does not match {}'.format(struct.snl_id, struct.task_id)
#                                                    msg += '  --> CLEANUP: remove task_id from SNL'
#                                                    print(msg)
#                                                    coll.update({'snl_id': struct.snl_id}, {'$unset': {'about._materialsproject.task_id': 1}})
#                                                    logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': s.fw_id, 'tags': [tag]})
#                                                    counter['snl-task_mismatch'] += 1
#                                                else:
#                                                    msg = '  --> OK: workflow resulted in matching task {}'.format(struct.task_id)
#                                                    print(msg)
#                                                    logger.warning(msg, extra={
#                                                        'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id, 'tags': [tag]
#                                                    })
#                                            else:
#                                                print('  --> did not find task', struct.task_id, 'for WF', s.fw_id)
#                                                fw_ids = [x.fw_id for x in grouped_workflow_structures[formula][sgnum][sidx]]
#                                                fws = lpad.fireworks.find({'fw_id': {'$in': fw_ids}}, ['fw_id', 'spec._tasks'])
#                                                fw_found = False
#                                                for fw in fws:
#                                                    if fw['spec']['_tasks'][5]['additional_fields'].get('task_id') == struct.task_id:
#                                                        msg = '  --> OK: workflow {} will result in intended task-id {}'.format(fw['fw_id'], struct.task_id)
#                                                        print(msg)
#                                                        logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'task_id': struct.task_id, 'fw_id': fw['fw_id'], 'tags': [tag]})
#                                                        fw_found = True
#                                                        break
#                                                if not fw_found:
#                                                    print('  --> no WF with enforced task-id', struct.task_id)
#                                                    fw = lpad.fireworks.find_one({'fw_id': s.fw_id}, {'state': 1})
#                                                    print('  -->', s.fw_id, fw['state'])
#                                                    if fw['state'] == 'COMPLETED':
#                                                        # the task is in lpad.database.tasks with different integer task_id
#                                                        #    => find task => overwrite task_id => add_tasks will pick it up
#                                                        full_name = list(tasks_collections.keys())[0]
#                                                        load_canonical_task_structures(formula, full_name)
#                                                        matched_task_ids = find_matching_canonical_task_structures(formula, struct, full_name)
#                                                        if len(matched_task_ids) == 1:
#                                                            tasks_collections[full_name].update(
#                                                                {'task_id': matched_task_ids[0]}, {
#                                                                    '$set': {'task_id': struct.task_id, 'retired_task_id': matched_task_ids[0], 'last_updated': datetime.utcnow()},
#                                                                    '$addToSet': {'tags': tag}
#                                                                }
#                                                            )
#                                                            print(' --> replaced task_id', matched_task_ids[0], 'with', struct.task_id, 'in', full_name)
#                                                        elif matched_task_ids:
#                                                            msg = '  --> ERROR: multiple tasks {} for completed WF {}'.format(matched_task_ids, s.fw_id)
#                                                            print(msg)
#                                                            logger.error(msg, extra={
#                                                                'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': 'Multiple tasks for Completed WF'
#                                                            })
#                                                        else:
#                                                            msg = '  --> ERROR: task for completed WF {} does not exist!'.format(s.fw_id)
#                                                            msg += ' --> CLEANUP: delete {} WF and re-add/run to enforce task-id {}'.format(fw['state'], struct.task_id)
#                                                            print(msg)
#                                                            lpad.delete_wf(s.fw_id)
#                                                            break
#                                                    else:
#                                                        print('  --> CLEANUP: delete {} WF and re-add to include task_id as additional_field'.format(fw['state']))
#                                                        lpad.delete_wf(s.fw_id)
#                                                        break
#                                        else:
#                                            logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'fw_id': s.fw_id, 'tags': [tag]})
#                                        wf_found = True
#                                        break
#
#                            if wf_found:
#                                continue
#
#                            # need to check tasks b/c not every task is guaranteed to have a workflow (e.g. VASP dir parsing)
#                            if not force_new:
#                                msg, matched_task_ids = '', OrderedDict()
#                                for full_name in reversed(tasks_collections):
#                                    load_canonical_task_structures(formula, full_name)
#                                    matched_task_ids[full_name] = find_matching_canonical_task_structures(formula, struct, full_name)
#                                    if struct.task_id is not None and matched_task_ids[full_name] and struct.task_id not in matched_task_ids[full_name]:
#                                        msg = '  --> WARNING: task {} not in {}'.format(struct.task_id, matched_task_ids[full_name])
#                                        print(msg)
#                                    if matched_task_ids[full_name]:
#                                        break
#                                if any(matched_task_ids.values()):
#                                    logger.warning('matched task ids' + msg, extra={
#                                        'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag],
#                                        'task_id(s)': dict((k.replace('.', '#'), v) for k, v in matched_task_ids.items())
#                                    })
#                                    continue
#
#                            no_potcars = set(NO_POTCARS) & set(struct.composition.elements)
#                            if len(no_potcars) > 0:
#                                msg = 'Structure for SNL {} --> NO POTCARS: {}'.format(struct.snl_id, no_potcars)
#                                print(msg)
#                                logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': no_potcars})
#                                continue
#
#                            try:
#                                wf = wf_structure_optimization(struct, c={'ADD_MODIFY_INCAR': True})
#                                wf = add_trackers(wf)
#                                wf = add_tags(wf, [tag, year_tags[-1]])
#                                if struct.task_id is not None:
#                                    wf = add_additional_fields_to_taskdocs(wf, update_dict={'task_id': struct.task_id})
#                            except Exception as ex:
#                                msg = 'Structure for SNL {} --> SKIP: Could not make workflow --> {}'.format(struct.snl_id, str(ex))
#                                print(msg)
#                                logger.error(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'error': 'could not make workflow'})
#                                continue
#
#                            msg = 'Structure for SNL {} --> ADD WORKFLOW'.format(struct.snl_id)
#                            if struct.task_id is not None:
#                                msg += ' --> enforcing task-id {}'.format(struct.task_id)
#                            print(msg)
#
#                            if insert:
#                                old_new = lpad.add_wf(wf)
#                                logger.warning(msg, extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag], 'fw_id': list(old_new.values())[0]})
#                            else:
#                                logger.error(msg + ' --> DRY RUN', extra={'formula': formula, 'snl_id': struct.snl_id, 'tags': [tag]})
#                            counter['add(ed)'] += 1
#
#            except CursorNotFound as ex:
#                print(ex)
#                sites_elements = set([
#                    (len(set([e.symbol for e in x.composition.elements])), x.num_sites)
#                    for x in canonical_structures_list
#                ])
#                print(len(canonical_structures_list), 'canonical structure(s) for', formula, sites_elements)
#                if tag is not None:
#                    print('trying again ...')
#                    wflows(add_snlcolls, add_taskdbs, tag, insert, clear_logs, max_structures, True, force_new)
#
#            print(counter)
#
# @cli.command()
# @click.argument('email')
# @click.option('--add_snlcolls', '-a', type=click.Path(exists=True), help='YAML config file with multiple documents defining additional SNLs collections to scan')
# @click.option('--add_tasks_db', type=click.Path(exists=True), help='config file for additional tasks collection to scan')
# def find(email, add_snlcolls, add_tasks_db):
#    """checks status of calculations by submitter or author email in SNLs"""
#    lpad = get_lpad()
#
#    snl_collections = [lpad.database.snls]
#    if add_snlcolls is not None:
#        for snl_db_config in yaml.load_all(open(add_snlcolls, 'r')):
#            snl_db_conn = MongoClient(snl_db_config['host'], snl_db_config['port'], j=False, connect=False)
#            snl_db = snl_db_conn[snl_db_config['db']]
#            snl_db.authenticate(snl_db_config['username'], snl_db_config['password'])
#            snl_collections.append(snl_db[snl_db_config['collection']])
#    for snl_coll in snl_collections:
#        print(snl_coll.count(exclude), 'SNLs in', snl_coll.full_name)
#
#    tasks_collections = OrderedDict()
#    tasks_collections[lpad.database.tasks.full_name] = lpad.database.tasks
#    if add_tasks_db is not None: # TODO multiple alt_task_db_files?
#        client = VaspCalcDb.from_db_file(add_tasks_db, admin=True)
#        tasks_collections[client.collection.full_name] = client.collection
#    for full_name, tasks_coll in tasks_collections.items():
#        print(tasks_coll.count(), 'tasks in', full_name)
#
#    #ensure_indexes(['snl_id', 'about.remarks', 'submitter_email', 'about.authors.email'], snl_collections)
#    ensure_indexes(['snl_id', 'fw_id'], [lpad.database.add_wflows_logs])
#    ensure_indexes(['fw_id'], [lpad.fireworks])
#    ensure_indexes(['launch_id'], [lpad.launches])
#    ensure_indexes(['dir_name', 'task_id'], tasks_collections.values())
#
#    snl_ids = []
#    query = {'$or': [{'submitter_email': email}, {'about.authors.email': email}]}
#    query.update(exclude)
#    for snl_coll in snl_collections:
#        snl_ids.extend(snl_coll.distinct('snl_id', query))
#    print(len(snl_ids), 'SNLs')
#
#    fw_ids = lpad.database.add_wflows_logs.distinct('fw_id', {'snl_id': {'$in': snl_ids}})
#    print(len(fw_ids), 'FWs')
#
#    launch_ids = lpad.fireworks.distinct('launches', {'fw_id': {'$in': fw_ids}})
#    print(len(launch_ids), 'launches')
#
#    launches = lpad.launches.find({'launch_id': {'$in': launch_ids}}, {'launch_dir': 1})
#    subdirs = [get_subdir(launch['launch_dir']) for launch in launches]
#    print(len(subdirs), 'launch directories')
#
#    for full_name, tasks_coll in tasks_collections.items():
#        print(full_name)
#        for subdir in subdirs:
#            subdir_query = {'dir_name': {'$regex': '/{}$'.format(subdir)}}
#            task = tasks_coll.find_one(subdir_query, {'task_id': 1})
#            if task:
#                print(task['task_id'])
#            else:
#                print(subdir, 'not found')
#
#
#
#
# @cli.command()
# @click.option('--tag', default=None, help='only include structures with specific tag')
# @click.option('--in-progress/--no-in-progress', default=False, help='show in-progress only')
# @click.option('--to-csv/--no-to-csv', default=False, help='save report as CSV')
# def report(tag, in_progress, to_csv):
#    """generate a report of calculations status"""
#
#    lpad = get_lpad()
#    states = Firework.STATE_RANKS
#    states = sorted(states, key=states.get)
#
#    tags = [tag]
#    if tag is None:
#        tags = [t for t in lpad.workflows.distinct('metadata.tags') if t is not None and t not in year_tags]
#        tags += [t for t in lpad.database.add_wflows_logs.distinct('tags') if t is not None and t not in tags]
#        all_tags = []
#        for t in tags:
#            all_tags.append((t, lpad.database.add_wflows_logs.count({'tags': t})))
#        tags = [t[0] for t in sorted(all_tags, key=lambda x: x[1], reverse=True)]
#        print(len(tags), 'tags in WFs and logs collections')
#
#    table = PrettyTable()
#    table.field_names = ['Tag', 'SNLs', 'WFs2Add', 'WFs'] + states + ['% FIZZLED', 'Progress']
#    sums = ['total'] + [0] * (len(table.field_names)-1)
#
#    for t in tags:
#        wflows = lpad.workflows.find({'metadata.tags': t}, {'state': 1})
#        nr_snls = lpad.database.add_wflows_logs.count({'tags': t})
#        wflows_to_add = lpad.database.add_wflows_logs.count({'tags': t, 'level': 'ERROR', 'error': {'$exists': 0}})
#        counter = Counter([wf['state'] for wf in wflows])
#        total = sum(v for k, v in counter.items() if k in states)
#        tc, progress = t, '-'
#        if wflows_to_add or counter['COMPLETED'] + counter['FIZZLED'] != total:
#            tc = "\033[1;34m{}\033[0m".format(t) if not to_csv else t
#            progress = (counter['COMPLETED'] + counter['FIZZLED']) / total * 100. if total else 0.
#            progress = '{:.0f}%'.format(progress)
#        elif in_progress:
#            continue
#        entry = [tc, nr_snls, wflows_to_add, total] + [counter[state] for state in states]
#        fizzled = counter['FIZZLED'] / total if total else 0.
#        if progress != '-' and bool(counter['COMPLETED'] + counter['FIZZLED']):
#            fizzled = counter['FIZZLED'] / (counter['COMPLETED'] + counter['FIZZLED'])
#        sfmt = "\033[1;31m{:.0f}%\033[0m" if (not to_csv and fizzled > 0.2) else '{:.0f}%'
#        percent_fizzled = sfmt.format(fizzled*100.)
#        entry.append(percent_fizzled)
#        entry.append(progress)
#        for idx, e in enumerate(entry):
#            if isinstance(e, int):
#                sums[idx] += e
#        if any(entry[2:-2]):
#            table.add_row(entry)
#
#    if tag is None:
#        sfmt = '{}' if to_csv else '\033[1;32m{}\033[0m'
#        table.add_row([sfmt.format(s if s else '-') for s in sums])
#    table.align['Tag'] = 'r'
#    print(table)
#
#    if to_csv:
#        with open('emmet_report.csv', 'w') as csv_file:
#            writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
#            writer.writerow(table._field_names)
#            options = table._get_options({})
#            for row in table._get_rows(options):
#                writer.writerow(row)
