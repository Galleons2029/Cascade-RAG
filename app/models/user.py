# -*- coding: utf-8 -*-
# @Time   : 2025/8/18 15:13
# @Author : Galleons
# @File   : user.py

"""
This file contains the user model for the application.
"""

from datetime import datetime, UTC
from typing import (
    TYPE_CHECKING,
    List,
    Optional,
)

import bcrypt
from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import BaseModel
from app.models.permission import UserRole

if TYPE_CHECKING:
    from app.models.session import Session


class User(BaseModel, table=True):
    """User model for storing user accounts.

    Attributes:
        id: The primary key
        email: User's email (unique)
        hashed_password: Bcrypt hashed password
        role: User's role (USER or ADMIN)
        is_active: Whether the user account is active
        display_name: Optional display name for the user
        last_login_at: Timestamp of last login
        created_at: When the user was created
        updated_at: When the user was last updated
        sessions: Relationship to user's chat sessions
    """

    id: int = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    role: UserRole = Field(default=UserRole.USER, index=True)
    is_active: bool = Field(default=True, index=True)
    display_name: Optional[str] = Field(default=None, max_length=100)
    last_login_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sessions: List["Session"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        """Verify if the provided password matches the hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def is_admin(self) -> bool:
        """Check if the user has admin role."""
        return self.role == UserRole.ADMIN

    def can_access_admin_features(self) -> bool:
        """Check if user can access administrative features."""
        return self.is_active and self.is_admin()


# Avoid circular imports
from app.models.session import Session  # noqa: E402
