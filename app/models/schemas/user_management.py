# -*- coding: utf-8 -*-
# @Time   : 2026/2/1
# @Author : Galleons
# @File   : user_management.py

"""
Pydantic schemas for user management and permission APIs.

This module provides request/response models for:
- User management (create, update, list, delete)
- Role management (assign, revoke)
- Knowledge base permission management
- Audit log queries
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator

from app.models.permission import PermissionLevel, UserRole


# ============ User Schemas ============

class UserCreateByAdmin(BaseModel):
    """Request model for admin to create a new user.
    
    Attributes:
        email: User's email address
        password: Initial password (will be hashed)
        role: User's role (defaults to USER)
        display_name: Optional display name
        is_active: Whether the account is active
    """
    email: EmailStr = Field(..., description="User's email address")
    password: SecretStr = Field(..., description="Initial password", min_length=8, max_length=64)
    role: UserRole = Field(default=UserRole.USER, description="User's role")
    display_name: Optional[str] = Field(default=None, max_length=100, description="Display name")
    is_active: bool = Field(default=True, description="Whether the account is active")


class UserUpdateByAdmin(BaseModel):
    """Request model for admin to update a user.
    
    All fields are optional - only provided fields will be updated.
    """
    email: Optional[EmailStr] = Field(default=None, description="New email address")
    role: Optional[UserRole] = Field(default=None, description="New role")
    display_name: Optional[str] = Field(default=None, max_length=100, description="New display name")
    is_active: Optional[bool] = Field(default=None, description="Account active status")


class UserPasswordReset(BaseModel):
    """Request model for admin to reset a user's password."""
    new_password: SecretStr = Field(..., description="New password", min_length=8, max_length=64)


