import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from backend.models import *

# 极简可靠方案：所有逻辑在一个fixture中完成，彻底避免顺序问题
@pytest.fixture(scope="function")
def test_setup(monkeypatch):
    """
    终极可靠的测试环境设置：
    1. 最先运行monkeypatch，替换数据库模块的所有全局变量
    2. 创建内存数据库和所有表
    3. 创建单一数据库会话
    4. 创建app并应用依赖覆盖
    5. 返回(client, db_session)供测试使用
    """
    # ========== 第1步：导入所有需要的东西 ==========

    from backend.db.database import Base
    import backend.db.database as db_module
    from backend.app.main import create_app
    from backend.app.dependencies import get_db
    
    # ========== 第2步：创建测试数据库 ==========
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # ========== 第3步：monkey patch一切！ ==========
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    
    # ========== 第4步：创建所有表 ==========
    Base.metadata.create_all(bind=test_engine)
    print(f"\n--- [TEST-SETUP] Tables created: {list(inspect(test_engine).get_table_names())} ---\n")
    
    # ========== 第5步：创建单一数据库会话 ==========
    db = TestingSessionLocal()
    
    # ========== 第6步：创建app并覆盖依赖 ==========
    app = create_app()
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    
    # ========== 第7步：创建测试客户端 ==========
    with TestClient(app) as client:
        yield client, db
    
    # ========== 清理 ==========
    db.close()
    Base.metadata.drop_all(bind=test_engine)


# 拆分fixture以保持测试代码的兼容性
@pytest.fixture(scope="function")
def client(test_setup):
    return test_setup[0]


@pytest.fixture(scope="function")
def db_session(test_setup):
    return test_setup[1]