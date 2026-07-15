"""
Azure Cosmos DB Client
Manages connections and operations with Cosmos DB
"""

from azure.cosmos import CosmosClient, exceptions, PartitionKey
from azure.cosmos.database import DatabaseProxy
from azure.cosmos.container import ContainerProxy
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from config import get_settings
from db.schemas import BOM, ChatSession, Pattern, Template, User, AnalyticsMetric

logger = logging.getLogger(__name__)
settings = get_settings()


class CosmosDBClient:
    """Cosmos DB client wrapper"""
    
    def __init__(self):
        """Initialize Cosmos DB client"""
        self.client: Optional[CosmosClient] = None
        self.database: Optional[DatabaseProxy] = None
        self.containers: Dict[str, ContainerProxy] = {}
        
    def connect(self):
        """Connect to Cosmos DB and auto-provision database + containers."""
        try:
            self.client = CosmosClient(
                settings.cosmos_db_endpoint,
                credential=settings.cosmos_db_key
            )
            # Auto-create database if it doesn't exist
            self.database = self.client.create_database_if_not_exists(
                id=settings.cosmos_db_database
            )
            logger.info(f"Connected to Cosmos DB: {settings.cosmos_db_database}")

            # Auto-create containers then initialise references
            self.create_containers_if_not_exist()
            self._init_containers()

        except Exception as e:
            logger.error(f"Failed to connect to Cosmos DB: {e}")
            raise
    
    def _init_containers(self):
        """Initialize container references"""
        container_names = [
            settings.cosmos_container_sessions,
            settings.cosmos_container_boms,
            settings.cosmos_container_patterns,
            settings.cosmos_container_templates,
            settings.cosmos_container_analytics,
            settings.cosmos_container_users
        ]
        
        for container_name in container_names:
            try:
                self.containers[container_name] = self.database.get_container_client(container_name)
                logger.info(f"Initialized container: {container_name}")
            except exceptions.CosmosResourceNotFoundError:
                logger.warning(f"Container not found: {container_name}")
    
    def create_containers_if_not_exist(self):
        """Create containers if they don't exist"""
        # Sessions container
        try:
            self.database.create_container(
                id=settings.cosmos_container_sessions,
                partition_key=PartitionKey(path="/user_id"),
                default_ttl=86400 * 30  # 30 days TTL
            )
            logger.info(f"Created container: {settings.cosmos_container_sessions}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # BOMs container
        try:
            self.database.create_container(
                id=settings.cosmos_container_boms,
                partition_key=PartitionKey(path="/project_name")
            )
            logger.info(f"Created container: {settings.cosmos_container_boms}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # Patterns container
        try:
            self.database.create_container(
                id=settings.cosmos_container_patterns,
                partition_key=PartitionKey(path="/category")
            )
            logger.info(f"Created container: {settings.cosmos_container_patterns}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # Templates container
        try:
            self.database.create_container(
                id=settings.cosmos_container_templates,
                partition_key=PartitionKey(path="/category")
            )
            logger.info(f"Created container: {settings.cosmos_container_templates}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # Analytics container
        try:
            self.database.create_container(
                id=settings.cosmos_container_analytics,
                partition_key=PartitionKey(path="/metric_type")
            )
            logger.info(f"Created container: {settings.cosmos_container_analytics}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # Users container
        try:
            self.database.create_container(
                id=settings.cosmos_container_users,
                partition_key=PartitionKey(path="/user_id")
            )
            logger.info(f"Created container: {settings.cosmos_container_users}")
        except exceptions.CosmosResourceExistsError:
            pass
        
        # Reinitialize container references
        self._init_containers()
    
    # ========================================================================
    # Generic CRUD Operations
    # ========================================================================
    
    def create_item(self, container_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create an item in a container"""
        try:
            container = self.containers[container_name]
            created_item = container.create_item(body=item)
            logger.info(f"Created item in {container_name}: {item.get('id')}")
            return created_item
        except Exception as e:
            logger.error(f"Error creating item in {container_name}: {e}")
            raise
    
    def read_item(
        self, 
        container_name: str, 
        item_id: str, 
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """Read an item from a container"""
        try:
            container = self.containers[container_name]
            item = container.read_item(item=item_id, partition_key=partition_key)
            return item
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(f"Item not found: {item_id} in {container_name}")
            return None
        except Exception as e:
            logger.error(f"Error reading item from {container_name}: {e}")
            raise
    
    def update_item(
        self, 
        container_name: str, 
        item_id: str, 
        item: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an item in a container"""
        try:
            container = self.containers[container_name]
            item['modified_at'] = datetime.utcnow().isoformat()
            updated_item = container.upsert_item(body=item)
            logger.info(f"Updated item in {container_name}: {item_id}")
            return updated_item
        except Exception as e:
            logger.error(f"Error updating item in {container_name}: {e}")
            raise
    
    def delete_item(
        self, 
        container_name: str, 
        item_id: str, 
        partition_key: str
    ):
        """Delete an item from a container"""
        try:
            container = self.containers[container_name]
            container.delete_item(item=item_id, partition_key=partition_key)
            logger.info(f"Deleted item from {container_name}: {item_id}")
        except Exception as e:
            logger.error(f"Error deleting item from {container_name}: {e}")
            raise
    
    def query_items(
        self, 
        container_name: str, 
        query: str, 
        parameters: Optional[List[Dict[str, Any]]] = None,
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query items from a container"""
        try:
            container = self.containers[container_name]
            
            if partition_key:
                items = list(container.query_items(
                    query=query,
                    parameters=parameters or [],
                    partition_key=partition_key
                ))
            else:
                items = list(container.query_items(
                    query=query,
                    parameters=parameters or [],
                    enable_cross_partition_query=True
                ))
            
            return items
        except Exception as e:
            logger.error(f"Error querying items from {container_name}: {e}")
            raise
    
    # ========================================================================
    # Specific Operations for BOMs  (dict-based — same interface as MockCosmosDBClient)
    # ========================================================================

    def create_bom(self, bom_data: dict) -> dict:
        """Create BOM — accepts and returns plain dict."""
        return self.create_item(settings.cosmos_container_boms, bom_data)

    def get_bom(self, bom_id: str) -> Optional[dict]:
        """Get BOM by ID.  Uses cross-partition query so no project_name needed."""
        try:
            items = self.query_items(
                settings.cosmos_container_boms,
                "SELECT * FROM c WHERE c.bom_id = @id OR c._id = @id OR c.id = @id",
                [{"name": "@id", "value": bom_id}],
            )
            return items[0] if items else None
        except Exception as e:
            logger.error("get_bom(%s) failed: %s", bom_id, e)
            return None

    def update_bom(self, bom_id: str, bom_data: dict) -> dict:
        """Update BOM — dict in, dict out."""
        return self.update_item(settings.cosmos_container_boms, bom_id, bom_data)

    def list_boms(self, filters: Optional[dict] = None, limit: int = 50) -> list:
        """List BOMs with optional dict filters — returns list of raw dicts."""
        query = "SELECT * FROM c"
        where_clauses: list = []
        parameters: list = []
        if filters:
            if filters.get("category"):
                where_clauses.append("c.category = @category")
                parameters.append({"name": "@category", "value": filters["category"]})
            if filters.get("status"):
                where_clauses.append("c.status = @status")
                parameters.append({"name": "@status", "value": filters["status"]})
            if filters.get("user_id"):
                where_clauses.append("c.created_by = @user_id")
                parameters.append({"name": "@user_id", "value": filters["user_id"]})
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        items = self.query_items(settings.cosmos_container_boms, query, parameters)
        return items[:limit]

    # ========================================================================
    # Specific Operations for Chat Sessions (dict-based)
    # ========================================================================

    def create_session(self, session_data: dict) -> dict:
        """Create session — dict in, dict out."""
        return self.create_item(settings.cosmos_container_sessions, session_data)

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID — cross-partition query (no user_id needed)."""
        try:
            items = self.query_items(
                settings.cosmos_container_sessions,
                "SELECT * FROM c WHERE c.session_id = @id OR c._id = @id OR c.id = @id",
                [{"name": "@id", "value": session_id}],
            )
            return items[0] if items else None
        except Exception as e:
            logger.error("get_session(%s) failed: %s", session_id, e)
            return None

    def update_session(self, session_id: str, session_data: dict) -> dict:
        """Update session — dict in, dict out."""
        return self.update_item(settings.cosmos_container_sessions, session_id, session_data)

    def list_sessions(self, user_id: Optional[str] = None, limit: int = 50) -> list:
        """List recent sessions.  Sorted in Python (avoids Cosmos composite index requirement)."""
        query = "SELECT c.session_id, c.user_id, c.status, c.created_at, c.updated_at, c.context FROM c"
        parameters: list = []
        if user_id:
            query += " WHERE c.user_id = @user_id"
            parameters.append({"name": "@user_id", "value": user_id})
        try:
            items = self.query_items(settings.cosmos_container_sessions, query, parameters)
        except Exception as exc:
            logger.warning("list_sessions query failed: %s", exc)
            return []
        items.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        return [
            {
                "session_id": s.get("session_id") or s.get("_id") or s.get("id"),
                "user_id": s.get("user_id"),
                "status": s.get("status", "active"),
                "created_at": s.get("created_at"),
                "updated_at": s.get("updated_at"),
                "message_count": len(s.get("conversation") or []),
                "context": s.get("context", {}),
            }
            for s in items[:limit]
        ]


    # ========================================================================
    # Close connection
    # ========================================================================
    
    def close(self):
        """Close Cosmos DB connection"""
        if self.client:
            # CosmosClient doesn't have explicit close method
            self.client = None
            logger.info("Closed Cosmos DB connection")


# Global Cosmos DB client instance
cosmos_client = CosmosDBClient()


def get_cosmos_client() -> CosmosDBClient:
    """Get Cosmos DB client instance"""
    if not cosmos_client.client:
        cosmos_client.connect()
    return cosmos_client
