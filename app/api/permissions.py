# -*- coding: utf-8 -*-
# @Time   : 2026/2/1
# @Author : Galleons
# @File   : permissions.py

"""
FastAPI dependency injection for permission and role checking.

This module provides reusable dependencies for:
- Checking user roles (admin, user)
- Checking knowledge base access permissions
- Rate limiting based on user role
- Audit logging for sensitive operations
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.db.db_services import database_service
from app.core.db.user_management_service import user_management_service
from app.core.logger_utils import logger
from app.models.permission import PermissionLevel, UserRole
from app.models.user import User
from app.utils.auth import verify_token
from app.utils.sanitization import sanitize_string


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user from JWT token.
    
    Args:
        credentials: HTTP authorization credentials containing JWT token
        
    Returns:
        User: The authenticated user
        
    Raises:
        HTTPException: If token is invalid or user not found
    """
    try:
        token = sanitize_string(credentials.credentials)
        user_id_str = verify_token(token)
        
        if user_id_str is None:
            logger.warning("invalid_token_in_auth")
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            user_id = int(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=401,
                detail="Invalid user identifier in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = await database_service.get_user(user_id)
        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="User account is deactivated",
            )
        
        return user
        
    except ValueError as ve:
        logger.error("token_validation_error", error=str(ve))
        raise HTTPException(
            status_code=422,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user and verify they are active.
    
    Args:
        current_user: User from get_current_user dependency
        
    Returns:
        User: The active user
        
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="User account is deactivated",
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Get current user and verify they have admin role.
    
    Args:
        current_user: User from get_current_active_user dependency
        
    Returns:
        User: The admin user
        
    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "unauthorized_admin_access_attempt",
            user_id=current_user.id,
            email=current_user.email,
        )
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required",
        )
    return current_user


def require_role(allowed_roles: list[UserRole]):
    """Dependency factory that requires specific roles.
    
    Args:
        allowed_roles: List of roles that are allowed
        
    Returns:
        Dependency function that checks user role
        
    Example:
        @router.get("/admin-or-manager")
        async def admin_endpoint(user: User = Depends(require_role([UserRole.ADMIN]))):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            logger.warning(
                "role_access_denied",
                user_id=current_user.id,
                required_roles=[r.value for r in allowed_roles],
                user_role=current_user.role.value,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of these roles: {', '.join(r.value for r in allowed_roles)}",
            )
        return current_user
    
    return role_checker


class KnowledgeBasePermissionChecker:
    """Dependency class for checking knowledge base permissions.
    
    This class creates a callable dependency that checks if the current user
    has the required permission level for a specific knowledge base.
    
    Example:
        @router.get("/kb/{kb_name}/search")
        async def search_kb(
            kb_name: str,
            user: User = Depends(KnowledgeBasePermissionChecker(PermissionLevel.READ)),
        ):
            ...
    """
    
    def __init__(
        self,
        required_level: PermissionLevel,
        kb_name_param: str = "kb_name",
        kb_name_body_field: Optional[str] = None,
    ):
        """Initialize the permission checker.
        
        Args:
            required_level: Minimum permission level required
            kb_name_param: Name of path parameter containing KB name
            kb_name_body_field: Name of body field containing KB name (for POST/PUT)
        """
        self.required_level = required_level
        self.kb_name_param = kb_name_param
        self.kb_name_body_field = kb_name_body_field
    
    async def __call__(
        self,
        request: Request,
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        """Check if user has required permission.
        
        Args:
            request: FastAPI request object
            current_user: Current authenticated user
            
        Returns:
            User: The authorized user
            
        Raises:
            HTTPException: If user lacks required permission
        """
        # Admin users have access to everything
        if current_user.role == UserRole.ADMIN:
            return current_user
        
        # Get knowledge base name from path or body
        kb_name = request.path_params.get(self.kb_name_param)
        
        if kb_name is None and self.kb_name_body_field:
            try:
                body = await request.json()
                kb_name = body.get(self.kb_name_body_field)
            except Exception:
                pass
        
        if kb_name is None:
            raise HTTPException(
                status_code=400,
                detail="Knowledge base name not provided",
            )
        
        # Check permission
        has_access, actual_level = await user_management_service.check_permission(
            user_id=current_user.id,
            knowledge_base_name=kb_name,
            required_level=self.required_level,
        )
        
        if not has_access:
            logger.warning(
                "kb_access_denied",
                user_id=current_user.id,
                knowledge_base=kb_name,
                required_level=self.required_level.value,
                actual_level=actual_level.value if actual_level else None,
            )
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions for knowledge base '{kb_name}'. "
                       f"Required: {self.required_level.value}",
            )
        
        return current_user


# Pre-configured permission checkers for common use cases
require_kb_read = KnowledgeBasePermissionChecker(PermissionLevel.READ)
require_kb_write = KnowledgeBasePermissionChecker(PermissionLevel.WRITE)
require_kb_manage = KnowledgeBasePermissionChecker(PermissionLevel.MANAGE)


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request.
    
    Handles X-Forwarded-For header for proxied requests.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client IP address string
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class AuditLogger:
    """Dependency for logging administrative actions.
    
    Example:
        @router.delete("/users/{user_id}")
        async def delete_user(
            user_id: int,
            audit: AuditLogger = Depends(AuditLogger("user_deleted")),
            admin: User = Depends(get_current_admin_user),
        ):
            # ... delete logic
            await audit.log(admin.id, "user", str(user_id), {"reason": "requested"})
    """
    
    def __init__(self, action: str):
        """Initialize audit logger with action type.
        
        Args:
            action: Type of action being logged
        """
        self.action = action
        self.request: Optional[Request] = None
    
    async def __call__(self, request: Request) -> "AuditLogger":
        """Capture request for IP extraction."""
        self.request = request
        return self
    
    async def log(
        self,
        actor_id: int,
        target_type: str,
        target_id: str,
        details: Optional[dict] = None,
    ) -> None:
        """Log an administrative action.
        
        Args:
            actor_id: ID of user performing the action
            target_type: Type of entity affected
            target_id: ID of affected entity
            details: Additional details to log
        """
        import json
        from app.core.db.user_management_service import user_management_service
        
        ip_address = get_client_ip(self.request) if self.request else None
        
        # Use internal log method
        async with user_management_service.session_maker() as session:
            from app.models.permission import AuditLog
            
            log_entry = AuditLog(
                actor_id=actor_id,
                action=self.action,
                target_type=target_type,
                target_id=target_id,
                details=json.dumps(details) if details else None,
                ip_address=ip_address,
            )
            session.add(log_entry)
            await session.commit()


# Convenience dependency for optional authentication
async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[User]:
    """Get current user if authenticated, None otherwise.
    
    Useful for endpoints that work differently for authenticated users.
    
    Args:
        credentials: Optional HTTP authorization credentials
        
    Returns:
        User if authenticated, None otherwise
    """
    if credentials is None:
        return None
    
    try:
        token = sanitize_string(credentials.credentials)
        user_id_str = verify_token(token)
        
        if user_id_str is None:
            return None
        
        user_id = int(user_id_str)
        user = await database_service.get_user(user_id)
        
        if user and user.is_active:
            return user
        return None
        
    except Exception:
        return None
