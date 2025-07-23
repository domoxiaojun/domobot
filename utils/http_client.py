"""
HTTP 客户端工具模块
提供优化的 httpx 客户端实例和便捷方法
"""

import logging

import httpx


logger = logging.getLogger(__name__)

# 全局共享的 HTTP 客户端实例
_global_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """
    获取全局共享的 HTTP 客户端实例

    Returns:
        httpx.AsyncClient: 优化配置的异步 HTTP 客户端
    """
    global _global_client

    if _global_client is None:
        # 创建优化的客户端配置
        _global_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=20,  # 最大保持连接数
                max_connections=100,  # 最大总连接数
                keepalive_expiry=30.0,  # 连接保持时间（秒）
            ),
            timeout=httpx.Timeout(
                connect=10.0,  # 连接超时
                read=30.0,  # 读取超时
                write=10.0,  # 写入超时
                pool=5.0,  # 连接池获取超时
            ),
            http2=True,  # 启用 HTTP/2 支持
            follow_redirects=True,  # 自动跟随重定向
            verify=True,  # SSL 证书验证
        )
        logger.debug("创建了新的全局 HTTP 客户端实例")

    return _global_client


def create_custom_client(
    *,
    headers: dict[str, str] | None = None,
    verify: bool = True,
    follow_redirects: bool = True,
    timeout: float | None = None,
) -> httpx.AsyncClient:
    """
    创建自定义配置的 HTTP 客户端

    Args:
        headers: 自定义请求头
        verify: 是否验证 SSL 证书
        follow_redirects: 是否自动跟随重定向
        timeout: 超时时间（秒）

    Returns:
        httpx.AsyncClient: 自定义配置的异步 HTTP 客户端
    """
    # 使用基础优化配置
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100, keepalive_expiry=30.0)

    # 自定义超时配置
    if timeout:
        timeout_config = httpx.Timeout(timeout)
    else:
        timeout_config = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)

    return httpx.AsyncClient(
        headers=headers,
        limits=limits,
        timeout=timeout_config,
        http2=True,
        follow_redirects=follow_redirects,
        verify=verify,
    )


async def close_global_client():
    """
    关闭全局 HTTP 客户端连接
    """
    global _global_client

    if _global_client:
        await _global_client.aclose()
        _global_client = None
        logger.debug("已关闭全局 HTTP 客户端实例")


# 便捷方法
async def get(url: str, **kwargs) -> httpx.Response:
    """GET 请求便捷方法"""
    client = get_http_client()
    return await client.get(url, **kwargs)


async def post(url: str, **kwargs) -> httpx.Response:
    """POST 请求便捷方法"""
    client = get_http_client()
    return await client.post(url, **kwargs)


async def put(url: str, **kwargs) -> httpx.Response:
    """PUT 请求便捷方法"""
    client = get_http_client()
    return await client.put(url, **kwargs)


async def delete(url: str, **kwargs) -> httpx.Response:
    """DELETE 请求便捷方法"""
    client = get_http_client()
    return await client.delete(url, **kwargs)
