# -*- coding: utf-8 -*-
# @Time   : 2026/2/1
# @Author : Galleons
# @File   : permission.py

"""
User roles and knowledge base permission models for enterprise-level access control.

This module defines:
- UserRole: Enum for user roles (USER, ADMIN)
- PermissionLevel: Enum for knowledge base access levels
- KnowledgeBasePermission: Model for user-knowledge base permission mapping
"""

from datetime import datetime, UTC
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel


class UserRole(str, Enum):
    """User role enumeration.
    
    Defines the available roles in the system:
    - USER: Regular user with limited permissions
    - ADMIN: Administrator with full system access
    """
    USER = "user"
    ADMIN = "admin"


class PermissionLevel(str, Enum):
    """Permission level for knowledge base access.
    
    Defines what a user can do with a knowledge base:
    - READ: Can only view/search the knowledge base
    - WRITE: Can view, search, and add/update content
    - MANAGE: Full control including delete and permission management
    """
    READ = "read"
    WRITE = "write"
    MANAGE = "manage"


if TYPE_CHECKING:
    from app.models.user import User


class KnowledgeBasePermission(SQLModel, table=True):
    """Permission model for user access to knowledge bases.
    
    Links users to knowledge bases with specific permission levels.
    Supports both collection-specific and global permissions.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to the user
        knowledge_base_name: Name of the Qdrant collection (null for global permissions)
        permission_level: The level of access granted
        granted_by: ID of the admin who granted this permission
        granted_at: Timestamp when the permission was granted
        expires_at: Optional expiration timestamp for temporary permissions
        is_active: Whether the permission is currently active
        user: Relationship to the User model
    """
    __tablename__ = "knowledge_base_permission"
    
    id: int = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    knowledge_base_name: Optional[str] = Field(default=None, index=True)
    permission_level: PermissionLevel = Field(default=PermissionLevel.READ)
    granted_by: Optional[int] = Field(default=None, foreign_key="user.id")
    granted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = Field(default=None)
    is_active: bool = Field(default=True)
    
    # Note: We cannot use Relationship here for user as it would create ambiguity
    # with granted_by also referencing user.id
    
    class Config:
        use_enum_values = True


class UserKnowledgeBaseAccess(SQLModel, table=True):
    """Quick access table for caching user's accessible knowledge bases.
    
    This table provides fast lookups for which knowledge bases a user can access.
    It is automatically updated when permissions change.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to the user
        knowledge_base_name: Name of the Qdrant collection
        can_read: Whether user has read access
        can_write: Whether user has write access
        can_manage: Whether user has manage access
        updated_at: Last update timestamp
    """
    __tablename__ = "user_knowledge_base_access"
    
    id: int = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    knowledge_base_name: str = Field(index=True)
    can_read: bool = Field(default=False)
    can_write: bool = Field(default=False)
    can_manage: bool = Field(default=False)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditLog(SQLModel, table=True):
    """Audit log for tracking user management and permission changes.
    
    Records all administrative actions for compliance and security monitoring.
    
    Attributes:
        id: Primary key
        actor_id: ID of the user who performed the action
        action: Type of action performed
        target_type: Type of entity affected (user, permission, knowledge_base)
        target_id: Identifier of the affected entity
        details: JSON string with additional action details
        ip_address: IP address from which the action was performed
        timestamp: When the action occurred
    """
    __tablename__ = "audit_log"
    
    id: int = Field(default=None, primary_key=True)
    actor_id: int = Field(foreign_key="user.id", index=True)
    action: str = Field(index=True)
    target_type: str = Field(index=True)
    target_id: str
    details: Optional[str] = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), index=True)
