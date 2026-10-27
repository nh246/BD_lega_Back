"""
LLM Configuration router for administrators: view and update active AI model parameters.
Re-exports router and handlers from app.routers.admin for compatibility.
"""

from fastapi import APIRouter
from app.routers.admin import (
    get_admin_llm_config as get_active_llm_config,
    update_admin_llm_config as update_llm_config,
    test_admin_llm_config,
    reset_admin_llm_config,
)

router = APIRouter()
