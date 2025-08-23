"""
媒体设置初始化脚本

用于初始化默认的媒体配置到数据库中
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rewrz.core.database import get_db
from rewrz.core.media_config import init_media_settings

def main():
    """初始化媒体设置"""
    print("正在初始化媒体设置...")
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        # 初始化媒体设置
        init_media_settings(db)
        print("媒体设置初始化完成！")
    except Exception as e:
        print(f"初始化失败: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()