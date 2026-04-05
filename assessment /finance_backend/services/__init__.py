"""Service layer grouped by domain so the flow is easy to review."""

from .dashboard import DashboardService
from .records import RecordService
from .users import UserService

__all__ = ["DashboardService", "RecordService", "UserService"]
