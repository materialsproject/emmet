# # https://gitlab.mpcdf.mpg.de/nomad-lab/nomad-FAIR/blob/v0.6.0/examples/external_project_parallel_upload/upload.py
# def upload_next_data(
#     sources: Iterator[Tuple[str, str, str]], upload_name="next upload"
# ):
#     """
#     Reads data from the given sources iterator. Creates and uploads a .zip-stream of
#     approx. size. Returns the upload, or raises StopIteration if the sources iterator
#     was empty. Should be used repeatedly on the same iterator until it is empty.
#     """
#
#     # potentially raises StopIteration before being streamed
#     first_source = next(sources)
#     calc_metadata = []
#
#     def iterator():
#         """
#         Yields dicts with keys arcname, iterable, as required for the zipstream
#         library. Will read from generator until the zip-stream has the desired size.
#         """
#         size = 0
#         first = True
#         while True:
#             if first:
#                 source_file, prefix, material_id, external_id = first_source
#                 first = False
#             else:
#                 try:
#                     source_file, prefix, material_id, external_id = next(sources)
#                 except StopIteration:
#                     break
#
#             source_tar = tarfile.open(source_file)
#             source = source_tar.fileobj
#             bufsize = source_tar.copybufsize
#             for source_member in source_tar.getmembers():
#                 if not source_member.isfile():
#                     continue
#
#                 target = io.BytesIO()
#                 source.seek(source_member.offset_data)
#                 tarfile.copyfileobj(  # type: ignore
#                     source, target, source_member.size, tarfile.ReadError, bufsize
#                 )
#
#                 size += source_member.size
#                 target.seek(0)
#
#                 def iter_content():
#                     while True:
#                         data = target.read(io.DEFAULT_BUFFER_SIZE)
#                         if not data:
#                             break
#                         yield data
#
#                 name = source_member.name
#                 if prefix is not None:
#                     name = os.path.join(prefix, name)
#
#                 if re.search(r"vasp(run)?\.xml(.gz)?$", name):
#                     calc_metadata.append(
#                         dict(
#                             mainfile=name,
#                             external_id=external_id,
#                             references=[
#                                 f"https://materialsproject.org/tasks/{material_id}#{external_id}"
#                             ],
#                         )
#                     )
#
#                 yield dict(
#                     arcname=name,
#                     iterable=iter_content(),
#                     buffer_size=source_member.size,
#                 )
#
#             if size > approx_upload_size:
#                 break
#
#     # create the zip-stream from the iterator above
#     zip_stream = zipstream.ZipFile(
#         mode="w", compression=zipfile.ZIP_STORED, allowZip64=True
#     )
#     zip_stream.paths_to_write = iterator()
#
#     user = nomad_client.auth.get_user().response().result
#     token = user.token
#     url = nomad_url + "/uploads/?%s" % urlencode(dict(name=upload_name))
#
#     def content():
#         for chunk in zip_stream:
#             if len(chunk) != 0:
#                 yield chunk
#
#     if direct_stream:
#         print("stream .zip to nomad ...")
#         response = requests.put(
#             url=url,
#             headers={"X-Token": token, "Content-type": "application/octet-stream"},
#             data=content(),
#         )
#     else:
#         print("save .zip and upload file to nomad ...")
#         zipfile_name = os.path.join(nomad_outdir, str(uuid4()) + ".zip")
#         with open(zipfile_name, "wb") as f:
#             for c in content():
#                 f.write(c)
#         try:
#             with open(zipfile_name, "rb") as f:
#                 response = requests.put(
#                     url=url,
#                     headers={
#                         "X-Token": token,
#                         "Content-type": "application/octet-stream",
#                     },
#                     data=f,
#                 )
#         finally:
#             os.remove(zipfile_name)
#
#     if response.status_code != 200:
#         raise Exception("nomad return status %d" % response.status_code)
#
#     upload_id = response.json()["upload_id"]
#
#     print("upload_id:", upload_id)
#     return (
#         nomad_client.uploads.get_upload(upload_id=upload_id).response().result,
#         calc_metadata,
#     )
#
#
# def publish_upload(upload, calc_metadata):
#     metadata = {
#         # these metadata are applied to all calcs in the upload
#         "comment": "Materials Project VASP Calculations",
#         "references": ["https://materialsproject.org"],
#         "co_authors": [928],
#         # these are calc specific metadata that supercede any upload metadata
#         "calculations": calc_metadata,
#     }
#     nomad_client.uploads.exec_upload_operation(
#         upload_id=upload.upload_id,
#         payload={"operation": "publish", "metadata": metadata},
#     ).response()
#
#
# def upload_archive(path, name, service, parent=None):
#     media = MediaFileUpload(path, mimetype="application/gzip", resumable=True)
#     body = {"name": name, "parents": [parent]}
#     request = service.files().create(media_body=media, body=body)
#     response = None
#     while response is None:
#         status, response = request.next_chunk()
#         if status:
#             print("Uploaded %d%%." % int(status.progress() * 100))
#     print("Upload Complete!")
#
#
# def download_file(service, file_id):
#     request = service.files().get_media(fileId=file_id)
#     fh = io.BytesIO()
#     downloader = MediaIoBaseDownload(fh, request)
#     done = False
#     with tqdm(total=100) as pbar:
#         while done is False:
#             status, done = downloader.next_chunk()
#             pbar.update(int(status.progress() * 100))
#     return fh.getvalue()
#
#
# @cli.command()
# @click.argument("target_spec")
# @click.option("--block-filter", "-f", help="block filter substring (e.g. block_2017-)")
# @click.option(
#     "--sync-nomad/--no-sync-nomad", default=False, help="sync to NOMAD repository"
# )
# def gdrive(target_spec, block_filter, sync_nomad):
#     """sync launch directories for target task DB to Google Drive"""
#     target = calcdb_from_mgrant(target_spec)
#     print("connected to target db with", target.collection.count(), "tasks")
#     print(target.db.materials.count(), "materials")
#
#     q = {} if block_filter is None else {"dir_name": {"$regex": block_filter}}
#     tasks = {}
#     for doc in target.collection.find(q, {"task_id": 1, "dir_name": 1}):
#         material = target.db.materials.find_one(
#             {"task_ids": doc["task_id"]}, {"task_id": 1}
#         )
#         if material is None:
#             print(doc["task_id"], "not in materials collection!", doc["dir_name"])
#             continue
#         subdir = get_subdir(doc["dir_name"])
#         tasks[subdir] = {"material_id": material["task_id"], "task_id": doc["task_id"]}
#     print(len(tasks), "tasks for block_filter", block_filter)
#
#     creds, store = None, None
#     if os.path.exists("token.json"):
#         store = file.Storage("token.json")
#         creds = store.get()
#     if not creds or creds.invalid:
#         flow = oauth2_client.flow_from_clientsecrets("credentials.json", SCOPES)
#         store = file.Storage("token.json")
#         args = tools.argparser.parse_args()
#         args.noauth_local_webserver = True
#         creds = tools.run_flow(
#             flow, store, args
#         )  # will need to run this in interactive session the first time
#     service = build("drive", "v3", http=creds.authorize(Http()))
#     garden_id = os.environ.get("MPDRIVE_GARDEN_ID")
#     if not garden_id:
#         print("MPDRIVE_GARDEN_ID not set!")
#         return
#
#     launcher_paths = []
#     full_launcher_path = []
#
#     def recurse(service, folder_id):
#         page_token = None
#         query = "'{}' in parents".format(folder_id)
#         while True:
#             response = (
#                 service.files()
#                 .list(
#                     q=query,
#                     spaces="drive",
#                     pageToken=page_token,
#                     fields="nextPageToken, files(id, name, modifiedTime, size)",
#                 )
#                 .execute()
#             )
#             print("#launchers:", len(response["files"]))
#
#             for idx, launcher in enumerate(response["files"]):
#                 if ".json" not in launcher["name"]:
#                     if ".tar.gz" in launcher["name"]:
#                         launcher_name = launcher["name"].replace(".tar.gz", "")
#                         full_launcher_path.append(launcher_name)
#                         launcher_paths.append(
#                             {
#                                 "path": os.path.join(*full_launcher_path),
#                                 "size": launcher["size"],
#                             }
#                         )
#
#                         if sync_nomad:
#                             full_launcher = os.path.join(*full_launcher_path)
#                             mainfiles = [
#                                 os.path.join(full_launcher, "vasprun.xml.gz"),
#                                 os.path.join(full_launcher, "vasprun.xml"),
#                                 os.path.join(full_launcher, "relax2", "vasprun.xml.gz"),
#                                 os.path.join(full_launcher, "vasprun.xml.relax2.gz"),
#                                 os.path.join(full_launcher, "vasprun.xml.relax2"),
#                             ]
#
#                             for j, mainfile in enumerate(mainfiles):
#                                 result = (
#                                     nomad_client.repo.search(mainfile=mainfile)
#                                     .response()
#                                     .result
#                                 )
#                                 path = os.path.join(
#                                     nomad_outdir, launcher_paths[-1]["path"] + ".tar.gz"
#                                 )
#
#                                 if (
#                                     result.pagination.total == 0
#                                     and j < len(mainfiles) - 1
#                                 ):
#                                     continue
#                                 elif result.pagination.total == 0:
#                                     print(f"{idx} {full_launcher_path[-1]} not found")
#                                     if not os.path.exists(path):
#                                         subdir = get_subdir(path.replace(".tar.gz", ""))
#                                         if tasks.get(subdir):
#                                             print("Retrieve", path, "from GDrive ...")
#                                             outdir_list = [
#                                                 nomad_outdir
#                                             ] + full_launcher_path[:-1]
#                                             outdir = os.path.join(*outdir_list)
#                                             if not os.path.exists(outdir):
#                                                 os.makedirs(outdir, exist_ok=True)
#                                             content = download_file(
#                                                 service, launcher["id"]
#                                             )
#                                             with open(path, "wb") as f:
#                                                 f.write(content)
#                                         else:
#                                             print(
#                                                 "skip download - no task_info available:",
#                                                 launcher_paths[-1]["path"],
#                                             )
#                                     else:
#                                         print("\t-> already retrieved from GDrive.")
#                                 elif result.pagination.total >= 1:
#                                     print(
#                                         f'Found calc {result.results[0]["calc_id"]} for {full_launcher_path[-1]}'
#                                     )
#                                     if os.path.exists(path):
#                                         os.remove(path)
#                                         print(path, "removed.")
#                                     break
#
#                     else:
#                         full_launcher_path.append(launcher["name"])
#                         recurse(service, launcher["id"])
#
#                     del full_launcher_path[-1:]
#
#             page_token = response.get("nextPageToken", None)
#             if page_token is None:
#                 break  # done with launchers in current block
#
#     # TODO older launcher directories don't have prefix
#     # TODO also cover non-b/l hierarchy
#     block_page_token = None
#     block_query = (
#         "'{}' in parents".format(garden_id)
#         if block_filter is None
#         else "'{}' in parents and name contains '{}'".format(garden_id, block_filter)
#     )
#
#     while True:
#         block_response = (
#             service.files()
#             .list(
#                 q=block_query,
#                 spaces="drive",
#                 pageToken=block_page_token,
#                 fields="nextPageToken, files(id, name)",
#             )
#             .execute()
#         )
#         print("#blocks:", len(block_response["files"]))
#
#         for block in block_response["files"]:
#             print(block["name"])
#             full_launcher_path.clear()
#             full_launcher_path.append(block["name"])
#             recurse(service, block["id"])
#
#             if sync_nomad:
#                 block_dir = os.path.join(nomad_outdir, block["name"])
#                 if not os.path.exists(block_dir):
#                     print("nothing to upload for", block["name"])
#                     continue
#
#                 def source_generator():
#                     for dirpath, dnames, fnames in os.walk(block_dir):
#                         for f in fnames:
#                             if f.endswith(".tar.gz"):
#                                 print(f)
#                                 ff = os.path.join(dirpath, f)
#                                 nroot = len(nomad_outdir.split(os.sep))
#                                 prefix = os.sep.join(dirpath.split(os.sep)[nroot:])
#                                 subdir = get_subdir(f.replace(".tar.gz", ""))
#                                 task_info = tasks.get(subdir)
#                                 if task_info:
#                                     yield ff, prefix, task_info[
#                                         "material_id"
#                                     ], task_info["task_id"]
#                                 else:
#                                     print("skipped - no task_info available:", f)
#
#                 # upload to NoMaD
#                 print(f'uploading {block["name"]} to NoMaD ...')
#                 source_iter = iter(source_generator())
#                 all_uploaded = False
#                 processing_completed = False
#                 all_calc_metadata: Dict[str, Any] = {}
#
#                 # run until there are no more uploads and everything is processed (and published)
#                 while not (all_uploaded and processing_completed):
#                     # process existing uploads
#                     while True:
#                         uploads = nomad_client.uploads.get_uploads().response().result
#
#                         for upload in uploads.results:
#                             calc_metadata = all_calc_metadata.get(
#                                 upload.upload_id, None
#                             )
#                             if calc_metadata is None:
#                                 continue
#
#                             if not upload.process_running:
#                                 if upload.tasks_status == "SUCCESS":
#                                     print(
#                                         "publish %s(%s)"
#                                         % (upload.name, upload.upload_id)
#                                     )
#                                     publish_upload(upload, calc_metadata)
#                                 elif upload.tasks_status == "FAILURE":
#                                     print(
#                                         "could not process %s(%s)"
#                                         % (upload.name, upload.upload_id)
#                                     )
#                                     nomad_client.uploads.delete_upload(
#                                         upload_id=upload.upload_id
#                                     ).response().result
#
#                         if uploads.pagination.total < max_parallel_uploads:
#                             # still processing some, but there is room for more uploads
#                             break
#                         else:
#                             print("wait for processing ...")
#                             time.sleep(10)
#
#                     # add a new upload
#                     if all_uploaded:
#                         processing_completed = uploads.pagination.total == 0
#
#                     try:
#                         upload, calc_metadata = upload_next_data(
#                             source_iter, upload_name=block["name"]
#                         )
#                         all_calc_metadata[upload.upload_id] = calc_metadata
#                         processing_completed = False
#                         print("uploaded %s(%s)" % (upload.name, upload.upload_id))
#                     except StopIteration:
#                         all_uploaded = True
#                     # except Exception as e:
#                     #    print('could not upload next upload: %s' % str(e))
#
#                 # cleanup to avoid duplicate uploads
#                 rmtree(block_dir)
#                 print("removed", block_dir)
#
#         block_page_token = block_response.get("nextPageToken", None)
#         if block_page_token is None:
#             break  # done with blocks
#
#     launcher_paths_sort = sorted([d["path"] for d in launcher_paths])
#     print(len(launcher_paths_sort), "launcher directories in GDrive")
#
#     if sync_nomad:
#         return
#
#     query = {}
#     blessed_task_ids = [
#         task_id
#         for doc in target.db.materials.find(query, {"task_id": 1, "blessed_tasks": 1})
#         for task_type, task_id in doc["blessed_tasks"].items()
#     ]
#     print(len(blessed_task_ids), "blessed tasks.")
#
#     nr_launchers_sync = 0
#     block_launchers = []
#     outfile = open("launcher_paths_{}.txt".format(block_filter), "w")
#     splits = ["block_", "res_1_aflow_engines-", "aflow_engines-"]
#     for task in target.collection.find(
#         {"task_id": {"$in": blessed_task_ids}}, {"dir_name": 1}
#     ):
#         dir_name = task["dir_name"]
#         for s in splits:
#             ds = dir_name.split(s)
#             if len(ds) == 2:
#                 block_launcher = s + ds[-1]
#                 if block_launcher not in launcher_paths_sort and (
#                     block_filter is None
#                     or (
#                         block_filter is not None
#                         and block_launcher.startswith(block_filter)
#                     )
#                 ):
#                     nr_launchers_sync += 1
#                     outfile.write(block_launcher + "\n")
#                 block_launchers.append(block_launcher)
#                 break
#         else:
#             print("could not split", dir_name)
#             return
#
#     outfile.close()
#     print(nr_launchers_sync, "launchers to sync")
#
#     outfile_sizes = open("launcher_paths_{}_sizes.txt".format(block_filter), "w")
#     for d in launcher_paths:
#         if d["path"] in block_launchers:
#             outfile_sizes.write(f"{d['path']} {d['size']}\n")
#     outfile_sizes.close()
#     return
#
#     nr_tasks_processed = 0
#     prev = None
#     outfile = open("launcher_paths.txt", "w")
#     stage_dir = "/project/projectdirs/matgen/garden/rclone_to_mp_drive"
#
#     for idx, dir_name in enumerate(dir_names):
#         block_launcher_split = dir_name.split(os.sep)
#         # if prev is not None and prev != block_launcher_split[0]: # TODO remove
#         #    break
#         print(idx, dir_name)
#         archive_name = "{}.tar.gz".format(block_launcher_split[-1])
#         query = "name = '{}'".format(archive_name)
#         response = (
#             service.files()
#             .list(q=query, spaces="drive", fields="files(id, name, size, parents)")
#             .execute()
#         )
#         files = response["files"]
#         archive_path = os.path.join(stage_dir, dir_name + ".tar.gz")
#         if files:
#             if len(files) > 1:
#                 # duplicate uploads - delete all and re-upload
#                 for f in files:
#                     print("removing", f["name"], "...")
#                     service.files().delete(fileId=f["id"]).execute()
#                 print("TODO: rerun to upload!")
#             elif int(files[0]["size"]) < 50:
#                 service.files().delete(fileId=files[0]["id"]).execute()
#                 if os.path.exists(archive_path):
#                     parent = files[0]["parents"][0]
#                     upload_archive(archive_path, archive_name, service, parent=parent)
#                 else:
#                     print("TODO: get from HPSS")
#                     outfile.write(dir_name + "\n")
#             else:
#                 print("OK:", files[0])
#         else:
#             if os.path.exists(archive_path):
#                 # make directories
#                 parents = [garden_id]
#                 for folder in block_launcher_split[:-1]:
#                     query = "name = '{}'".format(folder)
#                     response = (
#                         service.files()
#                         .list(
#                             q=query,
#                             spaces="drive",
#                             fields="files(id, name)",
#                             pageSize=1,
#                         )
#                         .execute()
#                     )
#                     if not response["files"]:
#                         print("create dir ...", folder)
#                         body = {
#                             "name": folder,
#                             "mimeType": "application/vnd.google-apps.folder",
#                             "parents": [parents[-1]],
#                         }
#                         gdrive_folder = service.files().create(body=body).execute()
#                         parents.append(gdrive_folder["id"])
#                     else:
#                         parents.append(response["files"][0]["id"])
#
#                 upload_archive(archive_path, archive_name, service, parent=parents[-1])
#             else:
#                 print("TODO: get from HPSS")
#                 outfile.write(dir_name + "\n")
#         nr_tasks_processed += 1
#         prev = block_launcher_split[0]
#
#     print(nr_tasks_processed)
#     outfile.close()
