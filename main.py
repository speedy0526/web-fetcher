# main.py
from fastapi import FastAPI, Depends, HTTPException, Security, Path
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN
from urllib.parse import unquote
from app.Fetcher import UrlFetcher
from app.APIKey import APIKeyManager, APIPermission

# 1. 创建 FastAPI 实例
app = FastAPI()

# 定义 API Key 名称（HTTP Header 中的字段名）
API_KEY_NAME = "X-API-Key"

# 创建 API Key Header 验证器
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# 初始化 APIKeyManager
api_key_manager = APIKeyManager(salt="test-salt-123", persist_file="./apikey_store.m5")


# 验证函数
def get_api_key(api_key_header_value: str = Security(api_key_header)):
    """
    验证 API Key 是否正确
    """
    valid = api_key_manager.validate_apikey(api_key_header_value, APIPermission.READ)

    if not valid["is_valid"]:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=valid["message"],
        )


@app.get("/{url:path}")
def fetch_html(
    url: str = Path(..., description="编码后的URL链接"),
    api_key: str = Depends(get_api_key),
):
    print(f"Received request for URL: {url} with API Key: {api_key}")
    # 调用 WebFetcher 类获取网页内容
    return UrlFetcher().fetch_content(unquote(url), use_js=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