class UserSelfUpdate(BaseModel):
    """Request model for user to update their own profile."""
    display_name: Optional[str] = Field(default=None, max_length=100, description="New display name")
    current_password: Optional[SecretStr] = Field(default=None, description="Current password for verification")
    new_password: Optional[SecretStr] = Field(default=None, min_length=8, max_length=64, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password_change(cls, v, info):
        """Ensure current_password is provided when changing password."""
        if v is not None and info.data.get("current_password") is None:
            raise ValueError("Current password is required to set a new password")
        return v


class UserListResponse(BaseModel):
    """Response model for user listing."""
    id: int = Field(..., description="User ID")
    email: str = Field(..., description="Email address")
    role: UserRole = Field(..., description="User role")
    display_name: Optional[str] = Field(default=None, description="Display name")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login_at: Optional[datetime] = Field(default=None, description="Last login timestamp")


class UserDetailResponse(UserListResponse):
    """Detailed response model for single user."""
    updated_at: datetime = Field(..., description="Last update timestamp")
    permissions: List["PermissionResponse"] = Field(default_factory=list, description="User's permissions")


class UserListPaginatedResponse(BaseModel):
    """Paginated response for user listing."""
    data: List[UserListResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


# ============ Permission Schemas ============

class PermissionGrantRequest(BaseModel):
    """Request model for granting knowledge base permission.
    
    Attributes:
        user_id: ID of the user to grant permission to
        knowledge_base_name: Name of the knowledge base (null for global permission)
        permission_level: Level of access to grant
        expires_at: Optional expiration timestamp
    """
    user_id: int = Field(..., description="User ID to grant permission to")
    knowledge_base_name: Optional[str] = Field(
        default=None, 
        max_length=128,
        description="Knowledge base name (null for global permission)"
    )
    permission_level: PermissionLevel = Field(..., description="Permission level to grant")
    expires_at: Optional[datetime] = Field(default=None, description="Optional expiration timestamp")


class PermissionRevokeRequest(BaseModel):
    """Request model for revoking knowledge base permission."""
    user_id: int = Field(..., description="User ID to revoke permission from")
    knowledge_base_name: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Knowledge base name (null to revoke global permission)"
    )


class PermissionResponse(BaseModel):
    """Response model for a single permission."""
    id: int = Field(..., description="Permission ID")
    user_id: int = Field(..., description="User ID")
    knowledge_base_name: Optional[str] = Field(default=None, description="Knowledge base name")
    permission_level: PermissionLevel = Field(..., description="Permission level")
    granted_by: Optional[int] = Field(default=None, description="Admin ID who granted this")
    granted_at: datetime = Field(..., description="When the permission was granted")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration timestamp")
    is_active: bool = Field(..., description="Whether the permission is active")


class PermissionListResponse(BaseModel):
    """Response model for listing permissions."""
    data: List[PermissionResponse] = Field(..., description="List of permissions")
    total: int = Field(..., description="Total number of permissions")


class UserPermissionSummary(BaseModel):
    """Summary of a user's permissions across all knowledge bases."""
    user_id: int = Field(..., description="User ID")
    role: UserRole = Field(..., description="User role")
    has_global_access: bool = Field(..., description="Whether user has global KB access")
    accessible_knowledge_bases: List[str] = Field(..., description="List of accessible KB names")
    permission_details: List[PermissionResponse] = Field(..., description="Detailed permissions")


# ============ Bulk Operation Schemas ============

class BulkPermissionGrantRequest(BaseModel):
    """Request for granting permissions to multiple users."""
    user_ids: List[int] = Field(..., min_length=1, description="List of user IDs")
    knowledge_base_name: Optional[str] = Field(default=None, max_length=128)
    permission_level: PermissionLevel = Field(..., description="Permission level to grant")


class BulkRoleAssignRequest(BaseModel):
    """Request for assigning role to multiple users."""
    user_ids: List[int] = Field(..., min_length=1, description="List of user IDs")
    role: UserRole = Field(..., description="Role to assign")


class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""
    success_count: int = Field(..., description="Number of successful operations")
    failure_count: int = Field(..., description="Number of failed operations")
    failures: List[dict] = Field(default_factory=list, description="Details of failures")


# ============ Audit Log Schemas ============

class AuditLogQuery(BaseModel):
    """Query parameters for audit log search."""
    actor_id: Optional[int] = Field(default=None, description="Filter by actor ID")
    action: Optional[str] = Field(default=None, description="Filter by action type")
    target_type: Optional[str] = Field(default=None, description="Filter by target type")
    start_time: Optional[datetime] = Field(default=None, description="Start time for range")
    end_time: Optional[datetime] = Field(default=None, description="End time for range")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")


class AuditLogResponse(BaseModel):
    """Response model for a single audit log entry."""
    id: int = Field(..., description="Log entry ID")
    actor_id: int = Field(..., description="ID of user who performed action")
    action: str = Field(..., description="Action type")
    target_type: str = Field(..., description="Type of affected entity")
    target_id: str = Field(..., description="ID of affected entity")
    details: Optional[str] = Field(default=None, description="Additional details (JSON)")
    ip_address: Optional[str] = Field(default=None, description="IP address")
    timestamp: datetime = Field(..., description="When the action occurred")


class AuditLogListResponse(BaseModel):
    """Paginated response for audit log listing."""
    data: List[AuditLogResponse] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of entries")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")


# ============ Knowledge Base Access Schemas ============

class KnowledgeBaseAccessCheck(BaseModel):
    """Request to check user's access to a knowledge base."""
    user_id: int = Field(..., description="User ID to check")
    knowledge_base_name: str = Field(..., max_length=128, description="Knowledge base name")
    required_permission: PermissionLevel = Field(..., description="Required permission level")


class KnowledgeBaseAccessResponse(BaseModel):
    """Response for access check."""
    has_access: bool = Field(..., description="Whether user has required access")
    user_role: UserRole = Field(..., description="User's role")
    permission_level: Optional[PermissionLevel] = Field(
        default=None, 
        description="User's permission level for this KB"
    )
    is_admin_override: bool = Field(
        default=False, 
        description="Whether access is granted due to admin role"
    )


# Forward reference update
UserDetailResponse.model_rebuild()
