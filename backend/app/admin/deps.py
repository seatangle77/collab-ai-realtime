import os

from fastapi import Header, HTTPException, status


# 默认开发环境的后台密钥；如果设置了 ADMIN_API_KEY 环境变量，则以环境变量为准。
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "TestAdminKey123")


def require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> bool:
    """
    简单的后台接口保护：
    - 默认使用固定值 TestAdminKey123，方便本地开发与测试；
    - 如需更安全，可在部署环境中配置 ADMIN_API_KEY 覆盖默认值；
    - 调用 /api/admin/** 时，HTTP 头中必须携带 X-Admin-Token 与之完全一致。
    """
    if x_admin_token != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问后台接口",
        )

    return True


