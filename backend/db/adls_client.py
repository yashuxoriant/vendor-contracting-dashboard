"""
Azure Data Lake Storage (ADLS) Gen2 Client
Handles file operations in Azure Data Lake Storage
"""

from azure.storage.filedatalake import DataLakeServiceClient, FileSystemClient
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from typing import List, Optional, BinaryIO
import logging
from datetime import datetime, timedelta
import os

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class ADLSClient:
    """Azure Data Lake Storage Gen2 client wrapper"""
    
    def __init__(self):
        """Initialize ADLS client"""
        self.service_client: Optional[DataLakeServiceClient] = None
        self.file_systems: dict = {}
        
    def connect(self):
        """Connect to ADLS and auto-provision filesystems."""
        try:
            account_url = f"https://{settings.adls_account_name}.dfs.core.windows.net"
            self.service_client = DataLakeServiceClient(
                account_url=account_url,
                credential=settings.adls_account_key
            )
            logger.info(f"Connected to ADLS: {settings.adls_account_name}")

            # Auto-create filesystems then initialise references
            self.create_containers_if_not_exist()
            self._init_file_systems()

        except Exception as e:
            logger.error(f"Failed to connect to ADLS: {e}")
            raise
    
    def _init_file_systems(self):
        """Initialize file system clients for containers"""
        container_names = [
            settings.adls_container_raw_boms,
            settings.adls_container_processed,
            settings.adls_container_templates,
            settings.adls_container_exports,
            settings.adls_container_chat_history,
        ]
        
        for container in container_names:
            try:
                self.file_systems[container] = self.service_client.get_file_system_client(container)
                logger.info(f"Initialized file system: {container}")
            except ResourceNotFoundError:
                logger.warning(f"File system not found: {container}")
    
    def create_containers_if_not_exist(self):
        """Create containers if they don't exist"""
        containers = [
            settings.adls_container_raw_boms,
            settings.adls_container_processed,
            settings.adls_container_templates,
            settings.adls_container_exports,
            settings.adls_container_chat_history,
        ]
        
        for container in containers:
            try:
                file_system = self.service_client.create_file_system(container)
                logger.info(f"Created file system: {container}")
                self.file_systems[container] = file_system
            except ResourceExistsError:
                logger.info(f"File system already exists: {container}")
                self.file_systems[container] = self.service_client.get_file_system_client(container)
    
    # ========================================================================
    # File Operations
    # ========================================================================
    
    def upload_file(
        self,
        container: str,
        file_path: str,
        content: bytes,
        overwrite: bool = False
    ) -> str:
        """
        Upload a file to ADLS
        
        Args:
            container: Container name (raw-boms, processed-boms, etc.)
            file_path: Path within container (e.g., "2024/01/bom-123.xlsx")
            content: File content as bytes
            overwrite: Whether to overwrite existing file
            
        Returns:
            Full file path
        """
        try:
            file_system = self.file_systems[container]
            file_client = file_system.get_file_client(file_path)
            
            file_client.upload_data(content, overwrite=overwrite)
            
            full_path = f"{container}/{file_path}"
            logger.info(f"Uploaded file: {full_path}")
            return full_path
            
        except Exception as e:
            logger.error(f"Error uploading file to {container}/{file_path}: {e}")
            raise
    
    def download_file(self, container: str, file_path: str) -> bytes:
        """
        Download a file from ADLS
        
        Args:
            container: Container name
            file_path: Path within container
            
        Returns:
            File content as bytes
        """
        try:
            file_system = self.file_systems[container]
            file_client = file_system.get_file_client(file_path)
            
            download = file_client.download_file()
            content = download.readall()
            
            logger.info(f"Downloaded file: {container}/{file_path}")
            return content
            
        except ResourceNotFoundError:
            logger.warning(f"File not found: {container}/{file_path}")
            raise
        except Exception as e:
            logger.error(f"Error downloading file from {container}/{file_path}: {e}")
            raise
    
    def delete_file(self, container: str, file_path: str):
        """Delete a file from ADLS"""
        try:
            file_system = self.file_systems[container]
            file_client = file_system.get_file_client(file_path)
            file_client.delete_file()
            
            logger.info(f"Deleted file: {container}/{file_path}")
            
        except ResourceNotFoundError:
            logger.warning(f"File not found: {container}/{file_path}")
        except Exception as e:
            logger.error(f"Error deleting file {container}/{file_path}: {e}")
            raise
    
    def list_files(
        self,
        container: str,
        path: Optional[str] = None,
        recursive: bool = False
    ) -> List[dict]:
        """
        List files in a container
        
        Args:
            container: Container name
            path: Path prefix to filter (optional)
            recursive: Whether to list recursively
            
        Returns:
            List of file metadata dicts
        """
        try:
            file_system = self.file_systems[container]
            
            paths = file_system.get_paths(path=path, recursive=recursive)
            
            files = []
            for path_item in paths:
                if not path_item.is_directory:
                    files.append({
                        "name": path_item.name,
                        "size": path_item.content_length,
                        "last_modified": path_item.last_modified,
                        "container": container
                    })
            
            logger.info(f"Listed {len(files)} files in {container}/{path or ''}")
            return files
            
        except Exception as e:
            logger.error(f"Error listing files in {container}: {e}")
            raise
    
    def file_exists(self, container: str, file_path: str) -> bool:
        """Check if a file exists"""
        try:
            file_system = self.file_systems[container]
            file_client = file_system.get_file_client(file_path)
            file_client.get_file_properties()
            return True
        except ResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error checking file existence {container}/{file_path}: {e}")
            raise
    
    def get_file_properties(self, container: str, file_path: str) -> dict:
        """Get file metadata"""
        try:
            file_system = self.file_systems[container]
            file_client = file_system.get_file_client(file_path)
            properties = file_client.get_file_properties()
            
            return {
                "name": file_path,
                "size": properties.size,
                "last_modified": properties.last_modified,
                "content_type": properties.content_settings.content_type,
                "etag": properties.etag,
                "container": container
            }
            
        except Exception as e:
            logger.error(f"Error getting file properties {container}/{file_path}: {e}")
            raise
    
    # ========================================================================
    # Directory Operations
    # ========================================================================
    
    def create_directory(self, container: str, directory_path: str):
        """Create a directory in ADLS"""
        try:
            file_system = self.file_systems[container]
            directory_client = file_system.get_directory_client(directory_path)
            directory_client.create_directory()
            
            logger.info(f"Created directory: {container}/{directory_path}")
            
        except ResourceExistsError:
            logger.info(f"Directory already exists: {container}/{directory_path}")
        except Exception as e:
            logger.error(f"Error creating directory {container}/{directory_path}: {e}")
            raise
    
    def delete_directory(self, container: str, directory_path: str):
        """Delete a directory from ADLS"""
        try:
            file_system = self.file_systems[container]
            directory_client = file_system.get_directory_client(directory_path)
            directory_client.delete_directory()
            
            logger.info(f"Deleted directory: {container}/{directory_path}")
            
        except ResourceNotFoundError:
            logger.warning(f"Directory not found: {container}/{directory_path}")
        except Exception as e:
            logger.error(f"Error deleting directory {container}/{directory_path}: {e}")
            raise
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def generate_file_path(self, container: str, filename: str, date: Optional[datetime] = None) -> str:
        """
        Generate organized file path with year/month structure
        
        Args:
            container: Container name
            filename: File name
            date: Date for organization (default: today)
            
        Returns:
            Path like "2024/01/filename.xlsx"
        """
        if date is None:
            date = datetime.utcnow()
        
        year = date.strftime("%Y")
        month = date.strftime("%m")
        
        return f"{year}/{month}/{filename}"
    
    def get_sas_url(
        self,
        container: str,
        file_path: str,
        expiry_hours: int = 24
    ) -> str:
        """
        Generate SAS URL for temporary file access
        (Simplified version - full implementation needs SAS token generation)
        """
        # TODO: Implement proper SAS token generation
        base_url = f"https://{settings.adls_account_name}.dfs.core.windows.net"
        return f"{base_url}/{container}/{file_path}"


# Global ADLS client instance
adls_client = ADLSClient()


def get_adls_client() -> ADLSClient:
    """Get ADLS client instance"""
    if not adls_client.service_client:
        adls_client.connect()
    return adls_client
