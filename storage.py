"""
Schedule storage strategies (Strategy pattern).
"""
import os
import re
import shutil
import tempfile
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from urllib.parse import urljoin, urlparse, unquote

import requests
import xml.etree.ElementTree as ET

from converter import convert_docx_to_pdf

logger = logging.getLogger(__name__)
PDFS_DIR = os.path.join(os.getcwd(), 'pdfs')
os.makedirs(PDFS_DIR, exist_ok=True)


class ScheduleStorage(ABC):
    @abstractmethod
    def get_schedule_files(self) -> List[str]:
        """Returns list of local PDF file paths containing schedule"""
        pass


class GoogleDriveStorage(ScheduleStorage):
    def __init__(self, folder_id: str):
        self.folder_id = folder_id

    def get_schedule_files(self) -> List[str]:
        if not self.folder_id:
            raise ValueError("folder_id is required for Google Drive storage")

        url = f'https://drive.google.com/drive/folders/{self.folder_id}'
        logger.info(f"\nDownloading files from Google Drive folder...")
        logger.info(f"Folder URL: {url}")

        downloaded_pdfs = []

        try:
            logger.info("\nDownloading folder with gdown...")
            temp_dir = tempfile.mkdtemp(prefix='schedule_')

            import gdown
            gdown.download_folder(url, quiet=False, use_cookies=False, output=temp_dir)

            logger.info("\nConverting DOCX files to PDF...")

            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    temp_path = os.path.join(root, file)
                    logger.info(f"\nProcessing: {file}")

                    if file.endswith('.pdf'):
                        safe_name = re.sub(r'[^\w\s\-\.\u0400-\u04FF]', '', file)
                        output_path = os.path.join(PDFS_DIR, safe_name)
                        shutil.copy(temp_path, output_path)
                        downloaded_pdfs.append(output_path)
                        logger.info(f"  Copied PDF: {safe_name}")

                    elif file.endswith('.docx') or file.endswith('.doc'):
                        docx_path = os.path.join(PDFS_DIR, file)
                        shutil.copy(temp_path, docx_path)

                        pdf_path = convert_docx_to_pdf(docx_path)
                        if pdf_path:
                            downloaded_pdfs.append(pdf_path)
                            try:
                                os.remove(docx_path)
                            except:
                                pass
                        else:
                            logger.warning(f"  Could not convert: {file}")
                    else:
                        logger.warning(f"  Skipping non-supported file: {file}")

            try:
                shutil.rmtree(temp_dir)
            except:
                pass

        except Exception as e:
            logger.error(f"Error downloading folder: {e}")
            import traceback
            traceback.print_exc()

        logger.info(f"\nTotal PDF files ready: {len(downloaded_pdfs)}")
        return downloaded_pdfs


