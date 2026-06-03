from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.dependencies import get_db
from backend.models.custom_agent import CustomAgent as CustomAgentModel
from backend.app.schemas import CustomAgent, CustomAgentCreate
from backend.core.orchestrator import Orchestrator
from backend.utils.logger import logger
import uuid

# 全局初始化Orchestrator实例，和你的main.py里的初始化保持一致
orchestrator = Orchestrator()

router = APIRouter()

@router.get("", response_model=list[CustomAgent])
async def list_agents(db: Session = Depends(get_db)):
    """获取所有可用的Agent（系统内置+用户创建的）"""
    # 先从数据库拿用户创建的
    db_agents = db.query(CustomAgentModel).filter(CustomAgentModel.is_active == True).all()
    # 给系统Agent补全所有CustomAgent schema要求的必填字段，和用户创建的Agent格式完全一致，避免FastAPI验证错误
    from datetime import datetime
    system_agents = [
        {
            "id": 0,  # 系统Agent的id用0占位，和用户创建的数据库自增id区分
            "agent_id": aid, 
            "name": aid, 
            "is_system": True,
            "system_prompt": "系统内置Agent",
            "llm_adapter": "system",
            "tools": [],
            "created_at": datetime.now(),  # 补全合法的datetime，解决FastAPI验证错误
            "is_active": True
        } for aid in orchestrator.agents.keys()
    ]
    return [*db_agents, *system_agents]

@router.post("", response_model=CustomAgent)
async def create_agent(req: CustomAgentCreate, db: Session = Depends(get_db)):
    """创建新的自定义Agent，表单提交过来的内容直接落库+注册到Orchestrator"""
    # 先检查是否有同名Agent
    existing = db.query(CustomAgentModel).filter(CustomAgentModel.name == req.name).first()
    if existing:
        # 同名的话自动加后缀，或者让用户改名称，这里自动处理加时间戳后缀
        from datetime import datetime
        timestamp = datetime.now().strftime("%m%d%H%M")
        final_name = f"{req.name}_{timestamp}"
    else:
        final_name = req.name
    
    # 1. 生成唯一的agent_id
    agent_id = f"custom_{final_name.replace(' ', '_').lower()}_{uuid.uuid4().hex[:6]}"
    # 2. 存入数据库
    db_agent = CustomAgentModel(
        name=final_name,
        agent_id=agent_id,
        system_prompt=req.system_prompt,
        llm_adapter=req.llm_adapter,
        tools=req.tools
    )
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    # 3. 动态注册到我们初始化的Orchestrator实例
    orchestrator.register_custom_agent(db_agent)
    logger.info(f"✅ 自定义Agent {db_agent.name} 创建成功")
    return db_agent


@router.put("/{agent_id}", response_model=CustomAgent)
async def update_agent(agent_id: str, req: CustomAgentCreate, db: Session = Depends(get_db)):
    """更新已有的自定义Agent，支持修改名称、提示词、工具集"""
    db_agent = db.query(CustomAgentModel).filter(CustomAgentModel.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent未找到")
    # 更新字段
    db_agent.name = req.name
    db_agent.system_prompt = req.system_prompt
    db_agent.llm_adapter = req.llm_adapter
    db_agent.tools = req.tools
    db.commit()
    db.refresh(db_agent)
    # 重新注册到Orchestrator，更新配置
    orchestrator.register_custom_agent(db_agent)
    logger.info(f"🔄 自定义Agent {db_agent.name} 已更新")
    return db_agent


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """删除自定义Agent，同时从Orchestrator中注销"""
    db_agent = db.query(CustomAgentModel).filter(CustomAgentModel.agent_id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent未找到")
    # 从数据库删除
    db.delete(db_agent)
    # 从Orchestrator中注销
    if agent_id in orchestrator.agents:
        del orchestrator.agents[agent_id]
    db.commit()
    logger.info(f"🗑️ 自定义Agent {db_agent.name} 已删除")
    return {"success": True, "message": "Agent已成功删除"}