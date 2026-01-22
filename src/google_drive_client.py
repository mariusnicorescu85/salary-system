"""
Google Drive Client
Handles file downloads from Google Drive
"""

import io
from typing import Optional, List
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import pandas as pd


SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


class GoogleDriveClient:
    """Client for interacting with Google Drive"""
    
    def __init__(self, credentials_path: str = 'credentials/google_drive_credentials.json',
                 token_path: str = 'credentials/google_drive_token.pickle'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Google Drive credentials not found at {self.credentials_path}. "
                        "Please download OAuth2 credentials from Google Cloud Console."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        self.service = build('drive', 'v3', credentials=creds)
    
    def download_file(self, file_id: str) -> bytes:
        """Download a file from Google Drive by file ID"""
        request = self.service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_content.seek(0)
        return file_content.read()
    
    def list_files_in_folder(self, folder_id: str) -> List[dict]:
        """List all files in a Google Drive folder"""
        query = f"'{folder_id}' in parents and trashed=false"
        results = self.service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        return results.get('files', [])
    
    def find_file_by_name(self, folder_id: str, filename: str) -> Optional[str]:
        """Find a file by name in a folder and return its file ID"""
        files = self.list_files_in_folder(folder_id)
        for file in files:
            if file['name'] == filename or file['name'].lower() == filename.lower():
                return file['id']
        return None
    
    def download_csv_as_dataframe(self, file_id: str) -> pd.DataFrame:
        """Download a CSV file and return as pandas DataFrame"""
        file_content = self.download_file(file_id)
        return pd.read_csv(io.BytesIO(file_content))
    
    def download_excel_as_dataframe(self, file_id: str) -> pd.DataFrame:
        """Download an Excel file and return as pandas DataFrame"""
        file_content = self.download_file(file_id)
        return pd.read_excel(io.BytesIO(file_content))
