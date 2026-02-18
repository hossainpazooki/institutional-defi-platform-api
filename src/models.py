"""Shared base model for all domain schemas.

All Pydantic response/request schemas across domains should inherit from
CustomBaseModel for consistent serialization behavior.

SQLModel table models continue to inherit from SQLModel directly.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomBaseModel(BaseModel):
    """Base model with consistent serialization defaults.

    Features:
    - from_attributes: allows ORM model → schema conversion
    - populate_by_name: allows field aliases alongside field names
    - Datetime serialization: ISO 8601 with trailing Z
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_encoders={datetime: lambda v: v.isoformat() + "Z"},
    )
