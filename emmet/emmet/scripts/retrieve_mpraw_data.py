from __future__ import print_function
import io, os, sys
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from googleapiclient.http import MediaIoBaseDownload
from tqdm import tqdm
import requests

# If modifying these scopes, delete the file token.json.
# see https://developers.google.com/identity/protocols/googlescopes#drivev3
SCOPES = 'https://www.googleapis.com/auth/drive'
OUTDIR = '/nomad/nomadlab/mpraw'
NOMAD_REPO = 'http://backend-repository-nomad.esc:8111/repo/search/calculations_oldformat?query={}'

def download_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    with tqdm(total=100) as pbar:
        while done is False:
            status, done = downloader.next_chunk()
            pbar.update(int(status.progress() * 100))
    return fh.getvalue()

full_launcher_path = []

def recurse(service, folder_id):
    page_token = None
    query = "'{}' in parents".format(folder_id)
    while True:
        response = service.files().list(
            q=query, spaces='drive', pageToken=page_token,
            fields='nextPageToken, files(id, name, modifiedTime, size)',
            pageSize=50
        ).execute()

        for launcher in response['files']:
            if '.tar.gz' in launcher['name']:
                print(launcher)
                launcher_name = launcher['name'].replace('.tar.gz', '')
                full_launcher_path.append(launcher_name)
                nomad_query='repository_main_file_uri="{}"'.format(launcher_name)
                #nomad_query='alltarget repository_uri.split="{}"'.format(','.join(full_launcher_path)) # TODO
                print(nomad_query)
                resp = requests.get(NOMAD_REPO.format(nomad_query)).json()
                if 'meta' in resp:
                    path = os.path.join(*full_launcher_path) + '.tar.gz'
                    if resp['meta']['total_hits'] < 1: # calculation not found in NoMaD repo
                        print('Retrieve', path, '...')
                        if not os.path.exists(path):
                            os.makedirs(path)
                            #content = download_file(service, launcher['id'])
                            #with open(path, 'wb') as f:
                            #    f.write(content)
                            print('... DONE.')
                    else:
                        print(path, 'found in NoMaD repo:')
                        for d in resp['data']:
                            print('\t', d['attributes']['repository_uri'])
                else:
                    raise Exception(resp['errors'][0]['detail'])
            else:
                full_launcher_path.append(launcher['name'])
                recurse(service, launcher['id'])

            del full_launcher_path[-1:]

        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break # done with launchers in current block

def main():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    store = file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets('credentials.json', SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('drive', 'v3', http=creds.authorize(Http()))

    # Call the Drive v3 API
    # https://developers.google.com/drive/api/v3/search-parameters#fn1
    # TODO older launcher directories don't have prefix
    # TODO also cover non-b/l hierarchy
    block_page_token = None
    garden_id = os.environ.get('MPDRIVE_GARDEN_ID')
    if garden_id:
        #block_query = "'{}' in parents and name contains 'block_'".format(garden_id)
        block_query = "'{}' in parents and name contains 'block_2011-10-07-08-57-17-804213'".format(garden_id)
    else:
        print('MPDRIVE_GARDEN_ID not set!')
        return

    while True:
        block_response = service.files().list(
            q=block_query, spaces='drive', pageToken=block_page_token,
            fields='nextPageToken, files(id, name)', pageSize=10
        ).execute()

        for block in block_response['files']:
            print(block['name'])
            full_launcher_path.clear()
            full_launcher_path.append(block['name'])
            recurse(service, block['id'])

        block_page_token = block_response.get('nextPageToken', None)
        if block_page_token is None:
            break # done with blocks

    # TODO in production, subscribe to watch garden directory?
    # https://developers.google.com/drive/api/v3/reference/files/watch

if __name__ == '__main__':
    main()
