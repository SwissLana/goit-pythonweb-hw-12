"""Schemas for service-level endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str
