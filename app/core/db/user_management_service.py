# -*- coding: utf-8 -*-
# @Time   : 2026/2/1
# @Author : Galleons
# @File   : user_management_service.py

"""
Database service for user management and permission operations.

This module provides CRUD operations for:
- User management (create, read, update, delete, list)
- Role management (assign, revoke)
- Knowledge base permission management
- Audit logging
"""

import json
from datetime import datetime, UTC
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_, func
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.core.db.postgre import async_session
from app.core.logger_utils import logger
from app.models.permission import (
    AuditLog,
    KnowledgeBasePermission,
    PermissionLevel,
    UserKnowledgeBaseAccess,
    UserRole,
)
from app.models.user import User


class UserManagementService:
    """Service class for user management and permission operations.
    
    Provides methods for:
    - User CRUD operations
    - Role management
    - Permission management
    - Audit logging
    - Access control checks
    """

    def __init__(self):
        """Initialize the service with async session maker."""
        self.session_maker = async_session

    # ============ User Management ============

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        role: UserRole = UserRole.USER,
        display_name: Optional[str] = None,
        is_active: bool = True,
        created_by: Optional[int] = None,
    ) -> User:
        """Create a new user.
        
        Args:
            email: User's email address
            hashed_password: Already hashed password
            role: User role (defaults to USER)
            display_name: Optional display name
            is_active: Whether account is active
            created_by: ID of admin who created the user
            
        Returns:
            User: The created user
        """
        async with self.session_maker() as session:
            user = User(
                email=email,
                hashed_password=hashed_password,
                role=role,
                display_name=display_name,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Log the action
            if created_by:
                await self._log_action(
                    session,
                    actor_id=created_by,
                    action="user_created",
                    target_type="user",
                    target_id=str(user.id),
                    details=json.dumps({"email": email, "role": role.value}),
                )
            
            logger.info("user_created_by_admin", email=email, role=role.value, created_by=created_by)
            return user

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        async with self.session_maker() as session:
            return await session.get(User, user_id)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        async with self.session_maker() as session:
            statement = select(User).where(User.email == email)
            result = await session.exec(statement)
            return result.first()

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[UserRole] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        """List users with pagination and filters.
        
        Args:
            page: Page number (1-based)
            page_size: Number of items per page
            role: Filter by role
            is_active: Filter by active status
            search: Search in email and display_name
            
        Returns:
            Tuple of (list of users, total count)
        """
        async with self.session_maker() as session:
            # Build query
            statement = select(User)
            count_statement = select(func.count(User.id))
            
            conditions = []
            if role is not None:
                conditions.append(User.role == role)
            if is_active is not None:
                conditions.append(User.is_active == is_active)
            if search:
                search_pattern = f"%{search}%"
                conditions.append(
                    or_(
                        User.email.ilike(search_pattern),
                        User.display_name.ilike(search_pattern),
                    )
                )
            
            if conditions:
                statement = statement.where(and_(*conditions))
                count_statement = count_statement.where(and_(*conditions))
            
            # Get total count
            count_result = await session.exec(count_statement)
            total = count_result.one()
            
            # Apply pagination
            offset = (page - 1) * page_size
            statement = statement.offset(offset).limit(page_size).order_by(User.created_at.desc())
            
            result = await session.exec(statement)
            users = list(result.all())
            
            return users, total

    async def update_user(
        self,
        user_id: int,
        updated_by: int,
        email: Optional[str] = None,
        role: Optional[UserRole] = None,
        display_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        hashed_password: Optional[str] = None,
    ) -> Optional[User]:
        """Update a user's information.
        
        Args:
            user_id: ID of user to update
            updated_by: ID of admin performing the update
            email: New email (optional)
            role: New role (optional)
            display_name: New display name (optional)
            is_active: New active status (optional)
            hashed_password: New hashed password (optional)
            
        Returns:
            Updated user or None if not found
        """
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                return None
            
            changes = {}
            if email is not None and email != user.email:
                changes["email"] = {"old": user.email, "new": email}
                user.email = email
            if role is not None and role != user.role:
                changes["role"] = {"old": user.role.value, "new": role.value}
                user.role = role
            if display_name is not None:
                changes["display_name"] = {"old": user.display_name, "new": display_name}
                user.display_name = display_name
            if is_active is not None and is_active != user.is_active:
                changes["is_active"] = {"old": user.is_active, "new": is_active}
                user.is_active = is_active
            if hashed_password is not None:
                changes["password"] = "changed"
                user.hashed_password = hashed_password
            
            user.updated_at = datetime.now(UTC)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Log the action
            await self._log_action(
                session,
                actor_id=updated_by,
                action="user_updated",
                target_type="user",
                target_id=str(user_id),
                details=json.dumps(changes),
            )
            
            logger.info("user_updated", user_id=user_id, changes=changes, updated_by=updated_by)
            return user

    async def delete_user(self, user_id: int, deleted_by: int) -> bool:
        """Delete a user (soft delete by setting is_active=False, or hard delete).
        
        For enterprise compliance, we perform soft delete by default.
        
        Args:
            user_id: ID of user to delete
            deleted_by: ID of admin performing the deletion
            
        Returns:
            True if deleted, False if not found
        """
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            
            # Soft delete - deactivate the user
            user.is_active = False
            user.updated_at = datetime.now(UTC)
            session.add(user)
            
            # Also deactivate all permissions
            perm_statement = select(KnowledgeBasePermission).where(
                KnowledgeBasePermission.user_id == user_id
            )
            perm_result = await session.exec(perm_statement)
            for perm in perm_result.all():
                perm.is_active = False
                session.add(perm)
            
            await session.commit()
            
            # Log the action
            await self._log_action(
                session,
                actor_id=deleted_by,
                action="user_deleted",
                target_type="user",
                target_id=str(user_id),
                details=json.dumps({"email": user.email}),
            )
            
            logger.info("user_deleted", user_id=user_id, deleted_by=deleted_by)
            return True

    async def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        async with self.session_maker() as session:
            user = await session.get(User, user_id)
            if user:
                user.last_login_at = datetime.now(UTC)
                session.add(user)
                await session.commit()

    # ============ Permission Management ============

    async def grant_permission(
        self,
        user_id: int,
        permission_level: PermissionLevel,
        granted_by: int,
        knowledge_base_name: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        ip_address: Optional[str] = None,
    ) -> KnowledgeBasePermission:
        """Grant a permission to a user.
        
        Args:
            user_id: ID of user to grant permission to
            permission_level: Level of permission to grant
            granted_by: ID of admin granting the permission
            knowledge_base_name: Name of KB (null for global permission)
            expires_at: Optional expiration timestamp
            ip_address: IP address for audit logging
            
        Returns:
            The created permission
        """
        async with self.session_maker() as session:
            # Check if permission already exists
            statement = select(KnowledgeBasePermission).where(
                and_(
                    KnowledgeBasePermission.user_id == user_id,
                    KnowledgeBasePermission.knowledge_base_name == knowledge_base_name,
                    KnowledgeBasePermission.is_active == True,
                )
            )
            result = await session.exec(statement)
            existing = result.first()
            
            if existing:
                # Update existing permission
                existing.permission_level = permission_level
                existing.expires_at = expires_at
                existing.granted_by = granted_by
                existing.granted_at = datetime.now(UTC)
                session.add(existing)
                permission = existing
            else:
                # Create new permission
                permission = KnowledgeBasePermission(
                    user_id=user_id,
                    knowledge_base_name=knowledge_base_name,
                    permission_level=permission_level,
                    granted_by=granted_by,
                    expires_at=expires_at,
                    is_active=True,
                )
                session.add(permission)
            
            await session.commit()
            await session.refresh(permission)
            
            # Update access cache
            await self._update_access_cache(session, user_id, knowledge_base_name)
            
            # Log the action
            await self._log_action(
                session,
                actor_id=granted_by,
                action="permission_granted",
                target_type="permission",
                target_id=str(permission.id),
                details=json.dumps({
                    "user_id": user_id,
                    "knowledge_base": knowledge_base_name,
                    "level": permission_level.value,
                }),
                ip_address=ip_address,
            )
            
            logger.info(
                "permission_granted",
                user_id=user_id,
                knowledge_base=knowledge_base_name,
                level=permission_level.value,
                granted_by=granted_by,
            )
            return permission

    async def revoke_permission(
        self,
        user_id: int,
        revoked_by: int,
        knowledge_base_name: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Revoke a user's permission.
        
        Args:
            user_id: ID of user to revoke permission from
            revoked_by: ID of admin revoking the permission
            knowledge_base_name: Name of KB (null for global permission)
            ip_address: IP address for audit logging
            
        Returns:
            True if revoked, False if not found
        """
        async with self.session_maker() as session:
            statement = select(KnowledgeBasePermission).where(
                and_(
                    KnowledgeBasePermission.user_id == user_id,
                    KnowledgeBasePermission.knowledge_base_name == knowledge_base_name,
                    KnowledgeBasePermission.is_active == True,
                )
            )
            result = await session.exec(statement)
            permission = result.first()
            
            if not permission:
                return False
            
            permission.is_active = False
            session.add(permission)
            await session.commit()
            
            # Update access cache
            await self._update_access_cache(session, user_id, knowledge_base_name)
            
            # Log the action
            await self._log_action(
                session,
                actor_id=revoked_by,
                action="permission_revoked",
                target_type="permission",
                target_id=str(permission.id),
                details=json.dumps({
                    "user_id": user_id,
                    "knowledge_base": knowledge_base_name,
                }),
                ip_address=ip_address,
            )
            
            logger.info(
                "permission_revoked",
                user_id=user_id,
                knowledge_base=knowledge_base_name,
                revoked_by=revoked_by,
            )
            return True

    async def get_user_permissions(
        self,
        user_id: int,
        include_expired: bool = False,
    ) -> List[KnowledgeBasePermission]:
        """Get all permissions for a user.
        
        Args:
            user_id: ID of user
            include_expired: Whether to include expired permissions
            
        Returns:
            List of permissions
        """
        async with self.session_maker() as session:
            conditions = [
                KnowledgeBasePermission.user_id == user_id,
                KnowledgeBasePermission.is_active == True,
            ]
            
            if not include_expired:
                conditions.append(
                    or_(
                        KnowledgeBasePermission.expires_at.is_(None),
                        KnowledgeBasePermission.expires_at > datetime.now(UTC),
                    )
                )
            
            statement = select(KnowledgeBasePermission).where(and_(*conditions))
            result = await session.exec(statement)
            return list(result.all())

    async def get_knowledge_base_permissions(
        self,
        knowledge_base_name: str,
    ) -> List[KnowledgeBasePermission]:
        """Get all permissions for a specific knowledge base.
        
        Args:
            knowledge_base_name: Name of the knowledge base
            
        Returns:
            List of active permissions
        """
        async with self.session_maker() as session:
            statement = select(KnowledgeBasePermission).where(
                and_(
                    KnowledgeBasePermission.knowledge_base_name == knowledge_base_name,
                    KnowledgeBasePermission.is_active == True,
                    or_(
                        KnowledgeBasePermission.expires_at.is_(None),
                        KnowledgeBasePermission.expires_at > datetime.now(UTC),
                    ),
                )
            )
            result = await session.exec(statement)
            return list(result.all())

    async def check_permission(
        self,
        user_id: int,
        knowledge_base_name: str,
        required_level: PermissionLevel,
    ) -> Tuple[bool, Optional[PermissionLevel]]:
        """Check if a user has the required permission level.
        
        Permission hierarchy: MANAGE > WRITE > READ
        
        Args:
            user_id: ID of user to check
            knowledge_base_name: Name of the knowledge base
            required_level: Minimum required permission level
            
        Returns:
            Tuple of (has_access, actual_permission_level)
        """
        async with self.session_maker() as session:
            # First check if user is admin
            user = await session.get(User, user_id)
            if user and user.role == UserRole.ADMIN:
                return True, PermissionLevel.MANAGE
            
            # Check specific KB permission
            statement = select(KnowledgeBasePermission).where(
                and_(
                    KnowledgeBasePermission.user_id == user_id,
                    or_(
                        KnowledgeBasePermission.knowledge_base_name == knowledge_base_name,
                        KnowledgeBasePermission.knowledge_base_name.is_(None),  # Global permission
                    ),
                    KnowledgeBasePermission.is_active == True,
                    or_(
                        KnowledgeBasePermission.expires_at.is_(None),
                        KnowledgeBasePermission.expires_at > datetime.now(UTC),
                    ),
                )
            )
            result = await session.exec(statement)
            permissions = list(result.all())
            
            if not permissions:
                return False, None
            
            # Find highest permission level
            level_order = {
                PermissionLevel.READ: 1,
                PermissionLevel.WRITE: 2,
                PermissionLevel.MANAGE: 3,
            }
            
            highest_perm = max(permissions, key=lambda p: level_order[p.permission_level])
            highest_level = highest_perm.permission_level
            
            # Check if meets required level
            has_access = level_order[highest_level] >= level_order[required_level]
            return has_access, highest_level

    async def get_accessible_knowledge_bases(self, user_id: int) -> List[str]:
        """Get list of knowledge bases a user can access.
        
        Args:
            user_id: ID of user
            
        Returns:
            List of knowledge base names
        """
        async with self.session_maker() as session:
            # Check if user is admin
            user = await session.get(User, user_id)
            if user and user.role == UserRole.ADMIN:
                return ["*"]  # Admin has access to all
            
            statement = select(KnowledgeBasePermission.knowledge_base_name).where(
                and_(
                    KnowledgeBasePermission.user_id == user_id,
                    KnowledgeBasePermission.is_active == True,
                    KnowledgeBasePermission.knowledge_base_name.is_not(None),
                    or_(
                        KnowledgeBasePermission.expires_at.is_(None),
                        KnowledgeBasePermission.expires_at > datetime.now(UTC),
                    ),
                )
            ).distinct()
            
            result = await session.exec(statement)
            return list(result.all())

    # ============ Audit Logging ============

    async def _log_action(
        self,
        session,
        actor_id: int,
        action: str,
        target_type: str,
        target_id: str,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Log an administrative action.
        
        This is an internal method called within existing sessions.
        """
        try:
            log_entry = AuditLog(
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details,
                ip_address=ip_address,
            )
            session.add(log_entry)
            await session.commit()
        except SQLAlchemyError as e:
            logger.error("audit_log_failed", error=str(e), action=action)
            # Don't raise - audit logging shouldn't break the main operation

    async def get_audit_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        actor_id: Optional[int] = None,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[List[AuditLog], int]:
        """Query audit logs with filters.
        
        Args:
            page: Page number (1-based)
            page_size: Items per page
            actor_id: Filter by actor ID
            action: Filter by action type
            target_type: Filter by target type
            start_time: Filter by start time
            end_time: Filter by end time
            
        Returns:
            Tuple of (list of logs, total count)
        """
        async with self.session_maker() as session:
            statement = select(AuditLog)
            count_statement = select(func.count(AuditLog.id))
            
            conditions = []
            if actor_id is not None:
                conditions.append(AuditLog.actor_id == actor_id)
            if action is not None:
                conditions.append(AuditLog.action == action)
            if target_type is not None:
                conditions.append(AuditLog.target_type == target_type)
            if start_time is not None:
                conditions.append(AuditLog.timestamp >= start_time)
            if end_time is not None:
                conditions.append(AuditLog.timestamp <= end_time)
            
            if conditions:
                statement = statement.where(and_(*conditions))
                count_statement = count_statement.where(and_(*conditions))
            
            # Get total count
            count_result = await session.exec(count_statement)
            total = count_result.one()
            
            # Apply pagination
            offset = (page - 1) * page_size
            statement = statement.offset(offset).limit(page_size).order_by(AuditLog.timestamp.desc())
            
            result = await session.exec(statement)
            logs = list(result.all())
            
            return logs, total

    # ============ Helper Methods ============

    async def _update_access_cache(
        self,
        session,
        user_id: int,
        knowledge_base_name: Optional[str],
    ) -> None:
        """Update the access cache for a user's knowledge base.
        
        This method is called internally to maintain the quick-access table.
        """
        if knowledge_base_name is None:
            return  # Global permissions don't need caching
        
        try:
            # Check current permissions
            has_access, level = await self.check_permission(
                user_id, knowledge_base_name, PermissionLevel.READ
            )
            
            # Find or create cache entry
            statement = select(UserKnowledgeBaseAccess).where(
                and_(
                    UserKnowledgeBaseAccess.user_id == user_id,
                    UserKnowledgeBaseAccess.knowledge_base_name == knowledge_base_name,
                )
            )
            result = await session.exec(statement)
            cache_entry = result.first()
            
            if cache_entry:
                cache_entry.can_read = has_access and level is not None
                cache_entry.can_write = level in [PermissionLevel.WRITE, PermissionLevel.MANAGE] if level else False
                cache_entry.can_manage = level == PermissionLevel.MANAGE if level else False
                cache_entry.updated_at = datetime.now(UTC)
            else:
                cache_entry = UserKnowledgeBaseAccess(
                    user_id=user_id,
                    knowledge_base_name=knowledge_base_name,
                    can_read=has_access and level is not None,
                    can_write=level in [PermissionLevel.WRITE, PermissionLevel.MANAGE] if level else False,
                    can_manage=level == PermissionLevel.MANAGE if level else False,
                )
            
            session.add(cache_entry)
            await session.commit()
        except SQLAlchemyError as e:
            logger.error("access_cache_update_failed", error=str(e))

    async def bulk_grant_permission(
        self,
        user_ids: List[int],
        permission_level: PermissionLevel,
        granted_by: int,
        knowledge_base_name: Optional[str] = None,
    ) -> Tuple[int, List[dict]]:
        """Grant permissions to multiple users.
        
        Args:
            user_ids: List of user IDs
            permission_level: Permission level to grant
            granted_by: ID of admin granting permissions
            knowledge_base_name: Name of KB (null for global)
            
        Returns:
            Tuple of (success_count, list of failures)
        """
        success_count = 0
        failures = []
        
        for user_id in user_ids:
            try:
                await self.grant_permission(
                    user_id=user_id,
                    permission_level=permission_level,
                    granted_by=granted_by,
                    knowledge_base_name=knowledge_base_name,
                )
                success_count += 1
            except Exception as e:
                failures.append({"user_id": user_id, "error": str(e)})
        
        return success_count, failures

    async def bulk_assign_role(
        self,
        user_ids: List[int],
        role: UserRole,
        assigned_by: int,
    ) -> Tuple[int, List[dict]]:
        """Assign role to multiple users.
        
        Args:
            user_ids: List of user IDs
            role: Role to assign
            assigned_by: ID of admin assigning roles
            
        Returns:
            Tuple of (success_count, list of failures)
        """
        success_count = 0
        failures = []
        
        for user_id in user_ids:
            try:
                result = await self.update_user(user_id, updated_by=assigned_by, role=role)
                if result:
                    success_count += 1
                else:
                    failures.append({"user_id": user_id, "error": "User not found"})
            except Exception as e:
                failures.append({"user_id": user_id, "error": str(e)})
        
        return success_count, failures


# Create singleton instance
user_management_service = UserManagementService()
