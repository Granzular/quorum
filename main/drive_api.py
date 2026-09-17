from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from django.conf import settings
from library.models import Resource, Course
import logging, re, io, json

logger = logging.getLogger(__name__)

# 1. Load the "Robot" credentials
creds = service_account.Credentials.from_service_account_file(
    settings.SERVICE_ACCOUNT_FILE, scopes=settings.SCOPES)
# 2. Build the Service 
# This is the core service for the google drive API service
DriveService = build('drive', 'v3', credentials=creds)


def test_drive():
    
    # List files in your specific Master Folder
    
    query = f"'{settings.DEFAULT_FOLDER_ID}' in parents"
    
    results = DriveService.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    
    for item in items:
        print(f"Found: {item['name']} (ID: {item['id']})")


def get_resource_index(folder_id:str,parent_name='Root'):
    """
    Recursively crawls folders and returns a flat list of files,
    each tagged with its immediate parent folder ID.
    """

    all_resources = []
    
    fields = "nextPageToken, files(id, name, mimeType, size, webViewLink, parents)"
    query = f"'{folder_id}' in parents and trashed = false"

    try:
        results = DriveService.files().list(
            q=query, 
            fields=fields,
            pageSize=100 
        ).execute()
        
        items = results.get('files', [])

        for item in items:
            # Check if the item is a folder
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                # Recursively go into the sub-folder
                all_resources.extend(get_resource_index(item['id'],parent_name=item['name']))
            else:
                # It's a file! Extract the immediate parent ID
                # 'parents' is a list, we take the first element [0]
                parent_id = item.get('parents', [None])[0]
                
                all_resources.append({
                    "drive_id": item['id'],
                    "name": item['name'],
                    "parent_name": parent_name,
                    "parent_id": parent_id,
                    "mime_type":  item['mimeType'],
                    "size": item.get('size'),
                    "download_url": f"https://drive.google.com/uc?export=download&id={item['id']}",
                    "preview_url": item.get('webViewLink'),
                })
        
        return all_resources

    except Exception as e:
        logger.error(f"Error crawling folder {folder_id}: {e}")
        return []


def __get_resource_index(folder_id:str,level=None,semester=None,parent_name='ROOT_FOLDER'):
    """
    Recursively crawls folders and returns a flat list of files,
    each tagged with its immediate parent folder ID.
    """

    all_resources = []
    
    fields = "nextPageToken, files(id, name, mimeType, size, webViewLink, parents)"
    query = f"'{folder_id}' in parents and trashed = false"

    try:
        results = DriveService.files().list(
            q=query, 
            fields=fields,
            pageSize=100 
        ).execute()
        
        items = results.get('files', [])

        for item in items:
            # Check if the item is a folder
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                # Recursively go into the sub-folder
                all_resources.extend(__get_resource_index(item['id'],level=level,semester=semester,parent_name=item['name']))
            else:
                # It's a file! Extract the immediate parent ID
                # 'parents' is a list, we take the first element [0]
                parent_id = item.get('parents', [None])[0]
                
                all_resources.append({
                    "drive_id": item['id'],
                    "name": item['name'],
                    "parent_name": parent_name,
                    "parent_id": parent_id,
                    "level": level,
                    "semester": semester,
                    "mime_type":  item['mimeType'],
                    "size": item.get('size'),
                    "download_url": f"https://drive.google.com/uc?export=download&id={item['id']}",
                    "preview_url": item.get('webViewLink'),
                })
        
        return all_resources

    except Exception as e:
        logger.error(f"Error crawling folder {folder_id}: {e}")
        return []


def pre_indexing():
    # performs preparatory action before indexing
    queryset = Resource.objects.only('is_active')
    for item in queryset:
        item.is_active = False
        item.save()
    
    
def post_indexing():
    # performs clean-up after indexing
    queryset = Resource.objects.filter(is_active=False).delete()

def start_resource_indexing():
    # 
    pre_indexing() # prep
    #data = get_resource_index(settings.DEFAULT_FOLDER_ID)
    with open('drive_index_filesystem.json','r') as fd:
        file = json.loads(fd.read())
    
    data = list()
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][0]['children'][0]['id'],level='100',semester='first'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][0]['children'][1]['id'],level='100',semester='second'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][1]['children'][0]['id'],level='200',semester='first'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][1]['children'][1]['id'],level='200',semester='second'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][2]['children'][0]['id'],level='300',semester='first'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][2]['children'][1]['id'],level='300',semester='second'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][3]['children'][0]['id'],level='400',semester='first'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][3]['children'][1]['id'],level='400',semester='second'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][4]['children'][0]['id'],level='500',semester='first'))
    data.extend(__get_resource_index(file['ROOT_FOLDER']['children'][4]['children'][1]['id'],level='500',semester='second'))

    
    if len(data) == 0:
        logger.debug('SYNC did not receive any data')
    else:
        for item in data:
            resource, created = Resource.objects.update_or_create(drive_id=item['drive_id'],defaults={
                'name': item['name'],
                'size': item['size'],
                'mime_type': item['mime_type'],
                'preview_url': item['preview_url'],
                'download_url': item['download_url'],
            })

            try:
                raw_name = item['parent_name']
                clean_name = " ".join(raw_name.split())
                if re.match(r'^[A-Za-z]{3} \d{3}$',clean_name) == None:
                    raise ValueError
                course,created = Course.objects.update_or_create(code__iexact=clean_name,defaults={
                    'drive_id': item['parent_id'],
                    'code': clean_name,
                    'level': item['level'],
                    'semester': item['semester'],
                })
                resource.is_active = True
                resource.save()
                course.resource.add(resource)

            except:
                logger.debug(f"{item['parent_name']} does not match a course code pattern")

        post_indexing()
        logger.debug('Indexing Completed')
            



def search_drive_materials(query_text=None, folder_id=None, mime_type=None):
    """
    A logic-only function to query Google Drive.
    Returns a list of dictionaries containing file metadata.
    """
    query_parts = ["trashed = false"]

    # 1. Scope by Folder (if provided)
    if folder_id:
        query_parts.extend(f"'{folder_id}' in parents")

    # 2. Filter by Name (Partial match)
    if query_text:
        # Note: 'contains' is case-insensitive for names in Drive API
        query_parts.extend(f"name contains '{query_text}'")

    # 3. Filter by MIME Type (e.g., 'application/pdf')
    if mime_type:
        query_parts.extend(f"mimeType = '{mime_type}'")

    # Join all parts with AND logic
    final_query = " and ".join(query_parts)

    try:
        results = []
        page_token = None
        
        while True:
            # We use fields to limit the data coming back over the wire
            # 'nextPageToken' handles cases where there are 100+ files
            response = DriveService.files().list(
                q=final_query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, size, modifiedTime)',
                pageToken=page_token,
                pageSize=100
            ).execute()
            
            results.extend(response.get('files', []))
            page_token = response.get('nextPageToken')
            
            if not page_token:
                break
                
        return results

    except Exception as e:
        # Log the error in your Django logs
        print(f"An error occurred during Drive search: {e}")
        return []
