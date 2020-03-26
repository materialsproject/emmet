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
#from log4mongo.handlers import MongoHandler, MongoFormatter
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
#task_base_query = {'tags': {'$nin': ['DEPRECATED', 'deprecated']}, '_mpworks_meta': {'$exists': 0}}
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


import click
from emmet.cli.admin import admin
from emmet.cli.utils import get_lpad, calcdb_from_mgrant


@click.group()
@click.option('--debug/--no-debug', default=False)
@click.option('-s', '--spec', help='mongogrant string for DB (default: FW_CONFIG_FILE)')
@click.pass_context
def entry_point(ctx, debug, spec):
    """command line interface for emmet"""
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug

    if not spec:
        lpad = get_lpad()
        spec = f'{lpad.host}/{lpad.name}'

    ctx.obj['SPEC'] = spec
    ctx.obj['CLIENT'] = calcdb_from_mgrant(spec)
    if debug:
        click.echo(f'Spec: {spec}')


def safe_entry_point():
    try:
        entry_point()
    except Exception as e:
        click.echo(e)


entry_point.add_command(admin)
