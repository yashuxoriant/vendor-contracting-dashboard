"""
Template management API endpoints
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional

from db import get_cosmos_client, Template

router = APIRouter(prefix="/api/templates", tags=["templates"])


# Response Models
class TemplateResponse(BaseModel):
    template: Template


class TemplateListResponse(BaseModel):
    templates: List[Template]
    count: int


@router.get("", response_model=TemplateListResponse)
async def list_templates():
    """
    List all available BOM templates
    """
    try:
        cosmos_client = get_cosmos_client()
        
        # Query all templates
        templates_data = cosmos_client.query_items(
            "templates",
            "SELECT * FROM c"
        )
        
        templates = [Template(**t) for t in templates_data]
        
        return TemplateListResponse(
            templates=templates,
            count=len(templates)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )


@router.get("/{category}", response_model=TemplateResponse)
async def get_template(category: str):
    """
    Get template for a specific category
    """
    try:
        cosmos_client = get_cosmos_client()
        
        # Query for template by category
        templates_data = cosmos_client.query_items(
            "templates",
            f"SELECT * FROM c WHERE c.category = '{category}'"
        )
        
        if not templates_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No template found for category: {category}"
            )
        
        return TemplateResponse(template=Template(**templates_data[0]))
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template: {str(e)}"
        )
