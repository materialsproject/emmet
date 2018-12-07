from __future__ import print_function
import io, os
from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools
from googleapiclient.http import MediaIoBaseDownload
from pprint import pprint
from tqdm import tqdm

# If modifying these scopes, delete the file token.json.
# see https://developers.google.com/identity/protocols/googlescopes#drivev3
SCOPES = 'https://www.googleapis.com/auth/drive'
OUTDIR = 'mpraw'
CHUNKSIZE = 1024*1024 # 5MB

def download_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request, chunksize=CHUNKSIZE)
    done = False
    with tqdm(total=100) as pbar:
        while done is False:
            status, done = downloader.next_chunk()
            pbar.update(int(status.progress() * 100))
    return fh.getvalue()

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
        block_query = "'{}' in parents and name contains 'block_'".format(garden_id)
    else:
        print('MPDRIVE_GARDEN_ID not set!')
        return

    while True:
        block_response = service.files().list(
            q=block_query, spaces='drive', pageToken=block_page_token,
            fields='nextPageToken, files(id, name)', pageSize=2
        ).execute()

        for block in block_response['files']:
            print(block['name'])
            block_dir = os.path.join(OUTDIR, block['name'])
            if not os.path.exists(block_dir):
                os.makedirs(block_dir)

            block_page_token = block_response.get('nextPageToken', None)
            if block_page_token is None:
                break # done with blocks

            # recurse into the block to retrieve launch_dir's
            launcher_page_token = None
            launcher_query = "'{}' in parents".format(block['id'])

            while True:
                launcher_response = service.files().list(
                    q=launcher_query, spaces='drive', pageToken=launcher_page_token,
                    fields='nextPageToken, files(id, name, modifiedTime, size)',
                    pageSize=10
                ).execute()

                for launcher in launcher_response['files']:
                    # TODO 'size' doesn't exist if launcher is another dir
                    # due to non-reservation mode production
                    if int(launcher['size']) < 50:
                        service.files().delete(fileId=launcher['id']).execute()
                        print('removed', launcher['name'])
                    else:
                        # download (incl. block)
                        #pprint(launcher)
                        path = os.path.join(block_dir, launcher['name'])
                        print(path)
                        if not os.path.exists(path):
                            content = download_file(service, launcher['id'])
                            with open(path, 'wb') as f:
                                f.write(content)
                            print(path, 'downloaded.')

                launcher_page_token = launcher_response.get('nextPageToken', None)
                if launcher_page_token is None:
                    break # done with launchers in current block

            # search for launchers in block again, and rm block if empty dir
            launcher_response = service.files().list(
                q=launcher_query, spaces='drive', pageSize=1
            ).execute()
            if not launcher_response['files']:
                service.files().delete(fileId=block['id']).execute()
                print('removed', block['name'])

        break # blocks loop TODO remove

    # TODO in production, subscribe to watch garden directory?
    # https://developers.google.com/drive/api/v3/reference/files/watch

if __name__ == '__main__':
    main()
