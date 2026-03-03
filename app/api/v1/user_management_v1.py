# -*- coding: utf-8 -*-
# @Time   : 2026/2/1
# @Author : Galleons
# @File   : user_management_v1.py

"""
User Management API endpoints.

This module provides comprehensive user management functionality:
- User CRUD operations (admin only)
- Role management
- Knowledge base permission management
- Audit log access
- Self-service profile updates
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.permissions import (
    get_current_active_user,
    get_current_admin_user,
    get_client_ip,
)
from app.core.db.user_management_service import user_management_service
from app.core.logger_utils import logger
from app.models.permission import PermissionLevel, UserRole
from app.models.schemas.user_management import (
    AuditLogListResponse,
    AuditLogResponse,
    BulkOperationResponse,
    BulkPermissionGrantRequest,
    BulkRoleAssignRequest,
    KnowledgeBaseAccessCheck,
    KnowledgeBaseAccessResponse,
    PermissionGrantRequest,
    PermissionListResponse,
    PermissionResponse,
    PermissionRevokeRequest,
    UserCreateByAdmin,
    UserDetailResponse,
    UserListPaginatedResponse,
    UserListResponse,
    UserPasswordReset,
    UserPermissionSummary,
    UserSelfUpdate,
    UserUpdateByAdmin,
)
from app.models.user import User


router = APIRouter()


# ============ User Management (Admin Only) ============

@router.post("/users", response_model=UserListResponse, status_code=201)
async def create_user(
    request: Request,
    user_data: UserCreateByAdmin,
    admin: User = Depends(get_current_admin_user),
):
    """Create a new user (admin only).
    
    Args:
        request: FastAPI request object
        user_data: User creation data
        admin: Current admin user
        
    Returns:
        UserListResponse: The created user
    """
    # Check if email already exists
    existing = await user_management_service.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered",
        )
    
    # Hash password
    hashed_password = User.hash_password(user_data.password.get_secret_value())
    
    # Create user
    user = await user_management_service.create_user(
        email=user_data.email,
        hashed_password=hashed_password,
        role=user_data.role,
        display_name=user_data.display_name,
        is_active=user_data.is_active,
        created_by=admin.id,
    )
    
    logger.info(
        "user_created_via_api",
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        admin_id=admin.id,
    )
    
    return UserListResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/users", response_model=UserListPaginatedResponse)
async def list_users(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    role: Optional[UserRole] = Query(default=None, description="Filter by role"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    search: Optional[str] = Query(default=None, max_length=100, description="Search in email/name"),
    admin: User = Depends(get_current_admin_user),
):
    """List all users with pagination and filters (admin only).
    
    Args:
        page: Page number (1-based)
        page_size: Number of items per page
        role: Filter by user role
        is_active: Filter by active status
        search: Search term for email/display_name
        admin: Current admin user
        
    Returns:
        UserListPaginatedResponse: Paginated list of users
    """
    users, total = await user_management_service.list_users(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        search=search,
    )
    
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    
    return UserListPaginatedResponse(
        data=[
            UserListResponse(
                id=u.id,
                email=u.email,
                role=u.role,
                display_name=u.display_name,
                is_active=u.is_active,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=UserDetailResponse)
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
):
    """Get detailed user information (admin only).
    
    Args:
        user_id: ID of user to retrieve
        admin: Current admin user
        
    Returns:
        UserDetailResponse: User details with permissions
    """
    user = await user_management_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user permissions
    permissions = await user_management_service.get_user_permissions(user_id)
    
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        updated_at=user.updated_at,
        permissions=[
            PermissionResponse(
                id=p.id,
                user_id=p.user_id,
                knowledge_base_name=p.knowledge_base_name,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in permissions
        ],
    )


@router.patch("/users/{user_id}", response_model=UserListResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdateByAdmin,
    admin: User = Depends(get_current_admin_user),
):
    """Update user information (admin only).
    
    Args:
        user_id: ID of user to update
        user_data: Update data
        admin: Current admin user
        
    Returns:
        UserListResponse: Updated user
    """
    # Prevent admin from accidentally removing their own admin status
    if user_id == admin.id and user_data.role == UserRole.USER:
        raise HTTPException(
            status_code=400,
            detail="Cannot demote yourself from admin",
        )
    
    # Check if new email already exists
    if user_data.email:
        existing = await user_management_service.get_user_by_email(user_data.email)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=400,
                detail="Email already registered",
            )
    
    user = await user_management_service.update_user(
        user_id=user_id,
        updated_by=admin.id,
        email=user_data.email,
        role=user_data.role,
        display_name=user_data.display_name,
        is_active=user_data.is_active,
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserListResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
):
    """Delete (deactivate) a user (admin only).
    
    This performs a soft delete - the user account is deactivated but not removed.
    
    Args:
        user_id: ID of user to delete
        admin: Current admin user
    """
    # Prevent admin from deleting themselves
    if user_id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account",
        )
    
    success = await user_management_service.delete_user(user_id, deleted_by=admin.id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_user_password(
    user_id: int,
    password_data: UserPasswordReset,
    admin: User = Depends(get_current_admin_user),
):
    """Reset a user's password (admin only).
    
    Args:
        user_id: ID of user whose password to reset
        password_data: New password data
        admin: Current admin user
    """
    hashed_password = User.hash_password(password_data.new_password.get_secret_value())
    
    user = await user_management_service.update_user(
        user_id=user_id,
        updated_by=admin.id,
        hashed_password=hashed_password,
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    logger.info(
        "user_password_reset_by_admin",
        user_id=user_id,
        admin_id=admin.id,
    )


# ============ Permission Management (Admin Only) ============

@router.post("/permissions", response_model=PermissionResponse, status_code=201)
async def grant_permission(
    request: Request,
    permission_data: PermissionGrantRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Grant knowledge base permission to a user (admin only).
    
    Args:
        request: FastAPI request object
        permission_data: Permission grant data
        admin: Current admin user
        
    Returns:
        PermissionResponse: The granted permission
    """
    # Verify target user exists
    target_user = await user_management_service.get_user_by_id(permission_data.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    permission = await user_management_service.grant_permission(
        user_id=permission_data.user_id,
        permission_level=permission_data.permission_level,
        granted_by=admin.id,
        knowledge_base_name=permission_data.knowledge_base_name,
        expires_at=permission_data.expires_at,
        ip_address=get_client_ip(request),
    )
    
    return PermissionResponse(
        id=permission.id,
        user_id=permission.user_id,
        knowledge_base_name=permission.knowledge_base_name,
        permission_level=permission.permission_level,
        granted_by=permission.granted_by,
        granted_at=permission.granted_at,
        expires_at=permission.expires_at,
        is_active=permission.is_active,
    )


@router.delete("/permissions", status_code=204)
async def revoke_permission(
    request: Request,
    permission_data: PermissionRevokeRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Revoke a user's knowledge base permission (admin only).
    
    Args:
        request: FastAPI request object
        permission_data: Permission revoke data
        admin: Current admin user
    """
    success = await user_management_service.revoke_permission(
        user_id=permission_data.user_id,
        revoked_by=admin.id,
        knowledge_base_name=permission_data.knowledge_base_name,
        ip_address=get_client_ip(request),
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Permission not found")


@router.get("/users/{user_id}/permissions", response_model=PermissionListResponse)
async def get_user_permissions(
    user_id: int,
    include_expired: bool = Query(default=False, description="Include expired permissions"),
    admin: User = Depends(get_current_admin_user),
):
    """Get all permissions for a user (admin only).
    
    Args:
        user_id: ID of user
        include_expired: Whether to include expired permissions
        admin: Current admin user
        
    Returns:
        PermissionListResponse: List of permissions
    """
    permissions = await user_management_service.get_user_permissions(
        user_id, include_expired=include_expired
    )
    
    return PermissionListResponse(
        data=[
            PermissionResponse(
                id=p.id,
                user_id=p.user_id,
                knowledge_base_name=p.knowledge_base_name,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in permissions
        ],
        total=len(permissions),
    )


@router.get("/knowledge-bases/{kb_name}/permissions", response_model=PermissionListResponse)
async def get_knowledge_base_permissions(
    kb_name: str,
    admin: User = Depends(get_current_admin_user),
):
    """Get all permissions for a knowledge base (admin only).
    
    Args:
        kb_name: Name of the knowledge base
        admin: Current admin user
        
    Returns:
        PermissionListResponse: List of permissions
    """
    permissions = await user_management_service.get_knowledge_base_permissions(kb_name)
    
    return PermissionListResponse(
        data=[
            PermissionResponse(
                id=p.id,
                user_id=p.user_id,
                knowledge_base_name=p.knowledge_base_name,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in permissions
        ],
        total=len(permissions),
    )


@router.post("/permissions/check", response_model=KnowledgeBaseAccessResponse)
async def check_access(
    access_check: KnowledgeBaseAccessCheck,
    admin: User = Depends(get_current_admin_user),
):
    """Check if a user has access to a knowledge base (admin only).
    
    Args:
        access_check: Access check parameters
        admin: Current admin user
        
    Returns:
        KnowledgeBaseAccessResponse: Access check result
    """
    user = await user_management_service.get_user_by_id(access_check.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    has_access, actual_level = await user_management_service.check_permission(
        user_id=access_check.user_id,
        knowledge_base_name=access_check.knowledge_base_name,
        required_level=access_check.required_permission,
    )
    
    return KnowledgeBaseAccessResponse(
        has_access=has_access,
        user_role=user.role,
        permission_level=actual_level,
        is_admin_override=user.role == UserRole.ADMIN,
    )


@router.get("/users/{user_id}/permission-summary", response_model=UserPermissionSummary)
async def get_user_permission_summary(
    user_id: int,
    admin: User = Depends(get_current_admin_user),
):
    """Get a summary of user's permissions (admin only).
    
    Args:
        user_id: ID of user
        admin: Current admin user
        
    Returns:
        UserPermissionSummary: Permission summary
    """
    user = await user_management_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    permissions = await user_management_service.get_user_permissions(user_id)
    accessible_kbs = await user_management_service.get_accessible_knowledge_bases(user_id)
    
    # Check for global access
    has_global = any(p.knowledge_base_name is None for p in permissions)
    
    return UserPermissionSummary(
        user_id=user_id,
        role=user.role,
        has_global_access=has_global or user.role == UserRole.ADMIN,
        accessible_knowledge_bases=accessible_kbs if accessible_kbs != ["*"] else [],
        permission_details=[
            PermissionResponse(
                id=p.id,
                user_id=p.user_id,
                knowledge_base_name=p.knowledge_base_name,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in permissions
        ],
    )


# ============ Bulk Operations (Admin Only) ============

@router.post("/permissions/bulk-grant", response_model=BulkOperationResponse)
async def bulk_grant_permissions(
    request: Request,
    bulk_data: BulkPermissionGrantRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Grant permissions to multiple users (admin only).
    
    Args:
        request: FastAPI request object
        bulk_data: Bulk grant data
        admin: Current admin user
        
    Returns:
        BulkOperationResponse: Results of bulk operation
    """
    success_count, failures = await user_management_service.bulk_grant_permission(
        user_ids=bulk_data.user_ids,
        permission_level=bulk_data.permission_level,
        granted_by=admin.id,
        knowledge_base_name=bulk_data.knowledge_base_name,
    )
    
    return BulkOperationResponse(
        success_count=success_count,
        failure_count=len(failures),
        failures=failures,
    )


@router.post("/users/bulk-role-assign", response_model=BulkOperationResponse)
async def bulk_assign_roles(
    bulk_data: BulkRoleAssignRequest,
    admin: User = Depends(get_current_admin_user),
):
    """Assign role to multiple users (admin only).
    
    Args:
        bulk_data: Bulk role assignment data
        admin: Current admin user
        
    Returns:
        BulkOperationResponse: Results of bulk operation
    """
    # Prevent admin from demoting themselves via bulk operation
    if admin.id in bulk_data.user_ids and bulk_data.role == UserRole.USER:
        raise HTTPException(
            status_code=400,
            detail="Cannot demote yourself from admin via bulk operation",
        )
    
    success_count, failures = await user_management_service.bulk_assign_role(
        user_ids=bulk_data.user_ids,
        role=bulk_data.role,
        assigned_by=admin.id,
    )
    
    return BulkOperationResponse(
        success_count=success_count,
        failure_count=len(failures),
        failures=failures,
    )


# ============ Audit Logs (Admin Only) ============

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def get_audit_logs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    actor_id: Optional[int] = Query(default=None, description="Filter by actor ID"),
    action: Optional[str] = Query(default=None, description="Filter by action type"),
    target_type: Optional[str] = Query(default=None, description="Filter by target type"),
    admin: User = Depends(get_current_admin_user),
):
    """Get audit logs with pagination and filters (admin only).
    
    Args:
        page: Page number (1-based)
        page_size: Number of items per page
        actor_id: Filter by actor ID
        action: Filter by action type
        target_type: Filter by target type
        admin: Current admin user
        
    Returns:
        AuditLogListResponse: Paginated audit logs
    """
    logs, total = await user_management_service.get_audit_logs(
        page=page,
        page_size=page_size,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
    )
    
    return AuditLogListResponse(
        data=[
            AuditLogResponse(
                id=log.id,
                actor_id=log.actor_id,
                action=log.action,
                target_type=log.target_type,
                target_id=log.target_id,
                details=log.details,
                ip_address=log.ip_address,
                timestamp=log.timestamp,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============ Self-Service (Any Authenticated User) ============

@router.get("/me", response_model=UserDetailResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    """Get current user's profile.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        UserDetailResponse: User's profile with permissions
    """
    permissions = await user_management_service.get_user_permissions(current_user.id)
    
    return UserDetailResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        updated_at=current_user.updated_at,
        permissions=[
            PermissionResponse(
                id=p.id,
                user_id=p.user_id,
                knowledge_base_name=p.knowledge_base_name,
                permission_level=p.permission_level,
                granted_by=p.granted_by,
                granted_at=p.granted_at,
                expires_at=p.expires_at,
                is_active=p.is_active,
            )
            for p in permissions
        ],
    )


@router.patch("/me", response_model=UserListResponse)
async def update_current_user_profile(
    update_data: UserSelfUpdate,
    current_user: User = Depends(get_current_active_user),
):
    """Update current user's profile.
    
    Users can update their display name and password.
    
    Args:
        update_data: Profile update data
        current_user: Current authenticated user
        
    Returns:
        UserListResponse: Updated profile
    """
    # If changing password, verify current password
    hashed_password = None
    if update_data.new_password:
        if not current_user.verify_password(update_data.current_password.get_secret_value()):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect",
            )
        hashed_password = User.hash_password(update_data.new_password.get_secret_value())
    
    user = await user_management_service.update_user(
        user_id=current_user.id,
        updated_by=current_user.id,
        display_name=update_data.display_name,
        hashed_password=hashed_password,
    )
    
    return UserListResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/me/accessible-knowledge-bases", response_model=list[str])
async def get_my_accessible_knowledge_bases(
    current_user: User = Depends(get_current_active_user),
):
    """Get list of knowledge bases the current user can access.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        List of accessible knowledge base names
    """
    accessible = await user_management_service.get_accessible_knowledge_bases(current_user.id)
    return accessible
