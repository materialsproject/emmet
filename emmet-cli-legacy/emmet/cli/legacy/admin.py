import logging

import click
from pymatgen.core import Structure

from emmet.cli.legacy import SETTINGS
from emmet.cli.legacy.utils import (
    EmmetCliError,
    ensure_indexes,
    get_meta_from_structure,
)

logger = logging.getLogger("emmet")


@click.group()
@click.pass_context
def admin(ctx):
    """Administrative and utility commands"""
    if "CLIENT" not in ctx.obj:
        raise EmmetCliError("--spec option required with admin sub-command!")


def clean_ensure_indexes(run, fields, coll):
    if run:
        created = ensure_indexes(fields, [coll])
        if created:
            indexes = ", ".join(created[coll.full_name])
            logger.info(
                f"Created the following index(es) on {coll.full_name}:\n{indexes}"
            )
        else:
            logger.info("All indexes already created.")
    else:
        fields_list = ", ".join(fields)
        logger.info(
            f"Would create/ensure the following index(es) on "
            f"{coll.full_name}:\n{fields_list}"
        )


@admin.command()
@click.argument("fields", nargs=-1)
@click.argument("collection", nargs=1)
@click.pass_context
def index(ctx, fields, collection):
    """Create index(es) for fields of a collection"""
    coll = ctx.obj["CLIENT"].db[collection]
    clean_ensure_indexes(ctx.obj["RUN"], fields, coll)


@admin.command()
@click.argument("collection")
@click.pass_context
def meta(ctx, collection):
    """Create meta-data fields and indexes for SNL collection"""
    coll = ctx.obj["CLIENT"].db[collection]
    q = {"$or": [{k: {"$exists": 0}} for k in SETTINGS.meta_keys]}
    docs = coll.find(q)

    ndocs = docs.count()
    if ndocs > 0:
        if ctx.obj["RUN"]:
            logger.info(f"Fix meta for {ndocs} SNLs ...")
            for idx, doc in enumerate(docs):
                if idx and not idx % 1000:
                    logger.debug(f"{idx} ...")
                nested = "snl" in doc
                struct = Structure.from_dict(doc["snl"] if nested else doc)
                key = "task_id" if nested else "snl_id"
                coll.update({key: doc[key]}, {"$set": get_meta_from_structure(struct)})
        else:
            logger.info(f"Would fix meta for {ndocs} SNLs.")

    clean_ensure_indexes(ctx.obj["RUN"], SETTINGS.snl_indexes, coll)


@admin.command()
@click.argument("tags", nargs=-1)
@click.pass_context
def reset(ctx, tags):
    """Reset collections for tag(s)"""
    # TODO workflows, tasks?
    q = {"tags": {"$in": tags}}
    total = ctx.obj["MONGO_HANDLER"].collection.count()
    if ctx.obj["RUN"]:
        r = ctx.obj["MONGO_HANDLER"].collection.remove(q)
        logger.info(f'{r["n"]} of {total} log entries removed.')
    else:
        cnt = ctx.obj["MONGO_HANDLER"].collection.count(q)
        logger.info(f"Would remove {cnt} of {total} log entries.")


# TODO tags overview
#    TODO move collecting tags to admin?
#    tags = OrderedDict()
#    if tag is None:
#        all_tags = OrderedDict()
#        query = dict(exclude)
#        query.update(base_query)
#        for snl_coll in snl_collections:
#            print('collecting tags from', snl_coll.full_name, '...')
#            projects = snl_coll.distinct('about.projects', query)
#            remarks = snl_coll.distinct('about.remarks', query)
#            projects_remarks = projects
#            if len(remarks) < 100:
#                projects_remarks += remarks
#            else:
#                print('too many remarks in', snl_coll.full_name, '({})'.format(len(remarks)))
#            for t in set(projects_remarks):
#                q = {'$and': [{'$or': [{'about.remarks': t}, {'about.projects': t}]}, exclude]}
#                q.update(base_query)
#                if t not in all_tags:
#                    all_tags[t] = []
#                all_tags[t].append([snl_coll.count(q), snl_coll])
#        print('sort and analyze tags ...')
#        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1][0][0])
#        for item in sorted_tags:
#            total = sum([x[0] for x in item[1]])
#            q = {'tags': item[0]}
#            if not skip_all_scanned:
#                q['level'] = 'WARNING'
#            to_scan = total - lpad.db.add_wflows_logs.count(q)
#            if total < max_structures and to_scan:
#                tags[item[0]] = [total, to_scan, [x[-1] for x in item[1]]]
