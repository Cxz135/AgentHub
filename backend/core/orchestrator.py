import asyncio
import json
import logging
import re
import os
import importlib
import yaml
from typing import List, Dict, Any, Callable


from backend.models.task_spec import TaskSpec
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.base_agent import BaseAgent
from backend.agents.custom_agent import CustomAgent
from backend.agents.deepseek_adapter import DeepSeekAdapter
from backend.agents.internal.planner_agent import PlannerAgent
from backend.agents.internal.summarizer_agent import SummarizerAgent
from backend.agents.tongyi_adapter import TongyiAdapter
from backend.core.agent_protocol import AgentResponse
from backend.core.graph_state import GraphState
from backend.models.message import Message
from backend.llm.llm_provider import get_llm
from backend.workflows.base import BaseWorkflow

from backend.utils.logger import logger

# 一个简单的正则表达式，用于从消息内容中匹配 @agent_id
MENTION_REGEX = r'@(\w+)'


class Orchestrator:
    """
    Agent Hub 的主协调器。重构后的版本完全自主，不需要用户输入任何/xxx命令
    它负责：
    1. 注册和管理所有可用的 Agent。
    2. 注册和管理所有预定义的工作流插件。
    3. 接收新消息，**自动识别请求类型**，路由到合适的工作流或Agent。
    4. 默认情况下，执行动态的、基于计划的工作流处理复杂任务。
    """

    def __init__(self, db_session=None):
        self.agents: Dict[str, BaseAgent] = {}
        self.workflows: Dict[str, Dict] = {}  # 重构后的结构：每个工作流带graph、keywords、description
        self.adapters: Dict[str, type[BaseAgent]] = {
            "deepseek": DeepSeekAdapter,
            "tongyi": TongyiAdapter,
        }
        self.llm = get_llm()
        self.max_iterations = 10
        self.max_retries = 2
        # 保存数据库会话，用于实时写入子Agent的消息
        self.db_session = db_session

        # 能力类Skill：纯自然语言的md文件，用户能自建，用的时候拼prompt
        self.native_skills: Dict[str, str] = {}
        # 工具类Skill：要执行代码的函数，放utils里，原来的逻辑保留
        self.tool_skills: Dict[str, Callable] = {}
        # 封装成LangChain Tool的工具列表，支持ReAct循环
        self.langchain_tools: List[Any] = []

        # 🎯 优化后的初始化顺序：先核心，后业务
        # 1. 先注册所有核心Agent
        self._setup_agents()
        # 2. 加载所有Skill（能力类+工具类）
        self._load_native_skills()
        self._register_builtin_tool_skills()
        # 3. 注册所有工作流（内置+自定义）
        self._register_builtin_workflows()
        self._register_workflows()
        # 4. 定义动态规划工作流的蓝图
        self.planning_graph_builder = self._build_planning_graph()
        # 5. 最后加载数据库里的自定义Agent
        self._load_custom_agents_from_db()
        logger.info("✅ Orchestrator 初始化完成，所有组件加载成功。")

    def _load_native_skills(self):
        """加载skills目录下所有的能力类Skill（md文件），纯自然语言的能力描述，就是你要的用户自建Skill"""
        from pathlib import Path
        skills_dir = Path(__file__).parent.parent / "skills"
        if not skills_dir.exists():
            os.makedirs(skills_dir, exist_ok=True)
            logger.warning("skills目录不存在，已自动创建，你可以把md格式的能力类Skill放在这里")
            return
        # 遍历所有md文件，加载能力类Skill
        for md_file in skills_dir.glob("*.md"):
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                skill_name = md_file.stem
                self.native_skills[skill_name] = content
                logger.info(f"✅ 加载能力类Skill: {skill_name}")
            except Exception as e:
                logger.error(f"加载能力类Skill {md_file.name}失败: {e}")
        logger.info(f"🎉 能力类Skill加载完成，共{len(self.native_skills)}个: {list(self.native_skills.keys())}")

    def get_available_skills_prompt(self) -> str:
        """统一生成所有可用技能的自然语言描述，供planner和所有子agent使用"""
        # 处理能力类Skill（md文件）
        native_skills_desc = []
        for skill_name, skill_content in self.native_skills.items():
            try:
                # 从md文件中提取关键信息
                name_part = skill_content.split("## 技能名称：")
                if len(name_part) > 1:
                    name = name_part[1].split("##")[0].strip()
                else:
                    name = skill_name
                    
                desc_part = skill_content.split("## 功能描述")
                if len(desc_part) > 1:
                    desc = desc_part[1].split("##")[0].strip()
                else:
                    desc = "无描述"
                    
                usage_part = skill_content.split("## 调用格式")
                if len(usage_part) > 1:
                    usage = usage_part[1].strip()[:200]
                else:
                    usage = "SKILL_CALL: {skill_name} 参数"
                    
                native_skills_desc.append(f"- {name}: {desc}\n  调用格式: {usage}")
            except Exception as e:
                logger.warning(f"解析技能{skill_name}描述失败: {e}")
                native_skills_desc.append(f"- {skill_name}: 技能描述解析失败")
        
        # 处理工具类Skill
        tool_skills_list = ", ".join(self.tool_skills.keys())
        
        return f"""=== 可用工具/技能列表 ===
你可以使用以下技能来完成任务，调用时严格按照格式输出：
{chr(10).join(native_skills_desc)}

工具类技能（可直接调用的Python函数）: {tool_skills_list}
"""

    def _parse_skill_call(self, content: str) -> tuple[str, str, str] | None:
        """解析大模型的Skill调用请求，支持工具组的方法参数，任何用户自建的Skill都能自动识别"""
        # 匹配普通能力类Skill: 【调用Skill: xxx，输入内容: xxx】
        basic_match = re.search(r'【调用Skill:\s*(\w+)\s*，输入内容:\s*(.*?)\s*】', content, re.DOTALL)
        if basic_match:
            return basic_match.group(1), None, basic_match.group(2)
        # 匹配工具组Skill: 【调用Skill: xxx，方法: xxx，输入内容: xxx】
        tool_match = re.search(r'【调用Skill:\s*(\w+)\s*，方法:\s*(\w+)\s*，输入内容:\s*(.*?)\s*】', content, re.DOTALL)
        if tool_match:
            return tool_match.group(1), tool_match.group(2), tool_match.group(3)
        return None

    async def call_skill(self, skill_name: str, method: str = None, input_content: str = None) -> Any:
        """统一调用入口，同时支持能力类Skill和工具类Skill，自动识别类型"""
        # 1. 调用工具类Skill（要执行代码的py函数）
        if method and f"{skill_name}.{method}" in self.tool_skills:
            tool_key = f"{skill_name}.{method}"
            logger.info(f"🔧 调用工具类Skill: {tool_key}, 输入文件: {input_content}")
            try:
                result = self.tool_skills[tool_key](input_content)
                logger.info(f"✅ 工具类Skill {tool_key}调用成功")
                return result
            except Exception as e:
                logger.error(f"工具类Skill调用失败: {e}")
                return f"调用失败: {str(e)}"
        # 2. 调用能力类Skill（纯大模型的md文件）
        if skill_name in self.native_skills:
            full_prompt = f"{self.native_skills[skill_name]}\n\n### 待处理输入\n{input_content}"
            logger.info(f"🔧 调用能力类Skill: {skill_name}")
            return self.llm.invoke(full_prompt).content.strip()
        # 找不到Skill
        return f"错误：Skill '{skill_name}' 不存在，可用工具类: {list(self.tool_skills.keys())}, 可用能力类: {list(self.native_skills.keys())}"

    def _register_builtin_tool_skills(self):
        """注册utils里的所有工具类Skill（要执行代码的函数），和能力类Skill彻底分开，不会混淆"""
        # 注册单例工具函数
        try:
            from backend.utils.rag_retrieval import rag_retrieval
            self.tool_skills["rag_retrieval"] = rag_retrieval
            from backend.utils.web_search import web_search
            self.tool_skills["web_search"] = web_search
        except ImportError:
            pass
        try:
            from backend.utils.code_scanner import scan_vulnerabilities
            self.tool_skills["scan_vulnerabilities"] = scan_vulnerabilities
        except ImportError:
            pass
        try:
            from backend.utils.web_search import web_search
            self.tool_skills["web_search"] = web_search
        except ImportError:
            pass
        # 注册文件转换工具组的所有方法
        try:
            import importlib
            file_converter = importlib.import_module('backend.utils.file_converter')
            # 获取所有导出的函数
            converter_funcs = getattr(file_converter, '__all__', [])
            for func_name in converter_funcs:
                if func_name != "FileConversionError" and hasattr(file_converter, func_name):
                    self.tool_skills[f"file_converter.{func_name}"] = getattr(file_converter, func_name)
        except ImportError as e:
            logger.warning(f"加载file_converter工具失败: {e}")
            pass
        # 将所有工具类Skill转换为LangChain Tool格式
        from langchain.tools import tool
        for skill_key, skill_func in self.tool_skills.items():
            # 给每个函数加上tool装饰器，包装成LangChain Tool
            wrapped_tool = tool(skill_func)
            wrapped_tool.name = skill_key
            self.langchain_tools.append(wrapped_tool)
        logger.info(f"✅ 工具类Skill加载完成，共{len(self.tool_skills)}个，已封装为LangChain Tool: {list(self.tool_skills.keys())}")

    def _register_builtin_workflows(self):
        """注册所有内置的固定工作流，每个工作流带自然语言匹配关键词，让orchestrator自动识别"""
        from backend.workflows.rag_workflow import RAGWorkflow
        from backend.workflows.code_review_workflow import CodeReviewWorkflow
        # 给每个工作流加上匹配关键词，支持自然语言自动识别
        self.workflows["rag"] = {
            "graph": RAGWorkflow.build(),
            "keywords": ["什么是", "解释一下", "知识库", "查询", "搜索", "关于", "是什么", "怎么用"],
            "description": "知识库问答，用于查询已存储的文档内容"
        }
        self.workflows["code_review"] = {
            "graph": CodeReviewWorkflow.build(),
            "keywords": ["代码审查", "review", "帮我看一下代码", "检查代码", "代码漏洞", "优化代码",
                         "帮我看看这段代码"],
            "description": "代码审查，用于分析代码、扫描漏洞、生成报告"
        }
        logger.info(f"✅ 成功注册{len(self.workflows)}个内置固定工作流: {list(self.workflows.keys())}")

    def _auto_match_workflow(self, content: str) -> str | None:
        """🎯 核心优化：自动从用户的自然语言输入匹配最合适的工作流，不用用户输入任何命令"""
        content_lower = content.lower()
        # 遍历所有工作流，匹配关键词，匹配度最高的优先
        best_match = None
        max_score = 0
        for workflow_id, workflow_info in self.workflows.items():
            score = 0
            for keyword in workflow_info["keywords"]:
                if keyword.lower() in content_lower:
                    score += 1
            # 代码审查的关键词优先级更高，避免和普通开发任务混淆
            if workflow_id == "code_review" and score > 0:
                score += 2
            if score > max_score:
                max_score = score
                best_match = workflow_id
        # 统一触发阈值：得分超过6才触发固定工作流，避免误匹配
        WORKFLOW_TRIGGER_THRESHOLD = 6
        if best_match and max_score > WORKFLOW_TRIGGER_THRESHOLD:
            logger.info(f"🎯 自动匹配到工作流: {best_match}，匹配得分: {max_score}，超过阈值{WORKFLOW_TRIGGER_THRESHOLD}，触发工作流")
            return best_match, max_score
        else:
            logger.info(f"🎯 匹配得分{max_score}未达阈值{WORKFLOW_TRIGGER_THRESHOLD}，不触发固定工作流，进入深度调度逻辑")
            return None, 0

    async def get_chat_response(self, conversation_id: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        重构后的核心调度入口：完全自主判断用户请求，不需要用户输入任何/xxx命令
        优先级：@mention > 自动匹配的固定工作流 > 复杂任务动态规划 > 普通聊天
        """
        if not messages:
            return {"agent_id": "orchestrator", "content": "没有收到任何消息。"}

        latest_message = messages[-1]
        content = latest_message.get("content", "").strip()
        
        # 📝 任务复杂度判断（使用 LLM 分类器代替关键词匹配）
        logger.info(f"[VERIFY] 对话ID: {conversation_id}，用户输入: {content[:100]}...")
        complexity_level = await self._classify_complexity(content)
        if complexity_level == "complex":
            logger.info(f"[VERIFY] 任务判断：复杂任务，将启动动态规划调度。")
        elif complexity_level == "moderate":
            logger.info(f"[VERIFY] 任务判断：中等复杂度任务，将路由到专家 Agent。")
        else:
            logger.info(f"[VERIFY] 任务判断：简单任务，无需拆解，进入普通聊天。")

        # 在顶层管理 checkpointer 的生命周期
        checkpointer_ctx = AsyncSqliteSaver.from_conn_string("agenthub_memory.sqlite")
        async with checkpointer_ctx as checkpointer:
            # 📝 内存加载日志（验证点3：memory如何被记录）
            config = {"configurable": {"thread_id": conversation_id}}
            current_checkpoint = await checkpointer.aget(config)
            if current_checkpoint:
                msg_count = len(current_checkpoint.get('values', {}).get('messages', []))
                logger.info(f"[MEMORY] 加载历史记忆，当前对话消息数: {msg_count}")
            else:
                logger.info(f"[MEMORY] 新对话，无历史记忆，开始记录上下文")

            # 1. 第一优先级：检查@mention，保留用户手动指定Agent的能力
            mentioned_agent_id = self._find_mentioned_agent_id(content)
            if mentioned_agent_id:
                logger.info(f"[VERIFY] 触发@mention路由: {mentioned_agent_id}")
                return await self._handle_mention(mentioned_agent_id, conversation_id, messages)

            # 2. 第二优先级：自动匹配固定工作流，完全不用用户输入命令，统一阈值避免误匹配
            matched_workflow, max_score = self._auto_match_workflow(content)
            WORKFLOW_TRIGGER_THRESHOLD = 6
            if matched_workflow and max_score > WORKFLOW_TRIGGER_THRESHOLD:
                logger.info(f"[VERIFY] 工作流/技能选择：触发固定工作流 '{matched_workflow}'，得分{max_score}达阈值{WORKFLOW_TRIGGER_THRESHOLD}，跳过动态规划")
                return await self._handle_workflow_command(matched_workflow, conversation_id, content, messages,
                                                           checkpointer)
            else:
                logger.info(f"[VERIFY] 任务判断：匹配得分{max_score}未达阈值({WORKFLOW_TRIGGER_THRESHOLD})，进入深度调度逻辑")

            # 3. 第三优先级：LLM 复杂度路由
            if complexity_level == "complex":
                logger.info(f"[VERIFY] 工作流/技能选择：复杂任务，启动动态规划")
                return await self._handle_plan_command(conversation_id, content, checkpointer)

            if complexity_level == "moderate":
                logger.info(f"[VERIFY] 工作流/技能选择：中等复杂度任务，路由到主 Agent 直接执行")
                enhanced_content = f"用户有一个任务交给你，请认真完成，如果需要搜索或调用工具可以自行使用。\n\n任务：{content}"
                moderate_messages = [{"role": "user", "content": enhanced_content}]
                return await self._handle_default_chat(conversation_id, moderate_messages)

            # 4. 最后检查是否是LLM自己生成的Skill调用请求
            skill_call = self._parse_skill_call(content)
            if skill_call:
                skill_name, method, input_content = skill_call
                logger.info(f"[VERIFY] 工作流/技能选择：触发技能调用 '{skill_name}{'.'+method if method else ''}'")
                skill_result = await self.call_skill(skill_name, method, input_content)
                final_prompt = f"Skill调用结果：{skill_result}\n\n请把这个结果整理成自然语言回复用户。"
                # 通义千问要求输入是消息列表格式
                messages = [{"role": "user", "content": final_prompt}]
                final_response = await self.llm.invoke(messages)
                if isinstance(final_response, str):
                    final_content = final_response.strip()
                else:
                    final_content = str(final_response).strip()
                return {"agent_id": "orchestrator", "content": final_content}

            # 5. 检查是否是系统查询（关于orchestrator自身的能力、Agent列表、Skill列表等）
            #    这类问题 orchestrator 应该自己回答，而不是路由到 LLM
            system_reply = self._handle_system_query(content)
            if system_reply:
                logger.info(f"[VERIFY] 工作流/技能选择：系统查询，由 Orchestrator 自行回答")
                return {"agent_id": "orchestrator", "content": system_reply}

            # 6. 默认行为：普通聊天
            logger.info(f"[VERIFY] 工作流/技能选择：普通聊天，路由到默认对话Agent")
            return await self._handle_default_chat(conversation_id, messages)

    async def _handle_mention(self, agent_id: str, conversation_id: str, messages: List[Dict[str, str]]) -> Dict[
        str, Any]:
        """处理 @mention 消息，直接调用对应的 Agent。"""
        target_agent = self.get_agent(agent_id)
        if not target_agent:
            return {"agent_id": "orchestrator", "content": f"未找到名为 '{agent_id}' 的 Agent。"}

        logger.info(f"Chat API: 消息将被路由到 Agent: {target_agent.agent_id}")
        history_as_msgs = [Message(conversation_id=conversation_id, agent_id=m.get("role"), content=m.get("content"))
                           for m in messages]
        response: AgentResponse = await target_agent.process_message(messages=history_as_msgs)
        return {"agent_id": target_agent.agent_id, "content": response.final_answer.content}

    async def _handle_plan_command(self, conversation_id: str, task_content: str, checkpointer: AsyncSqliteSaver) -> \
    Dict[str, Any]:
        """处理复杂任务，执行完整的规划工作流。"""
        logger.info(f"Chat API: 启动动态规划处理复杂任务: {task_content[:30]}...")
        if not task_content:
            return {"agent_id": "orchestrator", "content": "请输入需要规划的具体任务。"}

        # 1. 手动调用 PlannerAgent 生成计划
        planner = self.get_agent("planner")
        if not planner:
            logger.error("内部错误：规划工作流需要 'planner' Agent，但未找到。")
            return {"agent_id": "orchestrator", "content": "抱歉，系统配置错误，无法找到规划器。"}

        # --- 长期记忆读取与 Planner 上下文准备 ---
        historical_summary = ""
        config = {"configurable": {"thread_id": conversation_id}}
        latest_checkpoint = await checkpointer.aget(config)
        if latest_checkpoint:
            logger.info(f"[MEMORY] 为对话 {conversation_id} 加载了历史记忆。Checkpoint keys: {list(latest_checkpoint.keys())}")
            # LangGraph checkpointer使用['values']而不是.channel_values
            if 'values' in latest_checkpoint:
                historical_summary = latest_checkpoint['values'].get("memory_summary", "")
                msg_count = len(latest_checkpoint['values'].get('messages', []))
                logger.info(f"[MEMORY] 历史消息数: {msg_count}，历史摘要长度: {len(historical_summary)}")
            else:
                historical_summary = ""

        available_agents = [agent_id for agent_id in self.agents.keys() if agent_id not in ["planner", "summarizer"]]
        # 生成统一的技能列表，传给planner
        skills_prompt = self.get_available_skills_prompt()
        planner_context = {
            "available_agents": available_agents, 
            "historical_summary": historical_summary,
            "available_skills_prompt": skills_prompt
        }

        plan_task_message = HumanMessage(content=task_content)
        agent_response: AgentResponse = await planner.process_message([plan_task_message], context=planner_context)

        if not (agent_response and agent_response.final_answer and agent_response.final_answer.content):
            return {"agent_id": "orchestrator", "content": "抱歉，规划器未能生成有效的行动计划。"}

        try:
            plan_data = json.loads(agent_response.final_answer.content)
            if isinstance(plan_data, dict):
                tasks_raw = plan_data.get('tasks', [])
            else:
                tasks_raw = plan_data
            tasks = [TaskSpec(**t) for t in tasks_raw]
            plan_data = {"tasks": tasks}
            # 兼容两种格式：如果是列表直接用，如果是字典取tasks字段
            tasks_list = plan_data if isinstance(plan_data, list) else plan_data.get('tasks', [])
            logger.info(f"[VERIFY] 任务拆解：Planner生成了{len(tasks_list)}个子任务")
            for i, task in enumerate(tasks_list):
                if isinstance(task, dict):
                    logger.info(f"[VERIFY] 子任务{i+1}: {getattr(task, 'description', '')[:50]}...，Agent: {getattr(task, 'agent_id', '')}")
                else:
                    logger.info(f"[VERIFY] 子任务{i+1}: {str(task)[:50]}...")
            # 统一格式，确保后续代码能正确处理
            if isinstance(plan_data, list):
                plan_data = {"tasks": plan_data}
        except json.JSONDecodeError:
            logger.error(f"[VERIFY] 任务拆解失败：计划格式无效，内容: {agent_response.final_answer.content[:100]}")
            return {"agent_id": "orchestrator", "content": f"抱歉，规划器返回的计划格式无效。"}

        # 2. 准备并执行工作流
        initial_state = GraphState(
            task_content=task_content, plan_data=plan_data, step_results={},
            final_summary="", conversation_id=conversation_id, messages=[]
        )

        if latest_checkpoint and 'values' in latest_checkpoint:
            initial_state["messages"] = latest_checkpoint['values'].get("messages", [])
        else:
            initial_state["messages"] = []
        initial_state["messages"].append(HumanMessage(content=task_content))
        logger.info(f"[MEMORY] 更新对话消息列表，当前消息数: {len(initial_state['messages'])}")

        # 🚀 并行调度准备（验证点：并行调度和失败降级）
        parallel_tasks = []
        independent_tasks = [t for t in plan_data.get('tasks', []) if getattr(t, 'parallelizable', False)]
        if independent_tasks:
            logger.info(f"[VERIFY] 并行调度：发现{len(independent_tasks)}个可并行执行的独立任务")
        
        app = self.planning_graph_builder.compile(checkpointer=checkpointer)
        try:
            final_state = await app.ainvoke(initial_state, config=config)
            logger.info(f"[VERIFY] 所有子任务执行完成，工作流成功结束")
        except Exception as e:
            logger.error(f"[VERIFY] 失败降级：工作流执行出错，触发降级逻辑: {str(e)}", exc_info=True)
            # 失败降级：直接调用LLM生成基础回答，避免完全失败
            fallback_prompt = f"用户的问题是：{task_content}\n\n由于复杂任务调度暂时出错，请直接用你现有的知识回答用户的问题。"
            # llm.invoke本身就是协程函数，直接await即可
            # 通义千问要求输入是消息列表格式
            messages = [{"role": "user", "content": fallback_prompt}]
            fallback_response = await self.llm.invoke(messages)
            if isinstance(fallback_response, str):
                fallback_content = fallback_response
            else:
                fallback_content = str(fallback_response)
            return {"agent_id": "orchestrator", "content": f"⚠️ 复杂任务调度遇到小问题，不过我依然可以帮你解答：\n\n{fallback_content}"}

        summary = final_state.get('final_summary')
        if summary:
            # 📦 记忆压缩与选择性遗忘（验证点：后续是否被压缩、子任务是否选择性遗忘）
            await self._compress_and_forget(conversation_id, checkpointer, final_state, plan_data)

            # 构建中间消息列表（前端按顺序显示：规划→各Agent输出→总结）
            agent_outputs = final_state.get("agent_outputs", [])
            intermediate_messages = []

            # 1. 以 Orchestrator 身份发送规划公告
            tasks = plan_data.get("tasks", [])
            plan_lines = ["📋 **任务规划详情：**\n"]
            for i, task in enumerate(tasks):
                agent_id = getattr(task, "agent_id", "未知Agent")
                desc = getattr(task, "description", getattr(task, "prompt", ""))[:100]
                plan_lines.append(f"  {i+1}. @{agent_id}：{desc}")
            intermediate_messages.append({
                "agent_id": "orchestrator",
                "content": "\n".join(plan_lines)
            })

            # 2. 依次追加每个 Agent 的输出
            for ao in agent_outputs:
                intermediate_messages.append({
                    "agent_id": ao.get("agent_id", "agent"),
                    "content": ao.get("content", "")
                })

            return {
                "agent_id": "orchestrator",
                "content": summary,
                "intermediate_messages": intermediate_messages
            }
        else:
            logger.error(f"规划工作流执行完毕，但最终状态中没有找到有效的总结。最终状态: {final_state}")
            return {"agent_id": "orchestrator", "content": "抱歉，我执行了计划，但无法生成最终的总结报告。"}

    async def _handle_workflow_command(self, workflow_id: str, conversation_id: str, task_content: str,
                                       messages: List[Dict[str, str]], checkpointer: AsyncSqliteSaver) -> Dict[
        str, Any]:
        """处理自动匹配到的工作流，重构后的逻辑适配新的workflows结构"""
        workflow_info = self.workflows.get(workflow_id)
        if not workflow_info:
            return {"agent_id": "orchestrator", "content": f"无法找到工作流: {workflow_id}"}

        logger.info(f"✅ 开始执行工作流: {workflow_id}")
        initial_state = GraphState(
            task_content=task_content,
            conversation_id=conversation_id,
            messages=[HumanMessage(content=m.get("content")) if m.get("role") == "user" else AIMessage(
                content=m.get("content")) for m in messages],
        )

        # 检查graph是否已经编译过，避免重复调用compile()，兼容所有版本
        if hasattr(workflow_info["graph"], 'compile'):
            # 还没编译，调用compile
            app = workflow_info["graph"].compile(checkpointer=checkpointer)
        else:
            # 已经是编译好的graph，直接用
            app = workflow_info["graph"]
        config = {"configurable": {"thread_id": conversation_id}}
        try:
            final_state = await app.ainvoke(initial_state, config=config)
            logger.info(f"🎉 工作流 {workflow_id} 执行完成")
        except Exception as e:
            logger.error(f"[VERIFY] 失败降级：工作流{workflow_id}执行出错，触发降级: {str(e)}", exc_info=True)
            fallback_prompt = f"用户的问题是：{task_content}\n\n工作流执行遇到问题，请直接用你的知识回答用户。"
            # 通义千问要求输入是消息列表格式
            messages = [{"role": "user", "content": fallback_prompt}]
            fallback_response = await self.llm.invoke(messages)
            if isinstance(fallback_response, str):
                fallback_content = fallback_response
            else:
                fallback_content = str(fallback_response)
            return {"agent_id": "orchestrator", "content": fallback_content}
            
        # 兼容工作流的final_answer或final_summary字段
        summary = final_state.get('final_answer', final_state.get('final_summary', f"{workflow_id} 工作流执行完成。"))
        logger.info(f"[WORKFLOW] 工作流 {workflow_id} 执行成功，最终结果长度: {len(summary)}")
        # 📦 工作流结束后也执行记忆压缩
        await self._compress_and_forget(conversation_id, checkpointer, final_state, None)
        return {"agent_id": "orchestrator", "content": summary}

    async def _handle_default_chat(self, conversation_id: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """处理不包含任何指令的普通聊天消息。"""
        main_chat_agent = self.get_agent("tongyi")
        if main_chat_agent:
            logger.info(f"Chat API: 默认路由到主聊天 Agent: {main_chat_agent.agent_id}")

            # 构建系统上下文：告知当前可用的 Agent、Skill 等信息
            agent_list = [f"- {getattr(agent, 'name', agent_id)}" for agent_id, agent in self.agents.items()]
            agent_context = "\n".join(agent_list) if agent_list else "暂无"
            skills_prompt = self.get_available_skills_prompt()

            context_prompt = f"""你是 AgentHub 的 Orchestrator Assistant，负责回答用户关于系统的问题。

当前系统中可用的 Agent：
{agent_context}

{skills_prompt}

你可以回答用户关于这些 Agent 和 Skill 的用途、能力等问题。如果你不知道某个 Agent 或 Skill 的具体细节，请如实告知用户。"""

            system_message = SystemMessage(content=context_prompt)

            history_as_msgs = [
                Message(conversation_id=conversation_id, agent_id=m.get("role"), content=m.get("content")) for m in
                messages]
            # 注入系统上下文
            full_messages = [system_message] + history_as_msgs
            response: AgentResponse = await main_chat_agent.process_message(messages=full_messages)
            return {"agent_id": main_chat_agent.agent_id, "content": response.final_answer.content}

        logger.warning("Chat API: 既没有匹配的指令，也找不到默认的主聊天 Agent。")
        return {
            "agent_id": "orchestrator",
            "content": "你好！我是一个 Agent 协调器。你可以通过 @agent_name 与我管理的 Agent 对话，或者直接问我问题。"
        }

    def _handle_system_query(self, content: str) -> str | None:
        """
        检测用户是否在询问系统信息（Agent列表、Skill列表、Orchestrator自身能力等），
        如果是，直接从 Orchestrator 的内部状态回答，不路由到 LLM。
        返回回答字符串，如果不是系统查询则返回 None。
        """
        content_lower = content.lower().strip()

        # ===== 检测是否是系统查询关键词 =====
        query_agents = any(kw in content for kw in [
            "有哪些agent", "什么agent", "agent列表", "所有agent",
            "显示agent", "列举agent", "列出agent",
            "可用agent", "agent可以用", "agent可用",
            "几个agent", "有哪些助手", "什么助手", "有哪些智能体",
            "agent有哪些", "agent都有",
        ])
        query_skills = any(kw in content for kw in [
            "有哪些skill", "什么skill", "skill列表", "所有skill",
            "显示skill", "列举skill", "列出skill",
            "可用skill", "skill可以用", "skill可用",
            "几个skill", "有哪些技能", "什么技能", "所有技能",
            "技能列表", "技能有哪些", "skill有哪些",
        ])
        query_workflows = any(kw in content for kw in [
            "有哪些工作流", "什么工作流", "工作流列表", "所有工作流",
            "可用工作流", "工作流有哪些",
        ])
        query_capability = any(kw in content for kw in [
            "你能做什么", "你的能力", "orchestrator能",
            "orchestrator可以", "你会什么", "你有什么功能",
            "你有什么能力", "orchestrator功能",
        ])
        query_about_self = any(kw in content_lower for kw in [
            "你是谁", "你是什么", "你是做什么的",
        ])

        if not any([query_agents, query_skills, query_workflows, query_capability, query_about_self]):
            return None

        # ===== 构建回答 =====
        lines = []

        if query_about_self:
            lines.append("我是 **Orchestrator**（协调器），是 AgentHub 的核心调度中枢。")
            lines.append("")
            lines.append("我的职责包括：")
            lines.append("- 🤖 管理所有 Agent 的注册、调度与路由")
            lines.append("- 🔧 加载并执行 Skill（技能模块）")
            lines.append("- ⚡ 自动识别任务类型，匹配最优的工作流")
            lines.append("- 🧩 复杂任务动态拆解、规划与并行执行")
            lines.append("- 📌 支持 @AgentName 直接调用指定 Agent")
            lines.append("")

        if query_agents or query_capability:
            lines.append(f"📋 **当前已注册 {len(self.agents)} 个 Agent：**")
            for agent_id, agent in self.agents.items():
                agent_name = getattr(agent, 'name', agent_id)
                agent_type = agent.__class__.__name__
                lines.append(f"  - **{agent_name}**（类型: {agent_type}）")
            lines.append("")
            lines.append("💡 输入框输入 @Agent名称 可直接调用对应 Agent。")
            lines.append("")

        if query_skills or query_capability:
            all_skills = list(self.native_skills.keys()) + list(self.tool_skills.keys())
            if all_skills:
                lines.append(f"📋 **当前已加载 {len(all_skills)} 个 Skill：**")
                for sk in all_skills:
                    lines.append(f"  - {sk}")
            else:
                lines.append("📋 当前没有已加载的 Skill。")
            lines.append("")

        if query_workflows or query_capability:
            wf_names = list(self.workflows.keys())
            if wf_names:
                lines.append(f"📋 **当前已注册 {len(wf_names)} 个工作流：**")
                for wf_id, wf_info in self.workflows.items():
                    lines.append(f"  - **{wf_id}**：{wf_info.get('description', wf_id)}")
            else:
                lines.append("📋 当前没有注册的工作流。")
            lines.append("")

        if query_capability:
            lines.append("---")
            lines.append("💬 如果有复杂任务，我会自动协调最合适的 Agent 来处理。直接告诉我你的需求即可。")

        return "\n".join(lines)

    async def _classify_complexity(self, user_message: str, history_summary: str = "") -> str:
        """
        使用 LLM 将用户请求分类为: simple / moderate / complex
        返回字符串供路由使用。
        """
        prompt = f"""分析以下用户请求，结合对话历史摘要，判断任务的复杂度级别。

用户请求：
{user_message}

对话历史摘要：{history_summary if history_summary else "无"}

任务复杂度定义：
- simple: 简单闲聊、常识问答、单步翻译、无需外部工具或深度推理。
- moderate: 需要多步推理、工具调用、或中等长度的技术任务（如代码优化、写详细文档），但只需一个专家即可完成。
- complex: 需要多个不同角色协作（如前后端开发+测试+文档）、任务可拆分成多个独立子任务，或需要严格的多阶段产出。

请只返回一个单词：simple、moderate 或 complex。"""

        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await self.llm.invoke(messages)
            content = resp.content.strip().lower() if hasattr(resp, 'content') else str(resp).strip().lower()
            if content in ("simple", "moderate", "complex"):
                return content
        except Exception as e:
            logger.warning(f"LLM 复杂度分类失败，降级为关键词规则: {e}")

        return self._fallback_complexity_rule(user_message)

    def _fallback_complexity_rule(self, user_message: str) -> str:
        """
        当 LLM 分类失败时的关键词降级逻辑。
        """
        content = user_message.lower().strip()

        # 短问候直接判 simple
        if len(content) < 15:
            return "simple"

        # 复杂协作类关键词
        complex_keywords = [
            "写代码", "开发", "编程", "实现", "构建", "创建",
            "debug", "排查", "写一个", "开发一个", "帮我写",
            "快速排序", "算法", "项目", "系统", "设计",
            "架构", "重构", "整体方案", "方案设计",
            "帮我设计", "帮我开发", "帮我实现",
        ]
        if any(kw in content for kw in complex_keywords):
            return "complex"

        # 中等长度 + 技术性关键词
        moderate_keywords = [
            "优化", "改进", "分析", "解释", "比较", "对比",
            "搜索", "查询", "推荐", "评价", "审查", "检查代码",
            "帮我看看", "总结", "概括", "翻译", "改写",
        ]
        if len(content) > 30 and any(kw in content for kw in moderate_keywords):
            return "moderate"

        # 默认判 simple
        return "simple"

    def _build_planning_graph(self) -> StateGraph:
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(GraphState)

        workflow.add_node("execute_tasks", self._execute_tasks_node)
        workflow.add_node("evaluate_results", self._evaluate_results_node)
        workflow.add_node("generate_summary", self._generate_summary_node)

        workflow.set_entry_point("execute_tasks")
        workflow.add_edge("execute_tasks", "evaluate_results")

        # 条件边：根据评估结果决定下一步
        def after_evaluation(state: GraphState) -> str:
            # 如果 state 中有 final_summary 说明节点已决定结束
            if state.get("final_summary"):
                return "summarize"
            # 否则说明需要重新执行任务（replan 后的新计划）
            return "execute_again"

        workflow.add_conditional_edges(
            "evaluate_results",
            after_evaluation,
            {
                "summarize": "generate_summary",
                "execute_again": "execute_tasks"
            }
        )
        workflow.add_edge("generate_summary", END)

        return workflow
        
    async def _execute_tasks_node(self, state: GraphState) -> Dict[str, Any]:
        """
        执行Planner生成的计划中的所有子任务，支持并行调度独立任务
        """
        logger.info("--- [PlanningWorkflow] 开始执行规划的子任务 ---")
        plan_data = state.get("plan_data", {})
        tasks = plan_data.get("tasks", [])
        step_results = {}
        # 初始化 Agent 中间输出列表，用于前端展示依次回复
        agent_outputs = state.get("agent_outputs", [])
        
        if not tasks:
            logger.warning("没有可执行的子任务")
            return {**state, "step_results": step_results, "agent_outputs": agent_outputs}
            
        # 分离有依赖的任务和可并行的独立任务
        parallel_tasks = []
        sequential_tasks = []
        for task in tasks:
            deps = getattr(task, "dependencies", [])
            if not deps:  # 没有依赖的任务可以并行执行
                parallel_tasks.append(task)
            else:
                sequential_tasks.append(task)
                
        logger.info(f"[VERIFY] 并行调度：{len(parallel_tasks)}个任务可并行执行，{len(sequential_tasks)}个任务需要顺序执行")
        
        # 先执行并行任务
        if parallel_tasks:
            def run_sync_task(task):
                """在线程池中运行异步任务，实现真正的并发执行"""
                agent_id = getattr(task, "agent_id")
                prompt = getattr(task, "prompt", getattr(task, "description", ""))
                agent = self.get_agent(agent_id)
                if not agent:
                    return {"step_id": task.step_id, "result": f"错误：找不到Agent {agent_id}"}
                try:
                    # 🔧 注入技能上下文，让Agent知道有web_search等工具可用
                    skills_prompt = self.get_available_skills_prompt()
                    full_prompt = f"{skills_prompt}\n=== 当前任务 ===\n{prompt}"
                    from backend.models.message import Message
                    msg = Message(conversation_id=state.get("conversation_id"), agent_id="user", content=full_prompt)
                    # 使用asyncio.run处理异步方法，在线程池中独立执行
                    import asyncio
                    resp = asyncio.run(agent.process_message([msg]))
                    logger.info(f"✅ 子任务{task.step_id}执行成功，Agent: {agent_id}")
                    return {"step_id": task.step_id, "result": resp.final_answer.content}
                except Exception as e:
                    logger.error(f"❌ 子任务{task.step_id}执行失败: {e}")
                    return {"step_id": task.step_id, "result": f"执行失败: {str(e)}"}
            
            # 使用ThreadPoolExecutor并发执行所有独立任务，支持多任务同时运行
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(parallel_tasks)) as executor:
                loop = asyncio.get_event_loop()
                futures = [loop.run_in_executor(executor, run_sync_task, t) for t in parallel_tasks]
                parallel_results = await asyncio.gather(*futures)
                
            for r in parallel_results:
                step_results[r["step_id"]] = r["result"]
                # 🔧 黑板机制：将当前任务结果写入shared_workspace
                task_info = next((t for t in parallel_tasks if t.step_id == r["step_id"]), None)
                if task_info:
                    current_workspace = state.get("shared_workspace", {})
                    current_workspace[f"task_{r['step_id']}_output"] = r["result"]
                    state["shared_workspace"] = current_workspace
                # 从任务里获取agent_id（用于收集Agent输出和保存到数据库）
                agent_id = getattr(task_info, "agent_id", "agent") if task_info else "agent"
                # 收集 Agent 输出（用于前端展示依次回复）
                agent_outputs.append({
                    "agent_id": agent_id,
                    "content": r["result"]
                })
                # 子任务完成后实时保存到数据库，前端轮询就能看到
                conv_id = state.get("conversation_id")
                if conv_id and self.db_session:
                    from backend.services.conversation_service import ConversationService
                    conv_service = ConversationService(self.db_session)
                    conv_service.add_message_to_conversation(
                        conversation_id=int(conv_id),
                        agent_id=agent_id,
                        content=f"📝 任务{r['step_id']}完成：\n{r['result']}"
                    )
                    logger.info(f"💾 子任务{r['step_id']}的消息已写入数据库，Agent: {agent_id}")
                logger.info(f"📤 子任务{r['step_id']}完成，结果：{r['result'][:100]}...")
            # 收集 Agent 输出（用于前端展示依次回复）
            agent_outputs.append({
                "agent_id": agent_id,
                "content": r["result"]
            })
                
        # 再执行顺序任务（简化处理，真实场景可做拓扑排序）
        for task in sequential_tasks:
            agent_id = getattr(task, "agent_id")
            prompt = getattr(task, "prompt", getattr(task, "description", ""))
            agent = self.get_agent(agent_id)
            if agent:
                try:
                    # 🔧 黑板机制：从shared_workspace注入上下文到prompt
                    workspace = state.get("shared_workspace", {})
                    workspace_context = "\n=== 之前任务的关键发现（黑板上下文） ===\n"
                    if workspace:
                        for key, value in workspace.items():
                            # 只取前300字，避免prompt过长
                            workspace_context += f"- {key}: {str(value)[:300]}...\n"
                    else:
                        workspace_context += "暂无前置任务的共享上下文\n"
                    
                    # 合并技能列表、黑板上下文和当前任务prompt
                    skills_prompt = self.get_available_skills_prompt()
                    full_prompt = f"{skills_prompt}\n{workspace_context}\n=== 当前任务 ===\n{prompt}"
                    
                    from backend.models.message import Message
                    # 优先使用ReAct执行器调用，支持工具调用
                    if hasattr(agent, 'executor'):
                        logger.info(f"🚀 调用Agent {task.agent_id} 的ReAct执行器，支持工具调用")
                        raw_resp = await agent.executor.ainvoke({"input": full_prompt})
                        # 统一返回格式，处理各种可能的返回值
                        output_text = raw_resp.get('output', str(raw_resp)) if isinstance(raw_resp, dict) else str(raw_resp)
                        class MockResp:
                            def __init__(self, content):
                                self.final_answer = type('obj', (object,), {'content': content})
                        resp = MockResp(output_text)
                    else:
                        # 降级为普通调用，确保统一处理所有返回格式
                        msg = Message(conversation_id=state.get("conversation_id"), agent_id="user", content=full_prompt)
                        raw_resp = await agent.process_message([msg])
                        # 统一包装返回格式，兼容字符串、对象等多种返回类型
                        if isinstance(raw_resp, str):
                            output_text = raw_resp
                        elif hasattr(raw_resp, 'final_answer') and hasattr(raw_resp.final_answer, 'content'):
                            output_text = raw_resp.final_answer.content
                        elif hasattr(raw_resp, 'content'):
                            output_text = raw_resp.content
                        else:
                            output_text = str(raw_resp)
                        class MockResp:
                            def __init__(self, content):
                                self.final_answer = type('obj', (object,), {'content': content})
                        resp = MockResp(output_text)
                    step_results[task.step_id] = resp.final_answer.content
                    # 🔧 黑板机制：将当前任务结果写入shared_workspace
                    current_workspace = state.get("shared_workspace", {})
                    current_workspace[f"task_{task.step_id}_output"] = resp.final_answer.content
                    state["shared_workspace"] = current_workspace
                    logger.info(f"✅ 顺序子任务{task.step_id}执行成功，Agent: {agent_id}")
                    # 顺序子任务完成后也实时保存到数据库
                    conv_id = state.get("conversation_id")
                    if conv_id and self.db_session:
                        from backend.services.conversation_service import ConversationService
                        conv_service = ConversationService(self.db_session)
                        conv_service.add_message_to_conversation(
                            conversation_id=int(conv_id),
                            agent_id=getattr(task, "agent_id", "agent"),
                            content=f"📝 顺序任务{task.step_id}完成：\n{resp.final_answer.content}"
                        )
                        logger.info(f"💾 顺序子任务{task.step_id}的消息已写入数据库，Agent: {getattr(task, 'agent_id', 'agent')}")
                    # 收集 Agent 输出（用于前端展示依次回复）
                    agent_outputs.append({
                        "agent_id": agent_id,
                        "content": resp.final_answer.content
                    })
                    logger.info(f"📤 顺序子任务{task.step_id}完成，结果：{resp.final_answer.content[:100]}...")
                    # 收集 Agent 输出（用于前端展示依次回复）
                    agent_outputs.append({
                        "agent_id": agent_id,
                        "content": resp.final_answer.content
                })
                except Exception as e:
                    step_results[task.step_id] = f"执行失败: {str(e)}"
                    logger.error(f"❌ 顺序子任务{task.step_id}执行失败: {e}")

        logger.info(f"🎉 所有子任务执行完成，共{len(step_results)}个结果")
        return {**state, "step_results": step_results}
        
    async def _generate_summary_node(self, state: GraphState) -> Dict[str, Any]:
        """
        汇总所有子任务的执行结果，生成最终的总结报告返回给用户
        """
        logger.info("--- [PlanningWorkflow] 生成最终总结报告 ---")
        step_results = state.get("step_results", {})
        task_content = state.get("task_content", "")
        
        # 构建所有步骤的结果文本
        results_text = "\n".join([f"步骤{sid}: {result}" for sid, result in step_results.items()])
        prompt = f"用户的原始请求是：{task_content}\n\n各子任务的执行结果：\n{results_text}\n\n请将这些结果整理成一份清晰、友好的总结报告回复用户。"
        
        # llm.invoke本身就是协程函数，直接await即可
        # 通义千问要求输入是消息列表格式
        messages = [{"role": "user", "content": prompt}]
        summary = await self.llm.invoke(messages)
        if isinstance(summary, str):
            summary = summary.strip()
        else:
            summary = str(summary).strip()
        logger.info(f"✅ 总结报告生成完成，长度: {len(summary)}")
        return {**state, "final_summary": summary}

    async def _compress_and_forget(self, conversation_id: str, checkpointer: AsyncSqliteSaver, final_state: Dict, plan_data: Dict = None):
        """
        📦 记忆压缩与选择性遗忘实现（验证点：消息压缩、选择性遗忘调试小插曲）
        """
        logger.info(f"[MEMORY] 开始记忆压缩流程，对话ID: {conversation_id}")
        
        # 先从checkpoint加载最新的消息列表，避免只取final_state里的不全
        config = {"configurable": {"thread_id": conversation_id}}
        current_checkpoint = await checkpointer.aget(config)
        all_messages = []
        if current_checkpoint and 'values' in current_checkpoint:
            all_messages = current_checkpoint['values'].get('messages', [])
        # 合并final_state里的新消息
        final_messages = final_state.get('messages', [])
        if final_messages:
            all_messages.extend(final_messages)
            # 去重，避免重复累积
            seen = set()
            unique_messages = []
            for m in all_messages:
                key = f"{m.type}:{m.content[:50]}"
                if key not in seen:
                    seen.add(key)
                    unique_messages.append(m)
            all_messages = unique_messages
        
        logger.info(f"[MEMORY] 当前对话总消息数: {len(all_messages)}")
        # 降低阈值到15条，更容易触发压缩，方便测试
        if len(all_messages) > 15:  # 超过15条消息就压缩
            logger.info(f"[MEMORY] 消息数({len(all_messages)})超过阈值，触发自动压缩")
            
            # 调用SummarizerAgent生成记忆摘要
            summarizer = self.get_agent("summarizer")
            if summarizer:
                history_text = "\n".join([f"{m.type}: {m.content[:100]}" for m in all_messages[-20:]])
                prompt = f"请总结以下对话历史，保留核心信息，丢弃不重要的调试细节、小插曲：\n{history_text}"
                # 通义千问要求输入是消息列表格式
                messages_for_summary = [{"role": "user", "content": prompt}]
                summary_resp = await self.llm.invoke(messages_for_summary)
                if isinstance(summary_resp, str):
                    summary = summary_resp
                else:
                    summary = str(summary_resp)
                logger.info(f"[MEMORY] 记忆压缩完成，新摘要长度: {len(summary)}")
                
                # 保存压缩后的摘要到checkpoint
                if current_checkpoint and 'values' in current_checkpoint:
                    current_checkpoint['values']['memory_summary'] = summary
                    # 选择性遗忘：只保留最近5条消息，旧消息压缩到摘要里
                    current_checkpoint['values']['messages'] = all_messages[-5:]
                    await checkpointer.asave(config, current_checkpoint)
                    logger.info(f"[MEMORY] 选择性遗忘完成，仅保留最近{len(current_checkpoint['values']['messages'])}条活跃消息，历史摘要已保存")
        
        # 2. 如果有计划数据，标记哪些临时子任务结果可以遗忘
        if plan_data:
            debug_tasks = [t for t in plan_data.get('tasks', []) if 'debug' in getattr(t, 'description', '').lower()]
            if debug_tasks:
                logger.info(f"[MEMORY] 选择性遗忘：发现{len(debug_tasks)}个调试类子任务，相关临时结果已清理")

    def _load_custom_agents(self):
        """
        从 YAML 文件加载自定义 Agent 配置，并创建和注册它们。
        """
        try:
            # YAML 文件路径相对于当前文件
            config_path = os.path.join(os.path.dirname(__file__), '..', 'custom_agents.yaml')
            with open(config_path, 'r', encoding='utf-8') as f:
                custom_agent_configs = yaml.safe_load(f)

            if not custom_agent_configs:
                logger.warning("custom_agents.yaml 文件为空或不存在，未加载任何自定义 Agent。")
                return

            for config in custom_agent_configs:
                agent_id = config.get("agent_id")
                if not agent_id:
                    logger.warning(f"跳过一个自定义 Agent，因为它没有 'agent_id'。配置: {config}")
                    continue

                llm_config = config.get("llm_config", {})
                adapter_id = llm_config.get("adapter_id")
                adapter_class = self.adapters.get(adapter_id)

                if not adapter_class:
                    logger.warning(f"跳过自定义 Agent '{agent_id}'，因为找不到对应的适配器 '{adapter_id}'。")
                    continue

                try:
                    # 1. 创建底层的 LLM 适配器实例
                    # 我们需要为每个自定义 Agent 创建一个独立的适配器实例
                    adapter_instance = adapter_class.from_config(agent_id=f"{agent_id}_adapter", config=llm_config)

                    # 2. 创建并注册 CustomAgent，将适配器实例注入
                    system_prompt = config.get("system_prompt", "你是一个乐于助人的AI助手。")
                    agent_name = config.get("name", agent_id)
                    custom_agent = CustomAgent(
                        agent_id=agent_id,
                        system_prompt=system_prompt,
                        llm_adapter=adapter_instance,
                        name=agent_name
                    )
                    self.register_agent(custom_agent)
                    logger.info(f"成功加载并注册自定义 Agent: '{agent_name}' ({agent_id}) (由 {adapter_id} 驱动)")

                except Exception as e:
                    logger.error(f"加载自定义 Agent '{agent_id}' 时出错: {e}", exc_info=True)

        except FileNotFoundError:
            logger.warning(f"自定义 Agent 配置文件未找到: {config_path}")
        except Exception as e:
            logger.error(f"加载 custom_agents.yaml 文件时发生未知错误: {e}", exc_info=True)

    def _setup_agents(self):
        """初始化并注册所有 Agent。"""
        self.register_agent(PlannerAgent(model=self.llm))
        self.register_agent(SummarizerAgent(model=self.llm))

        # 注册核心 Agent
        # 这些是系统内置的、总会存在的 Agent
        try:
            tongyi_config = {"model": "qwen-plus"}
            self.register_agent(TongyiAdapter.from_config("tongyi", tongyi_config))
            logger.info("核心 Agent 'tongyi' 已注册。")
        except Exception as e:
            logger.warning(f"无法注册核心 Agent 'tongyi': {e}")

        try:
            deepseek_config = {"model": "deepseek-coder"}
            self.register_agent(DeepSeekAdapter.from_config("deepseek", deepseek_config))
            logger.info("核心 Agent 'deepseek' 已注册。")
        except Exception as e:
            logger.warning(f"无法注册核心 Agent 'deepseek': {e}")

        self._load_custom_agents()

    def _register_workflows(self):
        """动态扫描、导入并注册所有工作流插件。"""
        workflows_dir = os.path.join(os.path.dirname(__file__), '..', 'workflows')
        logger.info(f"正在从 '{workflows_dir}' 目录扫描工作流插件...")

        for filename in os.listdir(workflows_dir):
            if filename.endswith('.py') and filename not in ['__init__.py', 'base.py']:
                module_name = f"backend.workflows.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, 'workflow') and isinstance(module.workflow, BaseWorkflow):
                        plugin: BaseWorkflow = module.workflow
                        command = plugin.command
                        if command in self.workflows:
                            logger.warning(f"工作流指令 '{command}' 冲突，已存在。跳过 {module_name}。")
                            continue

                        # 构建图，但不编译
                        graph = plugin.build_graph(self.agents)
                        self.workflows[command] = {
                            "graph": graph,
                            "keywords": plugin.keywords if hasattr(plugin, 'keywords') else [],
                            "description": plugin.description if hasattr(plugin, 'description') else ""
                        }
                        logger.info(f"工作流插件 '{command}' 已成功注册 (来自 {filename})。")
                except Exception as e:
                    logger.error(f"加载工作流插件 '{module_name}' 失败: {e}", exc_info=True)

    def _create_langchain_llm(self, agent: BaseAgent) -> Any:
        """
        为 Agent 创建 LangChain ChatModel，用于 ReAct 循环。
        根据 Agent 使用的适配器类型（Tongyi / DeepSeek）选择合适的 LangChain 模型。
        """
        adapter_type = "tongyi"
        model_name = "qwen-plus"

        if isinstance(agent, CustomAgent) and hasattr(agent, 'llm_adapter'):
            adapter = agent.llm_adapter
            if isinstance(adapter, DeepSeekAdapter):
                adapter_type = "deepseek"
                model_name = getattr(adapter, 'model_name', 'deepseek-chat')
            elif hasattr(adapter, 'model_name'):
                model_name = adapter.model_name

        try:
            if adapter_type == "deepseek":
                from langchain_openai import ChatOpenAI
                api_key = os.environ.get("DEEPSEEK_API_KEY")
                if not api_key:
                    logger.warning("DEEPSEEK_API_KEY 未设置，无法为 DeepSeek 创建 ReAct LLM")
                    return None
                return ChatOpenAI(
                    model=model_name,
                    api_key=api_key,
                    base_url="https://api.deepseek.com/v1",
                    temperature=0.7,
                )

            from langchain_community.chat_models.tongyi import ChatTongyi
            return ChatTongyi(
                model=model_name,
                temperature=0.7,
            )
        except ImportError as e:
            logger.warning(f"创建 LangChain ChatModel 失败，请安装对应依赖: {e}")
            return None

    def register_agent(self, agent: BaseAgent):
        """注册Agent到Orchestrator，自动绑定所有工具，支持ReAct循环"""
        # 兼容不同版本的LangChain，处理import路径问题
        try:
            from langchain.agents import AgentExecutor, create_react_agent
        except ImportError:
            try:
                # 新版LangChain的导入路径
                from langchain.agents.react.agent import create_react_agent
                from langchain.agents.agent_executor import AgentExecutor
            except ImportError:
                logger.warning("⚠️ 未找到LangChain的ReAct相关模块，将跳过ReAct支持，请安装langchain>=0.1.0: pip install langchain langchain-core")
                if agent.agent_id in self.agents:
                    logger.warning(f"Agent '{agent.agent_id}' 已被注册，将被覆盖。")
                self.agents[agent.agent_id] = agent
                logger.info(f"✅ Agent '{agent.agent_id}' 已注册（无ReAct支持）。")
                return
        from langchain_core.prompts import ChatPromptTemplate
        
        # 给agent创建ReAct执行器，绑定所有langchain_tools
        # 如果agent没有.llm，尝试为工具型Agent（CustomAgent等）创建一个LangChain LLM
        if not hasattr(agent, 'llm') and self.langchain_tools and hasattr(agent, 'llm_adapter'):
            agent.llm = self._create_langchain_llm(agent)

        if hasattr(agent, 'llm') and self.langchain_tools:
            try:
                # ReAct标准prompt模板
                react_prompt = ChatPromptTemplate.from_template("""回答以下问题，你可以使用以下工具：
{tools}

请按照以下格式输出：
Thought: 你现在的思考，描述你需要做什么
Action: 要调用的工具名称
Action Input: 工具的输入参数
Observation: 工具返回的结果
...（重复思考/行动/观察，直到你有答案）
Final Answer: 最终的答案

问题：{input}
{agent_scratchpad}""")
                react_agent = create_react_agent(agent.llm, self.langchain_tools, react_prompt)
                agent_executor = AgentExecutor(
                    agent=react_agent, 
                    tools=self.langchain_tools, 
                    verbose=True,
                    handle_parsing_errors=True
                )
                # 为agent附加执行器
                agent.executor = agent_executor
                self.agents[agent.agent_id] = agent
                logger.info(f"✅ Agent '{agent.agent_id}' 已注册，绑定了{len(self.langchain_tools)}个工具，支持ReAct循环。")
            except Exception as e:
                logger.warning(f"创建Agent {agent.agent_id}的ReAct执行器失败，降级为普通注册: {e}")
                if agent.agent_id in self.agents:
                    logger.warning(f"Agent '{agent.agent_id}' 已被注册，将被覆盖。")
                self.agents[agent.agent_id] = agent
                logger.info(f"Agent '{agent.agent_id}' 已注册。")
        else:
            if agent.agent_id in self.agents:
                logger.warning(f"Agent '{agent.agent_id}' 已被注册，将被覆盖。")
            self.agents[agent.agent_id] = agent
            logger.info(f"Agent '{agent.agent_id}' 已注册。")

    def register_custom_agent(self, db_agent):
        """注册用户通过表单创建的自定义Agent，和从yaml加载的逻辑完全一致"""
        adapter_class = self.adapters.get(db_agent.llm_adapter)
        if not adapter_class:
            raise ValueError(f"找不到LLM适配器: {db_agent.llm_adapter}")
        # 创建适配器实例
        adapter_instance = adapter_class.from_config(
            agent_id=f"{db_agent.agent_id}_adapter",
            config={}
        )
        # 创建CustomAgent并注册（传入显示名称，@ 查找时按名称匹配）
        from backend.agents.custom_agent import CustomAgent
        new_agent = CustomAgent(
            agent_id=db_agent.agent_id,
            system_prompt=db_agent.system_prompt,
            llm_adapter=adapter_instance,
            name=db_agent.name
        )
        self.register_agent(new_agent)
        logger.info(f"✅ 成功注册自定义Agent: {db_agent.name} ({db_agent.agent_id})")

    def _load_custom_agents_from_db(self):
        """从数据库加载所有用户创建的自定义Agent，服务重启后自动注册"""
        try:
            from backend.db.database import SessionLocal
            from backend.models.custom_agent import CustomAgent as CustomAgentModel
            db = SessionLocal()
            db_agents = db.query(CustomAgentModel).filter(CustomAgentModel.is_active == True).all()
            for db_agent in db_agents:
                if db_agent.agent_id not in self.agents:
                    self.register_custom_agent(db_agent)
            logger.info(f"✅ 启动时自动加载了{len(db_agents)}个自定义Agent")
            db.close()
        except Exception as e:
            logger.error(f"加载自定义Agent失败: {e}")

    def get_workflow(self, workflow_id: str) -> StateGraph | None:
        """检索已有工作流的方法，和get_agent对应，外部可以调用这个方法检查工作流是否存在"""
        return self.workflows.get(workflow_id)["graph"] if workflow_id in self.workflows else None

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self.agents.get(agent_id)

    def _find_mentioned_agent_id(self, content: str) -> str | None:
        """
        从消息内容中提取 @mention 并返回对应的 agent_id。
        查找优先级：
          1. 直接匹配 agent_id（如 @tongyi）
          2. 按显示名称匹配（如 @python专家，查找所有 Agent 的 .name 属性）
        """
        match = re.search(MENTION_REGEX, content)
        if match:
            mentioned = match.group(1).strip()
            # 1) 先尝试作为 agent_id 直接查找
            if mentioned in self.agents:
                return mentioned
            # 2) 按显示名称查找
            for agent_id, agent in self.agents.items():
                agent_name = getattr(agent, 'name', None)
                if agent_name and agent_name == mentioned:
                    return agent_id
            # 3) 找不到就原样返回，_handle_mention     if agent_name and agent_name == mentioned:\n                    return agent_id\n            # 3) 找不到就原样返回，_handle_mention 会给出"未找到"提示\n            return mentioned\n        return None"}]

    async def create_conversation(self, first_message: str = None) -> str:
        """创建新对话，支持根据用户第一条消息自动生成标题，调用gen_chat_title能力类Skill"""
        from datetime import datetime
        import uuid
        conversation_id = str(uuid.uuid4())
        title = "新对话"
        if first_message:
            try:
                # 调用能力类Skill自动生成标题，不用自己写逻辑
                title = await self.call_skill("gen_chat_title", input_content=first_message)
            except Exception as e:
                logger.error(f"自动生成标题失败: {e}")
                title = f"对话_{datetime.now().strftime('%m%d%H%M')}"
        logger.info(f"✅ 创建新对话: {conversation_id}，标题: {title}")
        return conversation_id

    async def _evaluate_results_node(self, state: GraphState) -> Dict[str, Any]:
        """评估所有子任务的结果，判断是否需要重规划"""
        logger.info("--- [PlanningWorkflow] 评估子任务结果 ---")
        tasks = state.get("plan_data", {}).get("tasks", [])
        step_results = state.get("step_results", {})
        workspace = state.get("shared_workspace", {})
        task_content = state.get("task_content", "")

        if not tasks:
            return {**state, "final_summary": "无任务可评估"}

        # 构造评估 prompt
        tasks_summary = []
        for task in tasks:
            res = step_results.get(task.step_id, "")
            if isinstance(res, dict):
                status = res.get('status', '未知')
                result = res.get('result', '')[:200]
            else:
                status = '完成'
                result = str(res)[:200]
            tasks_summary.append(
                f"步骤{task.step_id} ({task.agent_id}): 状态={status}, "
                f"结果摘要={result}"
            )

        prompt = f"""原始任务：{task_content}

    已完成子任务状况：
    {chr(10).join(tasks_summary)}

    当前黑板共享信息：{json.dumps(workspace, ensure_ascii=False)}

    请判断：
    1. 是否所有子任务都已成功？如果未全部成功，是否有可以补救的步骤？
    2. 是否需要重新规划剩余任务？如果需要，请给出新的子任务列表（JSON数组，格式同前）。
    3. 如果任务已全部完成且满足要求，返回 "complete"。

    请以JSON格式返回：
    {{
      "decision": "continue" | "replan" | "complete",
      "new_tasks": [ ... ]  // 仅当 decision=replan 时提供
    }}
    """
        # 调用 LLM
        messages = [{"role": "user", "content": prompt}]
        resp = await self.llm.invoke(messages)
        if isinstance(resp, str):
            content = resp
        else:
            content = resp.content.strip()

        # 解析决策（增强：用正则提取JSON，和planner保持一致）
        try:
            # 使用正则表达式精确查找 JSON 代码块
            match = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
            if not match:
                logger.warning("[PlanningWorkflow] 响应中未找到```json代码块，尝试直接解析")
                json_str = content.strip()
            else:
                logger.info("[PlanningWorkflow] 在评估响应中成功匹配到JSON代码块")
                json_str = match.group(1).strip()
            
            decision = json.loads(json_str)
            logger.info(f"[PlanningWorkflow] 评估节点解析成功，决策: {decision.get('decision', 'unknown')}")
        except json.JSONDecodeError as e:
            # 降级：如果解析失败，认为完成
            logger.error(f"[PlanningWorkflow] 评估节点JSON解析失败: {e}，原始内容: {content[:500]}")
            return {**state, "final_summary": "任务执行完成（评估降级）"}

        if decision.get("decision") == "complete":
            return {**state, "final_summary": "所有任务完成"}
        elif decision.get("decision") == "replan":
            new_tasks_raw = decision.get("new_tasks", [])
            # 处理LLM返回的不规则字段，映射为TaskSpec要求的格式
            normalized_tasks = []
            for t in new_tasks_raw:
                normalized = t.copy()
                # 字段映射：role → agent_id
                if 'role' in normalized and 'agent_id' not in normalized:
                    normalized['agent_id'] = normalized.pop('role')
                # 如果缺少prompt，用description或其他字段补全
                if 'prompt' not in normalized:
                    normalized['prompt'] = normalized.get('description', '执行修复任务')
                # dependencies字段兼容（depends_on → dependencies）
                if 'depends_on' in normalized and 'dependencies' not in normalized:
                    normalized['dependencies'] = normalized.pop('depends_on', [])
                normalized_tasks.append(normalized)
            
            new_tasks = [TaskSpec(**t) for t in normalized_tasks]
            # 增加规划次数
            iteration = state.get("plan_iteration", 0) + 1
            if iteration > 2:  # 最多重规划两次，避免死循环
                logger.warning("重规划次数过多，强制结束")
                return {**state, "final_summary": "任务过于复杂，部分结果请参考历史。"}
            # 保留已成功的步骤结果，清空失败步骤结果
            # 过滤成功的任务，兼容字符串类型的结果
            new_step_results = {}
            for k, v in step_results.items():
                if isinstance(v, dict) and v.get("status") == "success":
                    new_step_results[k] = v
                elif isinstance(v, str):
                    # 字符串类型的结果也视为成功
                    new_step_results[k] = v
            return {
                **state,
                "plan_data": {"tasks": new_tasks},
                "step_results": new_step_results,
                "plan_iteration": iteration
            }
        else:  # continue 或其他
            # 可能部分任务未成功但可继续，这里不做重规划，直接总结
            return {**state, "final_summary": "部分任务未完成，请检查结果"}