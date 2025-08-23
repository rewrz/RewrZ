"""
调试版本的主应用 - 用于排查Internal Server Error
"""
import traceback
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import sys

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 创建简单的测试应用
debug_app = FastAPI(title="RewrZ Debug App")

@debug_app.middleware("http")
async def debug_middleware(request: Request, call_next):
    try:
        logger.info(f"接收请求: {request.method} {request.url}")
        response = await call_next(request)
        logger.info(f"响应状态: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"中间件异常: {str(e)}")
        logger.error(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)}
        )

@debug_app.get("/")
async def debug_root():
    logger.info("访问根路径")
    return {"message": "Debug app is working"}

@debug_app.get("/test-db")
async def test_database():
    try:
        from rewrz.core.database import get_db
        from sqlalchemy import text
        
        db = next(get_db())
        result = db.execute(text('SELECT 1'))
        db.close()
        return {"database": "OK"}
    except Exception as e:
        logger.error(f"数据库测试失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@debug_app.get("/test-main")
async def test_main_import():
    try:
        from rewrz.main import app
        return {"main_app": "OK", "routes": len(app.routes)}
    except Exception as e:
        logger.error(f"主应用导入失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(debug_app, host="0.0.0.0", port=8001, log_level="debug")