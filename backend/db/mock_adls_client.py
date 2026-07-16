"""
Mock/Dummy ADLS Client
File system storage for local development without Azure
"""

from typing import List, Optional
import logging
from datetime import datetime
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class MockADLSClient:
    """Mock ADLS client using local file system"""
    
    def __init__(self):
        """Initialize mock client with local storage"""
        self.base_path = Path("./local_storage")
        self.containers = {
            "raw-boms": self.base_path / "raw-boms",
            "processed-boms": self.base_path / "processed-boms",
            "templates": self.base_path / "templates",
            "exports": self.base_path / "exports",
            "chat-history": self.base_path / "chat-history",
        }
        logger.info("Initialized MockADLSClient (local file system)")
    
    def connect(self):
        """Mock connect - create directories"""
        for container_path in self.containers.values():
            container_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Mock ADLS connected - using {self.base_path}")
    
    def create_containers_if_not_exist(self):
        """Mock container creation - already handled in connect"""
        self.connect()
    
    def upload_file(
        self,
        container: str,
        file_path: str,
        content: bytes,
        overwrite: bool = False
    ) -> str:
        """Upload file to local storage"""
        container_path = self.containers[container]
        full_path = container_path / file_path
        
        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if exists and overwrite flag
        if full_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {full_path}")
        
        # Write file
        with open(full_path, 'wb') as f:
            f.write(content)
        
        relative_path = f"{container}/{file_path}"
        logger.info(f"Mock uploaded file: {relative_path}")
        return relative_path
    
    def download_file(self, container: str, file_path: str) -> bytes:
        """Download file from local storage"""
        container_path = self.containers[container]
        full_path = container_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        with open(full_path, 'rb') as f:
            content = f.read()
        
        logger.info(f"Mock downloaded file: {container}/{file_path}")
        return content
    
    def delete_file(self, container: str, file_path: str):
        """Delete file from local storage"""
        container_path = self.containers[container]
        full_path = container_path / file_path
        
        if full_path.exists():
            full_path.unlink()
            logger.info(f"Mock deleted file: {container}/{file_path}")
        else:
            logger.warning(f"Mock file not found: {container}/{file_path}")
    
    def list_files(
        self,
        container: str,
        path: Optional[str] = None,
        recursive: bool = False
    ) -> List[dict]:
        """List files in local storage"""
        container_path = self.containers[container]
        search_path = container_path / path if path else container_path
        
        files = []
        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"
        
        for file_path in search_path.glob(pattern):
            if file_path.is_file():
                relative_path = file_path.relative_to(container_path)
                stat = file_path.stat()
                files.append({
                    "name": str(relative_path),
                    "size": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime),
                    "container": container
                })
        
        logger.info(f"Mock listed {len(files)} files in {container}/{path or ''}")
        return files
    
    def file_exists(self, container: str, file_path: str) -> bool:
        """Check if file exists in local storage"""
        container_path = self.containers[container]
        full_path = container_path / file_path
        return full_path.exists()
    
    def get_file_properties(self, container: str, file_path: str) -> dict:
        """Get file metadata from local storage"""
        container_path = self.containers[container]
        full_path = container_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {full_path}")
        
        stat = full_path.stat()
        return {
            "name": file_path,
            "size": stat.st_size,
            "last_modified": datetime.fromtimestamp(stat.st_mtime),
            "content_type": "application/octet-stream",
            "etag": str(stat.st_mtime),
            "container": container
        }
    
    def create_directory(self, container: str, directory_path: str):
        """Create directory in local storage"""
        container_path = self.containers[container]
        full_path = container_path / directory_path
        full_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Mock created directory: {container}/{directory_path}")
    
    def delete_directory(self, container: str, directory_path: str):
        """Delete directory from local storage"""
        container_path = self.containers[container]
        full_path = container_path / directory_path
        
        if full_path.exists():
            import shutil
            shutil.rmtree(full_path)
            logger.info(f"Mock deleted directory: {container}/{directory_path}")
    
    def generate_file_path(self, container: str, filename: str, date: Optional[datetime] = None) -> str:
        """Generate organized file path"""
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
        """Generate mock file URL"""
        return f"file:///{self.containers[container]}/{file_path}"
