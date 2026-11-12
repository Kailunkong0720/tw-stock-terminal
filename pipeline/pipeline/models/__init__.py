"""SQLAlchemy 模型。新增模型後要在這裡匯入，讓 Alembic 看得到。"""

from pipeline.models.base import Base
from pipeline.models.ingest import IngestLog

__all__ = ["Base", "IngestLog"]
