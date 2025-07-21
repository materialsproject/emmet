# import click, os, yaml, sys, logging, tarfile, bson, gzip, csv, tarfile, zipstream, re
# import itertools, multiprocessing, math, io, requests, json, time, zipfile, zlib
# from oauth2client import client as oauth2_client
# from oauth2client import file, tools
# from glob import glob
# from fnmatch import fnmatch
# from datetime import datetime
# from collections import Counter, OrderedDict, deque
# from pymongo import MongoClient
# from pymongo.errors import CursorNotFound
# from pymongo.collection import ReturnDocument
# from pymongo.errors import DocumentTooLarge
# from pymatgen.analysis.structure_prediction.volume_predictor import DLSVolumePredictor
# from pymatgen import Structure
# from pymatgen.alchemy.materials import TransformedStructure
# from pymatgen.util.provenance import StructureNL, Author
# from fireworks import LaunchPad, Firework
# from fireworks.fw_config import FW_BLOCK_FORMAT
# from atomate.vasp.database import VaspCalcDb
# from atomate.vasp.workflows.presets.core import wf_structure_optimization, wf_bandstructure
# from atomate.vasp.powerups import add_trackers, add_tags, add_additional_fields_to_taskdocs, add_wf_metadata
# from emmet.vasp.materials import group_structures, get_sg
# from emmet.vasp.task_tagger import task_type
# from prettytable import PrettyTable
# from googleapiclient.discovery import build
# from httplib2 import Http
# from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
# from tqdm import tqdm
# from pprint import pprint
# from mongogrant.client import Client
# from zipfile import ZipFile
# from bravado.requests_client import RequestsClient
# from bravado.client import SwaggerClient
# from typing import Iterator, Iterable, Union, Tuple, Dict, Any
# from urllib.parse import urlparse, urlencode
# import functools
# from uuid import uuid4
#
# print = functools.partial(print, flush=True)
#
# SCOPES = 'https://www.googleapis.com/auth/drive'
#
# nomad_outdir = '/project/projectdirs/matgen/garden/nomad'
# nomad_outdir = '/clusterfs/mp/mp_prod/nomad'
# nomad_url = 'http://labdev-nomad.esc.rzg.mpg.de/fairdi/nomad/mp/api'
# user = 'phuck@lbl.gov'
# password = 'password'
# approx_upload_size = 24 * 1024 * 1024 * 1024  # you can make it really small for testing
# max_parallel_uploads = 6
# nomad_host = urlparse(nomad_url).netloc.split(':')[0]