class NextcloudStorage(ScheduleStorage):
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        if username and password:
            self.auth = (username, password)
        else:
            parsed = urlparse(base_url)
            path = unquote(parsed.path)
            match = re.search(r'/s/([^/]+)', path)
            if match:
                token = match.group(1)
                self.auth = (token, token)
            else:
                self.auth = None

    def _get_webdav_base(self) -> str:
        """Extract share token and build WebDAV base URL."""
        parsed = urlparse(self.base_url)
        path = unquote(parsed.path)
        match = re.search(r'/s/([^/]+)', path)
        if not match:
            raise ValueError("Invalid Nextcloud share URL")
        token = match.group(1)
        # Share token is used for HTTP Basic Auth, not as part of the URL path
        return f"{parsed.scheme}://{parsed.netloc}/public.php/webdav/"

    def _propfind(self, webdav_url: str) -> List[dict]:
        """List directory contents via WebDAV PROPFIND."""
        headers = {'Depth': '1'}
        body = '''<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <d:getcontentlength/>
  </d:prop>
</d:propfind>'''

        resp = requests.request('PROPFIND', webdav_url, auth=self.auth, headers=headers, data=body, timeout=30)
        if resp.status_code not in (200, 207):
            logger.warning(f"PROPFIND failed for {webdav_url}: {resp.status_code}")
            return []

        ns = {'d': 'DAV:', 'oc': 'http://owncloud.org/ns', 'nc': 'http://nextcloud.org/ns'}
        entries = []
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            logger.warning(f"Failed to parse WebDAV response for {webdav_url}")
            return []

        for response in root.findall('d:response', ns):
            href = response.find('d:href', ns)
            propstat = response.find('d:propstat', ns)
            if href is None or propstat is None:
                continue
            prop = propstat.find('d:prop', ns)
            if prop is None:
                continue
            displayname = prop.find('d:displayname', ns)
            resourcetype = prop.find('d:resourcetype', ns)
            contentlength = prop.find('d:getcontentlength', ns)
            raw_name = displayname.text if displayname is not None else href.text.rstrip('/').split('/')[-1]
            name = unquote(raw_name)
            is_collection = resourcetype.find('d:collection', ns) is not None if resourcetype is not None else False
            size = int(contentlength.text) if contentlength is not None and contentlength.text else 0
            entries.append({
                'name': name,
                'href': href.text,
                'is_collection': is_collection,
                'size': size,
            })
        return entries

    def _download_file(self, webdav_url: str, dest_path: str) -> None:
        """Download file from WebDAV URL to local path."""
        resp = requests.get(webdav_url, auth=self.auth, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    def _collect_files(self, webdav_url: str, collected: List[str]) -> None:
        """Recursively collect files from Nextcloud WebDAV."""
        entries = self._propfind(webdav_url)
        if not entries:
            return

        current_dir_name = unquote(webdav_url.rstrip('/').split('/')[-1])
        for entry in entries:
            name = entry['name']
            href = entry['href']
            is_collection = entry['is_collection']

            if is_collection:
                if name in ('..', '.', current_dir_name):
                    continue
                child_url = webdav_url + name + '/'
                logger.info(f"Entering directory: {name}")
                self._collect_files(child_url, collected)
            else:
                if name.lower().endswith(('.pdf', '.doc', '.docx')):
                    collected.append((name, webdav_url + name))

    def get_schedule_files(self) -> List[str]:
        webdav_base = self._get_webdav_base()
        logger.info(f"Fetching Nextcloud via WebDAV: {webdav_base}")

        parsed = urlparse(self.base_url)
        query = urlparse(self.base_url).query
        dir_param = ''
        if query:
            params = dict(param.split('=') for param in query.split('&') if '=' in param)
            dir_param = params.get('dir', '').lstrip('/')
        
        webdav_url = webdav_base + dir_param
        if webdav_url and not webdav_url.endswith('/'):
            webdav_url += '/'

        entries = self._propfind(webdav_url)
        if not entries:
            logger.warning("Nextcloud directory is empty or inaccessible")
            return []

        collected = []
        for entry in entries:
            if entry['is_collection']:
                if entry['name'] in ('..', '.'):
                    continue
                child_url = webdav_url + entry['name'] + '/'
                logger.info(f"Entering directory: {entry['name']}")
                self._collect_files(child_url, collected)
            else:
                if entry['name'].lower().endswith(('.pdf', '.doc', '.docx')):
                    collected.append((entry['name'], webdav_url + entry['name']))

        if not collected:
            logger.warning("No schedule files found in Nextcloud")
            return []

        downloaded_pdfs = []
        temp_dir = tempfile.mkdtemp(prefix='nextcloud_')

        for filename, file_url in collected:
            try:
                file_path = os.path.join(temp_dir, filename)
                logger.info(f"Downloading: {filename}")
                self._download_file(file_url, file_path)

                if filename.lower().endswith(('.doc', '.docx')):
                    pdf_path = convert_docx_to_pdf(file_path)
                    if pdf_path:
                        safe_name = re.sub(r'[^\w\s\-\.\u0400-\u04FF]', '', os.path.basename(pdf_path))
                        output_path = os.path.join(PDFS_DIR, safe_name)
                        if pdf_path != output_path and os.path.exists(pdf_path):
                            shutil.copy(pdf_path, output_path)
                            downloaded_pdfs.append(output_path)
                        else:
                            downloaded_pdfs.append(pdf_path)
                    try:
                        os.remove(file_path)
                    except:
                        pass
                elif filename.lower().endswith('.pdf'):
                    safe_name = re.sub(r'[^\w\s\-\.\u0400-\u04FF]', '', filename)
                    output_path = os.path.join(PDFS_DIR, safe_name)
                    shutil.copy(file_path, output_path)
                    downloaded_pdfs.append(output_path)
            except Exception as e:
                logger.error(f"Failed to download {filename}: {e}")

        try:
            shutil.rmtree(temp_dir)
        except:
            pass

        logger.info(f"\nTotal PDF files ready from Nextcloud: {len(downloaded_pdfs)}")
        return downloaded_pdfs


def create_storage() -> ScheduleStorage:
    storage_type = os.getenv('STORAGE_TYPE', 'google_drive').lower()

    if storage_type == 'google_drive':
        folder_id = os.getenv('FOLDER_ID')
        if not folder_id or folder_id == "your_folder_id_here":
            raise ValueError("FOLDER_ID is not set for google_drive storage")
        return GoogleDriveStorage(folder_id)
    elif storage_type == 'nextcloud':
        url = os.getenv('NEXTCLOUD_URL')
        if not url:
            raise ValueError("NEXTCLOUD_URL is not set for nextcloud storage")
        username = os.getenv('NEXTCLOUD_USERNAME')
        password = os.getenv('NEXTCLOUD_PASSWORD')
        return NextcloudStorage(url, username, password)
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
