import pytest
from sqlalchemy.orm import Session
from backend.models.conversation import Conversation

def test_db_fixture_directly(db_session: Session):
    """
    这个测试完全绕过 TestClient 和 FastAPI。
    它只从 conftest.py 获取一个 db_session，并直接尝试使用它。
    这将告诉我们数据库 fixture 本身是否健康。
    """
    print("\\n--- [Starting test_db_fixture_directly] ---")

    # 1. 创建一个 Conversation 对象
    new_conv = Conversation(title="A direct DB test")
    print(f"--- Created Conversation object: {new_conv}")

    # 2. 添加并提交到数据库
    try:
        db_session.add(new_conv)
        db_session.commit()
        print("--- Commit successful ---")
    except Exception as e:
        print(f"--- !!! COMMIT FAILED: {e} !!! ---")
        pytest.fail(f"Database commit failed: {e}")

    # 3. 从数据库中查询刚刚创建的对象
    retrieved_conv = db_session.query(Conversation).filter_by(title="A direct DB test").first()
    print(f"--- Retrieved Conversation object: {retrieved_conv}")

    assert retrieved_conv is not None
    assert retrieved_conv.title == "A direct DB test"
    print("--- [Test finished successfully] ---")