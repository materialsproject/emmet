#import click, os, yaml, sys, logging, tarfile, bson, gzip, csv, tarfile, zipstream, re
#import itertools, multiprocessing, math, io, requests, json, time, zipfile, zlib
#from oauth2client import client as oauth2_client
#from oauth2client import file, tools
#from shutil import copyfile, rmtree
#from glob import glob
#from fnmatch import fnmatch
#from datetime import datetime
#from collections import Counter, OrderedDict, deque
#from pymongo import MongoClient
#from pymongo.errors import CursorNotFound
#from pymongo.collection import ReturnDocument
#from pymongo.errors import DocumentTooLarge
##from pymatgen.analysis.structure_prediction.volume_predictor import DLSVolumePredictor
#from pymatgen import Structure
#from pymatgen.alchemy.materials import TransformedStructure
#from pymatgen.util.provenance import StructureNL, Author
#from fireworks import LaunchPad, Firework
#from fireworks.fw_config import FW_BLOCK_FORMAT
#from atomate.vasp.database import VaspCalcDb
#from atomate.vasp.drones import VaspDrone
#from atomate.vasp.workflows.presets.core import wf_structure_optimization, wf_bandstructure
#from atomate.vasp.powerups import add_trackers, add_tags, add_additional_fields_to_taskdocs, add_wf_metadata
#from emmet.vasp.materials import group_structures, get_sg
#from emmet.vasp.task_tagger import task_type
#from prettytable import PrettyTable
#from googleapiclient.discovery import build
#from httplib2 import Http
#from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
#from tqdm import tqdm
#from pprint import pprint
#from mongogrant.client import Client
#from zipfile import ZipFile
#from bravado.requests_client import RequestsClient
#from bravado.client import SwaggerClient
#from typing import Iterator, Iterable, Union, Tuple, Dict, Any
#from urllib.parse import urlparse, urlencode
#import functools
#from uuid import uuid4
#
#print = functools.partial(print, flush=True)
#
#SCOPES = 'https://www.googleapis.com/auth/drive'
#current_year = int(datetime.today().year)
#year_tags = ['mp_{}'.format(y) for y in range(2018, current_year+1)]
#
#nomad_outdir = '/project/projectdirs/matgen/garden/nomad'
##nomad_outdir = '/clusterfs/mp/mp_prod/nomad'
#nomad_url = 'http://labdev-nomad.esc.rzg.mpg.de/fairdi/nomad/mp/api'
#user = 'phuck@lbl.gov'
#password = 'password'
#approx_upload_size = 24 * 1024 * 1024 * 1024  # you can make it really small for testing
#max_parallel_uploads = 6
#nomad_host = urlparse(nomad_url).netloc.split(':')[0]
#http_client = RequestsClient()
#http_client.set_basic_auth(nomad_host, user, password)
#nomad_client = SwaggerClient.from_url('%s/swagger.json' % nomad_url, http_client=http_client)
#direct_stream = False


import logging
import click

from log4mongo.handlers import BufferedMongoHandler
from emmet.cli.config import log_fields
from emmet.cli.admin import admin
from emmet.cli.calc import calc
from emmet.cli.utils import calcdb_from_mgrant, ensure_indexes
from emmet.cli.utils import EmmetCliError


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
logger = logging.getLogger('emmet')


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--spec', required=True, metavar='HOST/DB',
              help='MongoGrant spec for user database.')
@click.option('--run', is_flag=True, help='Run DB/filesystem write operations.')
@click.option('--no-dupe-check', is_flag=True, help='Skip duplicate check(s).')
@click.option('--verbose', is_flag=True, help='Show debug messages.')
@click.version_option()
@click.pass_context
def emmet(ctx, spec, run, no_dupe_check, verbose):
    """Command line interface for emmet"""
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    ctx.ensure_object(dict)
    ctx.obj['RUN'] = run
    ctx.obj['NO_DUPE_CHECK'] = no_dupe_check
    ctx.obj['SPEC'] = spec
    client = calcdb_from_mgrant(spec)
    ctx.obj['CLIENT'] = client
    ctx.obj['MONGO_HANDLER'] = BufferedMongoHandler(
        host=client.host, port=client.port, database_name=client.db_name,
        username=client.user, password=client.password, level=logging.WARNING,
        authentication_db=client.db_name, collection='emmet_logs',
        buffer_periodical_flush_timing=False  # flush manually
    )
    logger.addHandler(ctx.obj['MONGO_HANDLER'])
    coll = ctx.obj['MONGO_HANDLER'].collection
    created = ensure_indexes(log_fields, [coll])
    if created:
        indexes = ', '.join(created[coll.full_name])
        logger.debug(f'Created the following index(es) on {coll.full_name}:\n{indexes}')
    if not run:
        logger.info(click.style('DRY RUN! Add --run flag to execute changes.', fg='green'))


def safe_entry_point():
    try:
        emmet()
    except EmmetCliError as e:
        click.secho(str(e), fg='red')
    except Exception as e:
        logger.info(e, exc_info=True)


emmet.add_command(admin)
emmet.add_command(calc)
