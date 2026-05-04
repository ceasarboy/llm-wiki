from .auth import router as auth_router
from .users import router as users_router
from .logs import router as logs_router
from .pages import router as pages_router
from .raw import router as raw_router
from .pdf import router as pdf_router, legacy_router as pdfs_legacy_router
from .search import router as search_router
from .ingest import router as ingest_router
from .config import router as config_router
from .graph import router as graph_router
from .maintenance import router as maintenance_router

__all__ = [
    "auth_router",
    "users_router",
    "logs_router",
    "pages_router",
    "raw_router",
    "pdf_router",
    "pdfs_legacy_router",
    "search_router",
    "ingest_router",
    "config_router",
    "graph_router",
    "maintenance_router",
]
