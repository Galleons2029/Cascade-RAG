# 用户管理和权限控制系统

## 概述

本模块为 Cascade-RAG 系统提供企业级的用户管理和知识库访问权限控制功能。支持两种用户角色（普通用户和管理员），以及细粒度的知识库访问权限管理。

## 功能特性

### 1. 用户角色

| 角色 | 标识 | 权限说明 |
|------|------|----------|
| 普通用户 | `user` | 只能访问被授权的知识库，可以更新自己的个人资料 |
| 管理员 | `admin` | 拥有所有知识库的完全访问权限，可以管理用户和权限 |

### 2. 知识库权限级别

| 权限级别 | 标识 | 说明 |
|----------|------|------|
| 读取 | `read` | 可以查看和搜索知识库内容 |
| 写入 | `write` | 包含读取权限，还可以添加和更新内容 |
| 管理 | `manage` | 完全控制，包括删除和权限管理 |

权限层级：`manage` > `write` > `read`

### 3. 权限类型

- **特定知识库权限**: 针对单个知识库的访问权限
- **全局权限**: 对所有知识库的访问权限（`knowledge_base_name = null`）
- **临时权限**: 支持设置过期时间的权限

## API 端点

所有端点前缀: `/api/v1/user-management`

### 用户管理 (仅管理员)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/users` | 创建新用户 |
| GET | `/users` | 获取用户列表（分页） |
| GET | `/users/{user_id}` | 获取用户详情 |
| PATCH | `/users/{user_id}` | 更新用户信息 |
| DELETE | `/users/{user_id}` | 删除用户（软删除） |
| POST | `/users/{user_id}/reset-password` | 重置用户密码 |

### 权限管理 (仅管理员)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/permissions` | 授予权限 |
| DELETE | `/permissions` | 撤销权限 |
| GET | `/users/{user_id}/permissions` | 获取用户的所有权限 |
| GET | `/knowledge-bases/{kb_name}/permissions` | 获取知识库的所有权限 |
| POST | `/permissions/check` | 检查用户对知识库的访问权限 |
| GET | `/users/{user_id}/permission-summary` | 获取用户权限摘要 |

### 批量操作 (仅管理员)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/permissions/bulk-grant` | 批量授予权限 |
| POST | `/users/bulk-role-assign` | 批量分配角色 |

### 审计日志 (仅管理员)

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/audit-logs` | 获取审计日志（分页、过滤） |

### 自助服务 (任何已认证用户)

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/me` | 获取当前用户资料 |
| PATCH | `/me` | 更新当前用户资料 |
| GET | `/me/accessible-knowledge-bases` | 获取可访问的知识库列表 |

## 数据模型

### User 模型 (扩展)

```python
class User(BaseModel, table=True):
    id: int                           # 主键
    email: str                        # 唯一邮箱
    hashed_password: str              # 加密密码
    role: UserRole                    # 用户角色 (user/admin)
    is_active: bool                   # 账户是否激活
    display_name: Optional[str]       # 显示名称
    last_login_at: Optional[datetime] # 最后登录时间
    created_at: datetime              # 创建时间
    updated_at: datetime              # 更新时间
```

### KnowledgeBasePermission 模型

```python
class KnowledgeBasePermission(SQLModel, table=True):
    id: int                              # 主键
    user_id: int                         # 用户ID
    knowledge_base_name: Optional[str]   # 知识库名称 (null = 全局权限)
    permission_level: PermissionLevel    # 权限级别
    granted_by: Optional[int]            # 授权者ID
    granted_at: datetime                 # 授权时间
    expires_at: Optional[datetime]       # 过期时间
    is_active: bool                      # 是否激活
```

### AuditLog 模型

```python
class AuditLog(SQLModel, table=True):
    id: int                         # 主键
    actor_id: int                   # 操作者ID
    action: str                     # 操作类型
    target_type: str                # 目标类型
    target_id: str                  # 目标ID
    details: Optional[str]          # 操作详情 (JSON)
    ip_address: Optional[str]       # IP地址
    timestamp: datetime             # 时间戳
```

## 使用示例

### 1. 创建管理员用户

```python
# POST /api/v1/user-management/users
{
    "email": "admin@example.com",
    "password": "SecurePass123!",
    "role": "admin",
    "display_name": "System Admin",
    "is_active": true
}
```

### 2. 授予知识库权限

```python
# POST /api/v1/user-management/permissions
{
    "user_id": 123,
    "knowledge_base_name": "financial_docs",
    "permission_level": "write",
    "expires_at": "2026-12-31T23:59:59Z"  # 可选
}
```

### 3. 检查用户权限

```python
# POST /api/v1/user-management/permissions/check
{
    "user_id": 123,
    "knowledge_base_name": "financial_docs",
    "required_permission": "read"
}
```

### 4. 在其他 API 中使用权限检查

```python
from app.api.permissions import (
    get_current_admin_user,
    get_current_active_user,
    KnowledgeBasePermissionChecker,
    require_kb_read,
    require_kb_write,
)
from app.models.permission import PermissionLevel

# 仅管理员可访问
@router.get("/admin-only")
async def admin_endpoint(admin: User = Depends(get_current_admin_user)):
    ...

# 需要知识库读取权限
@router.get("/kb/{kb_name}/search")
async def search_kb(
    kb_name: str,
    user: User = Depends(KnowledgeBasePermissionChecker(PermissionLevel.READ)),
):
    ...

# 需要知识库写入权限
@router.post("/kb/{kb_name}/documents")
async def add_document(
    kb_name: str,
    user: User = Depends(require_kb_write),
):
    ...
```

## 安全特性

1. **密码安全**: 使用 bcrypt 加密存储密码
2. **JWT 认证**: 所有 API 需要有效的 JWT token
3. **权限层级**: 严格的权限检查机制
4. **审计日志**: 记录所有管理操作用于合规审计
5. **软删除**: 用户删除采用软删除保留数据
6. **IP 记录**: 审计日志记录操作来源 IP
7. **权限过期**: 支持设置临时权限的过期时间

## 数据库迁移

新增的数据库表会在应用启动时自动创建：

- `user` - 用户表（已扩展新字段）
- `knowledge_base_permission` - 知识库权限表
- `user_knowledge_base_access` - 用户知识库访问缓存表
- `audit_log` - 审计日志表

## 配置

无需额外配置，系统使用现有的数据库连接配置。

## 最佳实践

1. **最小权限原则**: 只授予用户完成工作所需的最小权限
2. **定期审查**: 定期检查和清理过期或不必要的权限
3. **使用临时权限**: 对于临时访问需求，设置权限过期时间
4. **监控审计日志**: 定期检查审计日志发现异常活动
5. **避免全局权限**: 尽量使用特定知识库权限而非全局权限
