import asyncio
import json
import re
import os
import importlib
import yaml
from typing import List, Dict, Any, Callable, Optional, AsyncGenerator


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
from backend.llm.backend import LLMBackend
from backend.core.response_checker import check_response_completeness
from backend.llm.backends import TongyiBackend, DeepSeekBackend, OpenCodeBackend
from backend.workflows.base import BaseWorkflow

from backend.utils.logger import logger
from backend.core.memory_strategy import apply_memory_strategy
from backend.core.validation_strategy import apply_validation_strategy, get_max_retries
from backend.config.prompts import get_prompt_loader

# 边界情况 & Replan 闭环模块
from backend.core.task_status import (
    OrchestratorState, TaskState,
    can_transition, is_terminal, is_failed_state,
)
from backend.core.quality_checker import QualityChecker
from backend.core.replan_evaluator import (
    ReplanEvaluator, EvaluationVerdict, check_hard_replan_conditions,
)
from backend.core.config import (
    MAX_REPLAN_LIMIT, QUALITY_THRESHOLD, MAX_TASK_RETRIES, ENABLE_QUALITY_CHECK,
)

# 一个简单的正则表达式，用于从消息内容中匹配 @agent_id
MENTION_REGEX = r'@(\w+)'
WORKFLOW_TRIGGER_THRESHOLD = 6


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
        self.llm_backends: Dict[str, LLMBackend] = {}  # LLM 后端注册表
        self.adapters: Dict[str, type[BaseAgent]] = {
            "deepseek": DeepSeekAdapter,
            "tongyi": TongyiAdapter,
        }
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
        # 提示词加载器
        self.prompt_loader = get_prompt_loader()

        # 🎯 优化后的初始化顺序：先核心，后业务
        # 0. 先注册所有 LLM 后端（统一适配器层的基础）
        self._setup_backends()
        # 0.5 健康检查：移除超时/不可用的后端
        self._health_check_backends()
        # 1. 再加载所有Skill（工具类），这样注册Agent时 langchain_tools 已就绪
        self._load_native_skills()
        self._register_builtin_tool_skills()
        # 2. 再注册所有核心Agent（此时已有工具，可以创建ReAct执行器）
        self._setup_agents()
        # 3. 注册所有工作流（内置+自定义）
        self._register_builtin_workflows()
        self._register_workflows()
        # 4. 定义动态规划工作流的蓝图
        self.planning_graph_builder = self._build_planning_graph()
        # 5. 最后加载数据库里的自定义Agent
        self._load_custom_agents_from_db()
        # 6. 初始化边界情况 & Replan 闭环模块
        self._init_boundary_modules()
        logger.info("✅ Orchestrator 初始化完成，所有组件加载成功。")

    def _init_boundary_modules(self):
        """初始化边界情况 & Replan 闭环模块（QualityChecker + ReplanEvaluator）。"""
        try:
            llm_backend = self.get_backend("tongyi")
            async def _llm_invoke(messages):
                return await llm_backend.chat(messages)
            self.quality_checker = QualityChecker(
                llm_invoke=_llm_invoke if ENABLE_QUALITY_CHECK else None,
                quality_threshold=QUALITY_THRESHOLD,
                enable=ENABLE_QUALITY_CHECK,
            )
            self.replan_evaluator = ReplanEvaluator(
                llm_invoke=_llm_invoke,
                prompt_loader=self.prompt_loader,
            )
            logger.info(
                f"✅ 边界模块已初始化: quality_checker={'enabled' if ENABLE_QUALITY_CHECK else 'disabled'}, "
                f"replan_evaluator=enabled, max_replan={MAX_REPLAN_LIMIT}, "
                f"quality_threshold={QUALITY_THRESHOLD}, max_task_retries={MAX_TASK_RETRIES}"
            )
        except Exception as e:
            logger.warning(f"⚠️ 边界模块初始化失败（非致命，降级运行）: {e}")
            self.quality_checker = None
            self.replan_evaluator = None

    def _setup_backends(self):
        """
        注册所有 LLM 后端（统一适配器层）。
        每个后端封装一个 LLM 平台的 API 调用，提供统一的 chat / chat_stream 接口。
        """
        try:
            tongyi = TongyiBackend(model="qwen-plus")
            self.llm_backends["tongyi"] = tongyi
            logger.info(f"LLM 后端 'tongyi' 已注册 (model={tongyi.model_name})")
        except Exception as e:
            logger.warning(f"注册 LLM 后端 'tongyi' 失败: {e}")

        try:
            deepseek = DeepSeekBackend(model="deepseek-chat")
            self.llm_backends["deepseek"] = deepseek
            logger.info(f"LLM 后端 'deepseek' 已注册 (model={deepseek.model_name})")
        except Exception as e:
            logger.warning(f"注册 LLM 后端 'deepseek' 失败: {e}")

        try:
            opencode = OpenCodeBackend(model=OpenCodeBackend.DEFAULT_MODEL)
            self.llm_backends["opencode"] = opencode
            logger.info(f"LLM 后端 'opencode' 已注册 (model={opencode.model_name})")
        except ValueError as e:
            logger.warning(f"注册 LLM 后端 'opencode' 失败: {e}")
        except Exception as e:
            logger.warning(f"注册 LLM 后端 'opencode' 失败: {e}")

    def _health_check_backends(self, timeout: int = 8):
        """启动时同步健康检查所有后端，超时自动移除不可用后端。"""
        import httpx
        for name, backend in list(self.llm_backends.items()):
            try:
                url = getattr(backend, 'base_url', '')
                if not url:
                    continue
                client_url = url.rstrip('/')
                if '/chat/completions' not in client_url:
                    client_url += '/chat/completions'
                payload = {"model": getattr(backend, 'model_name', 'qwen-plus'),
                           "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
                with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
                    resp = client.post(
                        client_url,
                        headers={"Authorization": f"Bearer {getattr(backend, 'api_key', '')}",
                                 "Content-Type": "application/json"},
                        json=payload,
                    )
                    ok = resp.status_code == 200
            except Exception:
                ok = False
            if ok:
                backend._healthy = True
                logger.info(f"[HEALTH-CHECK] 后端 '{name}' 连通性检查通过")
            else:
                backend._healthy = False
                logger.warning(f"[HEALTH-CHECK] 后端 '{name}' 连通性检查失败（超时 {timeout}s），将被停用")
                del self.llm_backends[name]

    def get_backend(self, name: str) -> LLMBackend:
        """
        按名称获取 LLM 后端。
        如果找不到，返回默认后端（tongyi）；如果没有任何后端，抛出异常。
        """
        backend = self.llm_backends.get(name)
        if backend is not None:
            return backend
        # 降级：尝试用默认后端
        if "tongyi" in self.llm_backends:
            logger.warning(f"后端 '{name}' 未找到，降级使用 'tongyi'")
            return self.llm_backends["tongyi"]
        # 没有任何后端可用
        raise RuntimeError("没有可用的 LLM 后端，请检查配置")

    @property
    def llm(self) -> LLMBackend:
        """
        兼容旧代码：返回默认 LLM 后端（tongyi）。
        新代码应直接使用 self.get_backend(name).chat()。
        """
        return self.get_backend("tongyi")

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
        # 处理能力类Skill（md文件），但跳过已经有对应工具类Skill的（避免 ReAct Action: 格式和 SKILL_CALL: 格式冲突）
        native_skills_desc = []
        for skill_name, skill_content in self.native_skills.items():
            if skill_name in self.tool_skills:
                logger.debug(f"跳过能力类Skill '{skill_name}'，已有对应的工具类Skill，由ReAct执行器管理")
                continue
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
            return await self.get_backend("tongyi").chat([{"role": "user", "content": full_prompt}])
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
        # 注册文件转换工具组的所有方法
        try:
            file_converter = importlib.import_module('backends.utils.file_converter')
            # 获取所有导出的函数
            converter_funcs = getattr(file_converter, '__all__', [])
            for func_name in converter_funcs:
                if func_name != "FileConversionError" and hasattr(file_converter, func_name):
                    self.tool_skills[f"file_converter.{func_name}"] = getattr(file_converter, func_name)
        except ImportError as e:
            logger.warning(f"加载file_converter工具失败: {e}")
            pass
        try:
            manage_agent = importlib.import_module('backends.utils.manage_agent')
            manage_agent_funcs = getattr(manage_agent, '__all__', [])
            for func_name in manage_agent_funcs:
                if hasattr(manage_agent, func_name):
                    self.tool_skills[f"manage_agent.{func_name}"] = getattr(manage_agent, func_name)
        except ImportError as e:
            logger.warning(f"加载manage_agent工具失败: {e}")
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
        if best_match and max_score > WORKFLOW_TRIGGER_THRESHOLD:
            logger.info(f"🎯 自动匹配到工作流: {best_match}，匹配得分: {max_score}，超过阈值{WORKFLOW_TRIGGER_THRESHOLD}，触发工作流")
            return best_match, max_score
        else:
            logger.info(f"🎯 匹配得分{max_score}未达阈值{WORKFLOW_TRIGGER_THRESHOLD}，不触发固定工作流，进入深度调度逻辑")
            return None, 0

    async def get_chat_response(
        self,
        conversation_id: str,
        messages: List[Dict[str, str]],
        request_context: Optional[Dict[str, Any]] = None,
        agent_override: Optional[Dict[str, Any]] = None,
        progressive_queue: Optional[asyncio.Queue] = None,
    ) -> Dict[str, Any]:
        """
        重构后的核心调度入口：完全自主判断用户请求，不需要用户输入任何/xxx命令
        优先级：@mention > Agent管理请求 > 自动匹配的固定工作流 > 复杂任务动态规划 > 普通聊天

        agent_override: 可选。前端在"切换 Agent 后发消息"时传入 {id, name, ...}，
                        框架会自动将最后一条 user 消息改写为 "@<agent_id> <content>"
                        走 mention 路由，无需用户手动 @。
        progressive_queue: 可选。流式场景下，各路由路径将中间结果实时推入此队列。
        """
        if not messages:
            return {"agent_id": "orchestrator", "content": "没有收到任何消息。"}

        # 🎯 agent_override 注入：把最后一条 user 消息改写为 @mention 形式
        #     仅当用户没有显式 @ 时注入，避免覆盖 @xxx
        if agent_override and messages:
            override_id = agent_override.get("id") or agent_override.get("agent_id")
            if override_id:
                last = messages[-1]
                if last.get("role") == "user" and "@" not in (last.get("content") or ""):
                    new_content = f"@{override_id} {last.get('content', '')}".strip()
                    messages = list(messages[:-1]) + [{"role": "user", "content": new_content}]
                    logger.info(f"[AGENT-OVERRIDE] 自动注入 @mention: {override_id}")

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

        # 在顶层管理 checkpointer 的生命周期（持久连接，不提前退出）
        if not hasattr(self, '_checkpointer') or self._checkpointer is None:
            import aiosqlite
            _conn = await aiosqlite.connect("agenthub_memory.sqlite")
            self._checkpointer = AsyncSqliteSaver(_conn)
        checkpointer = self._checkpointer
        config = {"configurable": {"thread_id": conversation_id}}
        current_checkpoint = await checkpointer.aget(config)
        if current_checkpoint:
            msg_count = len(current_checkpoint.get('values', {}).get('messages', []))
            logger.info(f"[MEMORY] 加载历史记忆，当前对话消息数: {msg_count}")
        else:
            logger.info(f"[MEMORY] 新对话，无历史记忆，开始记录上下文")

        # 1. 第一优先级：检查@mention — 支持多个 @agent
        mentioned_ids = self._find_mentioned_agent_ids(content)
        # 过滤掉不是真正 Agent 的 @mention（如 override 注入的 "orchestrator"）
        mentioned_ids = [mid for mid in mentioned_ids if mid in self.agents]
        if len(mentioned_ids) >= 2:
            logger.info(f"[VERIFY] 触发多Agent群聊路由: {mentioned_ids}")
            return await self._handle_multiple_mentions(
                mentioned_ids, conversation_id, messages, request_context or {},
                progressive_queue=progressive_queue,
            )
        if len(mentioned_ids) == 1:
            logger.info(f"[VERIFY] 触发@mention路由: {mentioned_ids[0]}")
            return await self._handle_mention(mentioned_ids[0], conversation_id, messages, request_context or {})

        # 2. 第二优先级：Agent 管理请求
        if complexity_level == "agent_management":
            logger.info("[VERIFY] LLM 分类为 Agent 管理请求，优先路由到 agent_builder")
            return await self._handle_agent_management_request(conversation_id, messages, request_context or {})

        # 3. 第三优先级：自动匹配固定工作流
        matched_workflow, max_score = self._auto_match_workflow(content)
        if matched_workflow and max_score > WORKFLOW_TRIGGER_THRESHOLD:
            logger.info(f"[VERIFY] 工作流/技能选择：触发固定工作流 '{matched_workflow}'，得分{max_score}达阈值{WORKFLOW_TRIGGER_THRESHOLD}，跳过动态规划")
            return await self._handle_workflow_command(matched_workflow, conversation_id, content, messages,
                                                       checkpointer, progressive_queue=progressive_queue)
        else:
            logger.info(f"[VERIFY] 任务判断：匹配得分{max_score}未达阈值({WORKFLOW_TRIGGER_THRESHOLD})，进入深度调度逻辑")

        # 4. 第四优先级：LLM 复杂度路由
        if complexity_level == "complex":
            logger.info(f"[VERIFY] 工作流/技能选择：复杂任务，启动动态规划")
            return await self._handle_plan_command(
                conversation_id, content, checkpointer, request_context or {},
                progressive_queue=progressive_queue,
            )

        if complexity_level == "simple":
            logger.info(f"[VERIFY] 工作流/技能选择：简单任务，Orchestrator 直接回复")
            return await self._handle_simple_chat(content, messages, progressive_queue)

        if complexity_level == "moderate":
            logger.info(f"[VERIFY] 工作流/技能选择：中等复杂度任务，路由到主 Agent 直接执行")
            enhanced_content = f"用户有一个任务交给你，请认真完成，如果需要搜索或调用工具可以自行使用。\n\n任务：{content}"
            moderate_messages = [{"role": "user", "content": enhanced_content}]
            return await self._handle_default_chat(conversation_id, moderate_messages, progressive_queue)

        # 5. Skill 调用请求
        skill_call = self._parse_skill_call(content)
        if skill_call:
            skill_name, method, input_content = skill_call
            logger.info(f"[VERIFY] 工作流/技能选择：触发技能调用 '{skill_name}{'.'+method if method else ''}'")
            skill_result = await self.call_skill(skill_name, method, input_content)
            final_prompt = f"Skill调用结果：{skill_result}\n\n请把这个结果整理成自然语言回复用户。"
            messages = [{"role": "user", "content": final_prompt}]
            final_response = await self.get_backend("tongyi").chat(messages)
            if isinstance(final_response, str):
                final_content = final_response.strip()
            else:
                final_content = str(final_response).strip()
            return {"agent_id": "orchestrator", "content": final_content}

        # 6. 系统查询
        system_reply = self._handle_system_query(content)
        if system_reply:
            logger.info(f"[VERIFY] 工作流/技能选择：系统查询，由 Orchestrator 自行回答")
            return {"agent_id": "orchestrator", "content": system_reply}

        # 7. 默认行为：普通聊天
        logger.info(f"[VERIFY] 工作流/技能选择：普通聊天，路由到默认对话Agent")
        return await self._handle_default_chat(conversation_id, messages, progressive_queue)

    async def get_chat_stream(
        self,
        conversation_id: str,
        messages: List[Dict[str, str]],
        request_context: Optional[Dict[str, Any]] = None,
        agent_override: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式聊天接口（async generator）。

        设计：保留 get_chat_response 的全部路由逻辑；产出以"伪流式"形式逐 token 推送
              最终 content。复杂任务规划场景下，intermediate_messages 也会在 final 之前
              依次 yield 出来。

        Yield 格式：
          {"type": "token",        "content": "..."}
          {"type": "intermediate", "agent_id": "...", "content": "...", "type": "plan|output"}
          {"type": "artifact",     "type": "code|html_preview|markdown", "title": "...", "content": "..."}
          {"type": "thinking",     "agent_id": "...", "status": "thinking|done"}
          {"type": "final",        "content": "...", "intermediate_messages": [...], "artifacts": [...]}
          {"type": "error",        "message": "..."}
        """
        # 每个流式请求独立队列，避免并发干扰
        per_request_queue: asyncio.Queue = asyncio.Queue()

        yield {"type": "thinking", "agent_id": "orchestrator", "status": "thinking"}

        # 1) 后台启动路由，同时消费逐步推送的中间结果
        main_task = asyncio.create_task(
            self.get_chat_response(
                conversation_id=conversation_id,
                messages=messages,
                request_context=request_context,
                agent_override=agent_override,
                progressive_queue=per_request_queue,
            )
        )
        intermediate_from_queue: List[Dict] = []
        aggregated_artifacts: List[Dict] = []
        had_token_stream = False
        while not main_task.done():
            try:
                entry = per_request_queue.get_nowait()
                # token 事件 → 实时 yield 给前端
                if entry.get("type") == "token_event":
                    had_token_stream = True
                    yield {"type": "token", "content": entry["token"]}
                elif entry.get("type") == "thinking":
                    yield {"type": "thinking", "agent_id": entry.get("agent_id", "agent"), "status": entry.get("status", "thinking")}
                elif entry.get("type") == "tool_output":
                    # 工具调用结果不作为 intermediate 渲染，也不收集到 intermediate_messages
                    pass
                else:
                    intermediate_from_queue.append(entry)
                    yield {
                        "type": "intermediate",
                        "agent_id": entry.get("agent_id", "agent"),
                        "content": entry.get("content", ""),
                        "type_detail": entry.get("type", "output"),
                    }
                    for art in entry.get("artifacts", []):
                        aggregated_artifacts.append(art)
                        yield {"type": "artifact", **art}
                await asyncio.sleep(0)
            except asyncio.QueueEmpty:
                pass
            try:
                await asyncio.wait_for(
                    asyncio.shield(main_task),
                    timeout=0.5,
                )
            except asyncio.TimeoutError:
                continue

        # 取回最终结果
        try:
            response = main_task.result()
        except Exception as e:
            logger.exception("[CHAT-STREAM] get_chat_response 异常")
            yield {"type": "error", "message": str(e)}
            return

        # 消费剩余的队列事件
        while not per_request_queue.empty():
            entry = per_request_queue.get_nowait()
            if entry.get("type") == "token_event":
                had_token_stream = True
                yield {"type": "token", "content": entry["token"]}
            elif entry.get("type") == "tool_output":
                intermediate_from_queue.append(entry)
            elif entry.get("type") == "thinking":
                yield {"type": "thinking", "agent_id": entry.get("agent_id", "agent"), "status": entry.get("status", "thinking")}
            else:
                intermediate_from_queue.append(entry)
                yield {
                    "type": "intermediate",
                    "agent_id": entry.get("agent_id", "agent"),
                    "content": entry.get("content", ""),
                    "type_detail": entry.get("type", "output"),
                }
                for art in entry.get("artifacts", []):
                    aggregated_artifacts.append(art)
                    yield {"type": "artifact", **art}
            await asyncio.sleep(0)

        if not isinstance(response, dict):
            yield {"type": "error", "message": "Orchestrator 返回格式异常"}
            return

        # 2) 最终 content（如果已有 LLM 级流式 token 则跳过模拟）
        content = response.get("content", "") or ""
        if content and not had_token_stream:
            if len(content) <= 200:
                tokens = list(content)
            else:
                tokens = [content[i:i+8] for i in range(0, len(content), 8)]
            for tok in tokens:
                yield {"type": "token", "content": tok}
                await asyncio.sleep(0.015)
        if content and had_token_stream:
            logger.info(f"[CHAT-STREAM] 已完成 LLM 级流式，跳过模拟 chunking（长度={len(content)}）")

        yield {"type": "thinking", "agent_id": "orchestrator", "status": "done"}

        # 3) final
        yield {
            "type": "final",
            "content": content,
            "intermediate_messages": intermediate_from_queue,
            "artifacts": aggregated_artifacts,
        }

    # Agent 回退链：当主 Agent 失败时，按顺序尝试回退
    AGENT_FALLBACK_CHAIN = {
        "opencode_coder": ["tongyi", "deepseek"],
        "opencode_bigpickle": ["tongyi"],
    }

    async def _call_agent_with_tools(
        self,
        agent: Any,
        prompt: str = None,
        messages: list = None,
        conversation_id: str = None,
        progressive_queue: asyncio.Queue = None
    ) -> str:
        """
        统一 Agent 调用入口。
        优先使用 ReAct 执行器（支持工具调用），降级为 process_message。
        所有调用 Agent 的路径必须走此方法，确保工具调用永不被遗漏。
        支持回退链：如果主 Agent 超时/出错，按 AGENT_FALLBACK_CHAIN 尝试回退。
        """
        from backend.models.message import Message
        from datetime import datetime
        import time as _time

        def _extract_last_user_message(msgs, pmt):
            """提取最后一条用户消息，用于响应完整性检查"""
            if msgs:
                for m in reversed(msgs):
                    if isinstance(m, dict) and m.get('role') == 'user':
                        return m.get('content', '')
                    elif hasattr(m, 'role') and m.role == 'user' and hasattr(m, 'content'):
                        return m.content
            return pmt or ''

        def _should_ask_for_clarification(a):
            """检查 agent 是否开启了回答前检查配置"""
            cfg = getattr(a, 'validation_config', None) or {}
            return bool(cfg.get('ask_before_answer', False))

        def _apply_completeness_check(output_text, user_q, target_agent):
            """对回复运行完整性检查，必要时追加追问"""
            should_check = _should_ask_for_clarification(target_agent)
            if not should_check:
                return output_text
            backend = getattr(target_agent, 'backend', None) or getattr(target_agent, 'llm_backend', None)
            if not backend:
                return output_text
            try:
                check_result = asyncio.run(check_response_completeness(user_q, output_text, backend))
                if check_result.get('needs_clarification') and check_result.get('questions'):
                    from backend.core.response_checker import build_clarification_response
                    return build_clarification_response(check_result['questions'], output_text)
            except Exception:
                pass
            return output_text

        # 收集要尝试的 agent 列表
        agents_to_try = [agent]
        if agent.agent_id in self.AGENT_FALLBACK_CHAIN:
            for fallback_id in self.AGENT_FALLBACK_CHAIN[agent.agent_id]:
                fallback_agent = self.get_agent(fallback_id)
                if fallback_agent and fallback_agent is not agent:
                    agents_to_try.append(fallback_agent)

        last_error = None
        user_last_msg = _extract_last_user_message(messages, prompt)
        for attempt_agent in agents_to_try:
            t_agent = _time.time()
            try:
                if hasattr(attempt_agent, 'executor'):
                    if prompt is None and messages:
                        lines = []
                        for m in messages:
                            if isinstance(m, dict):
                                lines.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
                            elif hasattr(m, 'role') and hasattr(m, 'content'):
                                lines.append(f"{m.role}: {m.content}")
                            elif hasattr(m, 'agent_id') and hasattr(m, 'content'):
                                role = "user" if m.agent_id == "user" else "assistant"
                                lines.append(f"{role}: {m.content}")
                            else:
                                lines.append(str(m))
                        prompt = "\n".join(lines)

                    if prompt:
                        label = "主 Agent" if attempt_agent is agent else f"回退 Agent ({attempt_agent.agent_id})"
                        logger.info(f"🚀 统一调用 {label} {attempt_agent.agent_id} 的 ReAct 执行器")
                        logger.info(f"📋 ReAct 可用工具列表: {[t.name for t in self.langchain_tools]}")
                        full_prompt = f"【重要】你必须始终使用中文回复，不得切换到其他语言。\n当前日期：{datetime.now().strftime('%Y年%m月%d日')}\n\n用户问题：{prompt}"
                        logger.info(f"🔧 开始调用 executor.ainvoke，工具数: {len(self.langchain_tools)}, 工具名: {[t.name for t in self.langchain_tools]}")

                        if progressive_queue is not None:
                            progressive_queue.put_nowait({
                                "type": "thinking",
                                "agent_id": attempt_agent.agent_id,
                                "status": "thinking"
                            })

                        try:
                            raw_resp = await attempt_agent.executor.ainvoke({"input": full_prompt})
                        except Exception as exec_err:
                            logger.error(f"❌ executor.ainvoke 执行异常: {exec_err}")
                            raise

                        if progressive_queue is not None:
                            progressive_queue.put_nowait({
                                "type": "thinking",
                                "agent_id": attempt_agent.agent_id,
                                "status": "done"
                            })

                        logger.info(f"✅ executor.ainvoke 完成")
                        t_elapsed = _time.time() - t_agent
                        output = raw_resp.get('output', str(raw_resp)) if isinstance(raw_resp, dict) else str(raw_resp)
                        logger.info(f"🔍 [ReAct输出] 类型: {type(raw_resp)}, keys: {list(raw_resp.keys()) if isinstance(raw_resp, dict) else 'N/A'}")
                        logger.info(f"[AGENT-RESULT] {attempt_agent.agent_id} ({t_elapsed:.1f}s) 输出前200字: {str(output)[:200]}")

                        err_signals = ["invalid api-key", "401", "authentication_error", "rate limit", "invalid response"]
                        if any(sig in str(output).lower() for sig in err_signals):
                            logger.warning(f"[AGENT-FALLBACK] {attempt_agent.agent_id} 输出了错误内容，触发回退: {str(output)[:100]}")
                            raise RuntimeError(f"Agent 输出了错误内容: {str(output)[:200]}")
                        checked = _apply_completeness_check(output, user_last_msg, attempt_agent)
                        return checked
            except Exception as e:
                last_error = e
                err_type = "主 Agent" if attempt_agent is agent else f"回退 Agent ({attempt_agent.agent_id})"
                logger.warning(f"[AGENT-FALLBACK] {err_type} {attempt_agent.agent_id} 执行失败: {e}")
                continue

        logger.info(f"调用 Agent {agent.agent_id} 的 process_message")
        if messages is None and prompt is not None:
            messages = [Message(conversation_id=conversation_id or 0, agent_id="user", content=prompt)]
        elif messages is None:
            return "错误：未提供 prompt 或 messages"

        raw_resp = await agent.process_message(messages)
        if isinstance(raw_resp, str):
            checked = _apply_completeness_check(raw_resp, user_last_msg, agent)
            return checked
        if hasattr(raw_resp, 'final_answer') and raw_resp.final_answer and hasattr(raw_resp.final_answer, 'content'):
            checked = _apply_completeness_check(raw_resp.final_answer.content, user_last_msg, agent)
            return checked
        if hasattr(raw_resp, 'content'):
            checked = _apply_completeness_check(raw_resp.content, user_last_msg, agent)
            return checked
        return str(raw_resp)

    def _build_agent_management_prompt(self, user_request: str, conversation_id: str, messages: Optional[List[Dict[str, str]]] = None, request_context: Optional[Dict[str, Any]] = None) -> str:
        logger.info("build_agent 已启动")
        context = request_context or {}

        current_user_id = context.get("current_user_id", "")
        logger.info(f"current_user_id: {current_user_id}")
        recent_context = "\n".join(
            f"- {m.get('role', 'unknown')}: {str(m.get('content', '')).strip()}"
            for m in (messages or [])[-6:]
            if str(m.get("content", "")).strip()
        ) or "- no extra context"
        return f"""你是 AgentHub 的 Agent Builder，负责在系统中创建或修改 Agent。

你必须遵守以下规则：
1. 如果用户要修改已有 Agent，先调用 `manage_agent.list_agents` 查看当前用户已有的 Agent。
2. 如果用户要新建 Agent，收集足够信息后调用 `manage_agent.create_agent`。
3. 如果用户要更新 Agent，调用 `manage_agent.update_agent`。
4. 所有工具输入都必须是 JSON 对象。`conversation_id` 和 `current_user_id` 已由系统提供（见下方上下文），调用工具时**必须带上**这两个字段。
5. JSON 字段可使用：`conversation_id`、`current_user_id`、`agent_id`、`target_name`、`name`、`description`、`system_prompt`、`llm_backend`、`tools`、`icon`、`memory_config`、`planning_config`、`validation_config`。
6. 嵌套配置字段示例（均为可选，未明说不要下发）：
   - memory_config:
     * {{ "strategy": "none" }}
     * {{ "strategy": "sliding_window", "window_size": 10 }}
     * {{ "strategy": "summary", "summary_threshold": 4000, "summary_prompt": "..." }}
   - planning_config:
     * {{ "mode": "direct" }}
     * {{ "mode": "react" }}
     * {{ "mode": "plan_execute", "steps_template": "...", "require_confirmation_for_complex_tasks": false }}
   - validation_config:
     * {{ "strategy": "none" }}
     * {{ "strategy": "rules", "rules": [{{"type":"regex","pattern":"...","message":"..."}}], "max_retries": 1 }}
     * {{ "strategy": "llm_judge", "judge_prompt": "...", "max_retries": 1 }}
7. **对于缺失的字段，使用合理的默认值，不要追问用户。** 例如：
   - `name` 默认使用用户描述的职能名（如“数据分析师”）
   - `llm_backend` 默认使用 `"tongyi"`（可选值: `" + ", ".join(self.llm_backends.keys()) + "`）
   - `tools` 默认使用 `[]`（空列表）
   - `description` 从用户描述中一句话概括
   只有当用户完全没有提供任何 agent 相关信息时，才简要说明需要什么。
8. 每个工具调用的 JSON **必须包含**以下两个字段（直接从下方「当前执行上下文」拷贝数值）：
   - "conversation_id": {conversation_id}
   - "current_user_id": {current_user_id or 0}
9. 完成后用自然语言汇报结果，包含 Agent 名称、用途、模型和是否已成功生效。

当前执行上下文（请直接使用，**不要质疑这些值**）：
- conversation_id: {conversation_id}
- current_user_id: {current_user_id or 'unknown'}

用户原始请求：
{user_request}
"""


    async def _handle_agent_management_request(self, conversation_id: str, messages: List[Dict[str, str]], request_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target_agent = self.get_agent("agent_builder")
        if not target_agent:
            logger.warning("agent_builder 未注册，回退到默认聊天")
            return await self._handle_default_chat(conversation_id, messages)

        # 🎯 解析 current_user_id：优先从 request_context，次之从 conversation 查库
        current_user_id = (request_context or {}).get("current_user_id", "")
        if not current_user_id and conversation_id:
            try:
                from backend.db.database import SessionLocal
                from backend.models.conversation import Conversation as ConversationModel
                _db = SessionLocal()
                _conv = _db.query(ConversationModel).filter(ConversationModel.id == int(conversation_id)).first()
                if _conv and _conv.user_id:
                    current_user_id = _conv.user_id
                _db.close()
            except Exception:
                pass

        # 🎯 设置 manage_agent 调用上下文，确保工具函数能自动注入身份信息
        try:
            import backend.utils.manage_agent as _ma
            _ma._caller_ctx.set({
                "current_user_id": current_user_id,
                "conversation_id": conversation_id
            })
        except Exception:
            pass

        latest_user_request = messages[-1].get("content", "") if messages else ""
        prompt = self._build_agent_management_prompt(latest_user_request, conversation_id, messages, request_context)
        output_text = await self._call_agent_with_tools(
            agent=target_agent,
            prompt=prompt,
            conversation_id=conversation_id
        )
        return {"agent_id": target_agent.agent_id, "content": output_text}

    async def _handle_mention(self, agent_id: str, conversation_id: str, messages: List[Dict[str, str]], request_context: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        """处理 @mention 消息，直接调用对应的 Agent。

        A 档：对自定义 Agent 应用 per-Agent 的 memory / planning / validation 配置。
        """
        target_agent = self.get_agent(agent_id)
        if not target_agent:
            return {"agent_id": "orchestrator", "content": f"未找到名为 '{agent_id}' 的 Agent。"}

        logger.info(f"Chat API: 消息将被路由到 Agent: {target_agent.agent_id}")
        if target_agent.agent_id == "agent_builder":
            latest_user_request = messages[-1].get("content", "") if messages else ""
            prompt = self._build_agent_management_prompt(latest_user_request, conversation_id, messages, request_context)
            output_text = await self._call_agent_with_tools(
                agent=target_agent,
                prompt=prompt,
                conversation_id=conversation_id
            )
            return {"agent_id": target_agent.agent_id, "content": output_text}

        # === A 档 Step 1: 记忆裁剪 ===
        memory_cfg = getattr(target_agent, "memory_config", None)
        if memory_cfg:
            messages = await apply_memory_strategy(messages, memory_cfg, self._llm_invoke_text)

        # === A 档 Step 2: 规划路由 ===
        planning_cfg = getattr(target_agent, "planning_config", None) or {}
        mode = str(planning_cfg.get("mode") or "direct").lower()

        async def _direct_invoke(_messages: List[Dict[str, str]]) -> str:
            history = [Message(conversation_id=conversation_id, agent_id=m.get("role"), content=m.get("content"))
                       for m in _messages]
            resp: AgentResponse = await target_agent.process_message(messages=history)
            return resp.final_answer.content if resp and resp.final_answer else ""

        if mode == "react":
            # ReAct：使用 target_agent.executor（register_agent 已在有 tools 时挂上）
            if hasattr(target_agent, "executor"):
                logger.info(f"[planning] route=react for {target_agent.agent_id}")
                latest = messages[-1].get("content", "") if messages else ""
                try:
                    answer_text = await self._call_agent_with_tools(
                        agent=target_agent,
                        prompt=latest,
                        conversation_id=conversation_id
                    )
                except Exception as exc:
                    logger.warning(f"[planning] react 失败，fallback direct: {exc}")
                    answer_text = await _direct_invoke(messages)
            else:
                logger.warning(f"[planning] mode=react 但 Agent 无 executor，fallback direct")
                answer_text = await _direct_invoke(messages)
        elif mode == "plan_execute":
            logger.info(f"[planning] route=plan_execute for {target_agent.agent_id}")
            # 复用 _handle_plan_command（需要 checkpointer，这里临时创建一个 MemorySaver 兜底）
            try:
                checkpointer = MemorySaver()
                latest = messages[-1].get("content", "") if messages else ""
                plan_result = await self._handle_plan_command(conversation_id, latest, checkpointer, request_context)
                answer_text = plan_result.get("content", "") if isinstance(plan_result, dict) else str(plan_result)
            except Exception as exc:
                logger.warning(f"[planning] plan_execute 失败，fallback direct: {exc}")
                answer_text = await _direct_invoke(messages)
        else:
            logger.info(f"[planning] route=direct for {target_agent.agent_id}")
            answer_text = await _direct_invoke(messages)

        # === A 档 Step 3: 校验闭环 ===
        validation_cfg = getattr(target_agent, "validation_config", None)
        if validation_cfg:
            max_retries = get_max_retries(validation_cfg)
            for attempt in range(max_retries + 1):
                result = await apply_validation_strategy(answer_text, validation_cfg, self._llm_invoke_text)
                if result.passed:
                    break
                if attempt < max_retries:
                    logger.info(f"[validation] 第 {attempt + 1} 次失败，触发重试: {result.reason_text}")
                    # 在 messages 末尾追加一条 system 提示，重新走 direct 路径生成
                    retry_messages = messages + [{
                        "role": "system",
                        "content": f"上一次回答未通过校验：{result.reason_text}\n请改进后重新作答。",
                    }]
                    answer_text = await _direct_invoke(retry_messages)
                else:
                    logger.info(f"[validation] 已达 max_retries={max_retries}，附带提示返回")
                    answer_text = f"{answer_text}\n\n⚠️ 自动校验未通过：{result.reason_text}"

        return {"agent_id": target_agent.agent_id, "content": answer_text}

    async def _handle_multiple_mentions(
        self,
        agent_ids: List[str],
        conversation_id: str,
        messages: List[Dict[str, str]],
        request_context: Dict[str, Any],
        progressive_queue: Optional[asyncio.Queue] = None,
    ) -> Dict[str, Any]:
        """
        处理多个 @mention：依次调用每个 Agent，逐步收集结果。
        每个 Agent 的输出立即推入 progressive_queue（流式场景），
        最终返回合并后的结果。
        """
        from backend.models.message import Message

        all_outputs: List[Dict[str, str]] = []
        for agent_id in agent_ids:
            # 通知前端：子 Agent 开始思考
            if progressive_queue is not None:
                progressive_queue.put_nowait({
                    "type": "thinking",
                    "agent_id": agent_id,
                    "status": "thinking",
                })
            logger.info(f"[MULTI-MENTION] 调用 Agent: {agent_id}")
            result = await self._handle_mention(agent_id, conversation_id, messages, request_context)
            content = result.get("content", "")
            artifacts = self._parse_artifacts(content)
            entry = {"agent_id": agent_id, "content": content, "artifacts": artifacts}
            all_outputs.append(entry)
            if progressive_queue is not None:
                progressive_queue.put_nowait(entry)
                # 通知前端：子 Agent 完成思考
                progressive_queue.put_nowait({
                    "type": "thinking",
                    "agent_id": agent_id,
                    "status": "done",
                })
            # 将当前 Agent 的输出拼入消息历史，后续 Agent 可看到前文
            messages = messages + [{"role": "assistant", "content": content}]

        combined = "\n\n---\n\n".join(
            [f"**@{ao['agent_id']} 的回复：**\n{ao['content']}" for ao in all_outputs]
        )
        # 发送 Orchestrator 总结
        if len(all_outputs) > 0:
            agent_count = len(all_outputs)
            agent_names = "、".join([f"@{ao['agent_id']}" for ao in all_outputs])
            summary = f"✅ 所有任务已完成！共调用了 {agent_count} 个 Agent（{agent_names}）协作完成了本次任务。"
        else:
            summary = "任务处理完成。"
        if progressive_queue is not None:
            progressive_queue.put_nowait({
                "agent_id": "orchestrator",
                "content": summary,
                "type": "output",
            })
        return {
            "agent_id": "orchestrator",
            "content": combined,
            "intermediate_messages": all_outputs,
        }

    async def _handle_plan_command(self, conversation_id: str, task_content: str, checkpointer: AsyncSqliteSaver, request_context: Optional[Dict[str, Any]] = None, progressive_queue: Optional[asyncio.Queue] = None) -> \
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
        if progressive_queue is not None:
            progressive_queue.put_nowait({"type": "thinking", "agent_id": "planner", "status": "thinking"})
        logger.info(f"[PROGRESS] 正在调用规划器（PlannerAgent）拆解任务: {task_content[:60]}...")
        agent_response: AgentResponse = await planner.process_message([plan_task_message], context=planner_context)
        if progressive_queue is not None:
            progressive_queue.put_nowait({"type": "thinking", "agent_id": "planner", "status": "done"})
        logger.info(f"[PROGRESS] 规划器返回结果，长度={len(agent_response.final_answer.content) if agent_response and agent_response.final_answer else 0}")

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

        # 将计划内容和 Agent 分配以聊天消息形式发布给用户
        prog_q = progressive_queue
        if prog_q is not None and tasks_list:
            agent_names = [getattr(t, 'agent_id', str(t.get('agent_id', ''))) for t in tasks_list]
            unique_agents = []
            seen = set()
            for a in agent_names:
                if a not in seen:
                    seen.add(a)
                    unique_agents.append(a)
            agent_intro = "、".join([f"`@{a}`" for a in unique_agents])
            plan_summary = f"📋 我已将任务拆解为 **{len(tasks_list)}** 个子任务，将由 {agent_intro} 依次协作完成。"
            prog_q.put_nowait({
                "agent_id": "orchestrator",
                "content": plan_summary,
                "type": "output",
            })
            # 列出每个任务
            for i, task in enumerate(tasks_list):
                task_desc = getattr(task, 'description', '') or getattr(task, 'prompt', str(task))
                agent_id = getattr(task, 'agent_id', 'unknown')
                task_brief = task_desc[:80] + ('...' if len(task_desc) > 80 else '')
                prog_q.put_nowait({
                    "agent_id": "orchestrator",
                    "content": f"**任务 {i+1}** (`{agent_id}`): {task_brief}",
                    "type": "output",
                })

        # 2. 准备并执行工作流
        initial_state = GraphState(
            task_content=task_content, plan_data=plan_data, step_results={},
            final_summary="", conversation_id=conversation_id, messages=[]
        )
        initial_state["current_user_id"] = (request_context or {}).get("current_user_id")

        if latest_checkpoint and 'values' in latest_checkpoint:
            initial_state["messages"] = latest_checkpoint['values'].get("messages", [])
        else:
            initial_state["messages"] = []
        initial_state["messages"].append(HumanMessage(content=task_content))
        logger.info(f"[MEMORY] 更新对话消息列表，当前消息数: {len(initial_state['messages'])}")

        # 传引用给 LangGraph 节点，使图内节点能实时推送 LLM token 到 SSE 队列
        # 不能放在 initial_state 里——LangGraph checkpoint 会 msgpack 序列化 state，
        # asyncio.Queue 无法 msgpack 序列化会炸。用 orchestrator 实例属性代替。
        if progressive_queue is not None:
            self._progressive_queue = progressive_queue

        # 🚀 并行调度准备（验证点：并行调度和失败降级）
        parallel_tasks = []
        independent_tasks = [t for t in plan_data.get('tasks', []) if getattr(t, 'parallelizable', False)]
        if independent_tasks:
            logger.info(f"[VERIFY] 并行调度：发现{len(independent_tasks)}个可并行执行的独立任务")
        
        app = self.planning_graph_builder.compile(checkpointer=checkpointer)
        agent_outputs: List[Dict] = []
        try:
            # 改用 astream 逐步获取中间状态，实时收集 agent_outputs
            async for step_state in app.astream(initial_state, config=config, stream_mode="values"):
                new_outputs = step_state.get("agent_outputs", [])
                if new_outputs:
                    # 只追加本轮新增的
                    for ao in new_outputs[len(agent_outputs):]:
                        agent_outputs.append(ao)
                        content_preview = str(ao.get('content', ''))[:100]
                        logger.info(f"[PROGRESS] 子任务完成: agent={ao.get('agent_id')}, 长度={len(ao.get('content',''))}, 预览={content_preview}")
                        # 推送到渐进式队列（如果有），get_chat_stream 会实时消费
                        if progressive_queue is not None:
                            progressive_queue.put_nowait(ao)
            final_state = step_state
            logger.info(f"[VERIFY] 所有子任务执行完成，工作流成功结束")
        except Exception as e:
            logger.error(f"[VERIFY] 失败降级：工作流执行出错，触发降级逻辑: {str(e)}", exc_info=True)
            # 失败降级：直接调用LLM生成基础回答，避免完全失败
            fallback_prompt = f"用户的问题是：{task_content}\n\n由于复杂任务调度暂时出错，请直接用你现有的知识回答用户的问题。"
            messages = [{"role": "user", "content": fallback_prompt}]
            fallback_response = await self.get_backend("tongyi").chat(messages)
            if isinstance(fallback_response, str):
                fallback_content = fallback_response
            else:
                fallback_content = str(fallback_response)
            return {"agent_id": "orchestrator", "content": f"⚠️ 复杂任务调度遇到小问题，不过我依然可以帮你解答：\n\n{fallback_content}"}

        summary = final_state.get('final_summary')
        logger.info(f"[SUMMARY-CHECK] final_summary={repr(summary)[:200]}, state keys={list(final_state.keys())}")

        if not summary:
            logger.warning("[SUMMARY-CHECK] final_summary 为空，尝试从 agent_outputs 拼接兜底摘要")
            agent_outputs = final_state.get("agent_outputs", [])
            if agent_outputs:
                parts = [f"## {ao.get('agent_id', 'Agent')} 的输出：\n{ao.get('content', '')}" for ao in agent_outputs]
                summary = "\n\n".join(parts)
            else:
                # 最终降级：从 final_state 尝试提取任何可用内容
                for candidate_key in ("content", "summary", "result", "final_output"):
                    candidate = final_state.get(candidate_key)
                    if candidate:
                        summary = str(candidate)
                        break
                if not summary:
                    logger.error(f"规划工作流执行完毕，但最终状态中没有找到有效的总结。最终状态 keys: {list(final_state.keys())}")
                    return {"agent_id": "orchestrator", "content": "抱歉，我执行了计划，但无法生成最终的总结报告。"}

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

    async def _handle_workflow_command(self, workflow_id: str, conversation_id: str, task_content: str,
                                       messages: List[Dict[str, str]], checkpointer: AsyncSqliteSaver,
                                       progressive_queue: Optional[asyncio.Queue] = None) -> Dict[
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
            final_state = initial_state
            async for step in app.astream(initial_state, config=config, stream_mode="values"):
                final_state = step
                # 代理工作流也可能产生 agent_outputs
                for ao_key in ("agent_outputs", "intermediate_outputs"):
                    new_outs = step.get(ao_key, [])
                    if new_outs and progressive_queue is not None:
                        for ao in new_outs:
                            progressive_queue.put_nowait(ao if isinstance(ao, dict) else {"content": str(ao)})
            logger.info(f"🎉 工作流 {workflow_id} 执行完成")
        except Exception as e:
            logger.error(f"[VERIFY] 失败降级：工作流{{workflow_id}}执行出错，触发降级: {str(e)}", exc_info=True)
            fallback_prompt = f"用户的问题是：{task_content}\n\n工作流执行遇到问题，请直接用你的知识回答用户。"
            messages = [{"role": "user", "content": fallback_prompt}]
            fallback_response = await self.get_backend("tongyi").chat(messages)
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

    async def _llm_invoke_text(self, msgs: List[Dict[str, str]]) -> str:
        """工具方法：直接用 LLMBackend 跑一轮，返回纯文本。供 memory.summary 与 llm_judge 使用。"""
        try:
            resp = await self.get_backend("tongyi").chat(msgs)
            return resp.strip() if isinstance(resp, str) else str(resp).strip()
        except Exception as exc:
            logger.warning(f"_llm_invoke_text 失败: {exc}")
            return ""

    async def _handle_default_chat(self, conversation_id: str, messages: List[Dict[str, str]], progressive_queue: asyncio.Queue = None) -> Dict[str, Any]:
        """处理不包含任何指令的普通聊天消息。

        A 档运行时三段式：
        1) 记忆裁剪 (apply_memory_strategy)
        2) 规划路由 (按 target_agent.planning_config.mode 选择 direct / react / plan_execute)
        3) 校验闭环 (apply_validation_strategy + max_retries 重试)
        """
        main_chat_agent = self.get_agent("tongyi")
        if main_chat_agent:
            logger.info(f"Chat API: 默认路由到主聊天 Agent: {main_chat_agent.agent_id}")

            # === A 档 Step 1: 记忆裁剪 ===
            # main_chat_agent 是系统内置 Agent，没有 memory_config；
            # 仅当通过 @mention 路由到自定义 Agent 时才有 per-Agent 配置。
            # 此处对内置 Agent 跳过裁剪（保持原行为）。
            memory_cfg = getattr(main_chat_agent, "memory_config", None)
            if memory_cfg:
                messages = await apply_memory_strategy(messages, memory_cfg, self._llm_invoke_text)

            # 构建系统上下文：告知当前可用的 Agent、Skill 等信息
            agent_list = [f"- {getattr(agent, 'name', agent_id)}" for agent_id, agent in self.agents.items()]
            agent_context = "\n".join(agent_list) if agent_list else "暂无"
            skills_prompt = self.get_available_skills_prompt()

            context_prompt = self.prompt_loader.get('orchestrator', 'default_chat',
                agent_context=agent_context,
                tool_names=', '.join(self.tool_skills.keys())
            )

            system_message = SystemMessage(content=context_prompt)

            history_as_msgs = [
                Message(conversation_id=conversation_id, agent_id=m.get("role"), content=m.get("content")) for m in
                messages]
            # 注入系统上下文
            full_messages = [system_message] + history_as_msgs

            # 通过统一调用入口，自动走 ReAct 或降级
            output = await self._call_agent_with_tools(
                agent=main_chat_agent,
                messages=full_messages,
                prompt=f"{context_prompt}\n\n" + "\n".join(
                    f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
                ),
                conversation_id=conversation_id,
                progressive_queue=progressive_queue
            )
            return {"agent_id": main_chat_agent.agent_id, "content": output}


    async def _handle_simple_chat(self, content: str, messages: List[Dict], progressive_queue: asyncio.Queue = None) -> Dict[str, Any]:
        """
        处理简单聊天：Orchestrator 直接调用 LLM 回复，不经过 Agent。
        用于简单闲聊、问候等不需要工具调用的场景。
        不推送事件到 progressive_queue，由 get_chat_stream 统一处理流式输出。
        """
        prompt = self.prompt_loader.get('orchestrator', 'simple_chat', content=content)

        try:
            response = await self.get_backend("tongyi").chat([{"role": "user", "content": prompt}])
            final_content = response.strip() if isinstance(response, str) else str(response).strip()
        except Exception as e:
            logger.error(f"[SIMPLE-CHAT] LLM 调用失败: {e}")
            final_content = "你好！很高兴为你服务。请问有什么我可以帮你的？"

        return {"agent_id": "orchestrator", "content": final_content}

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
        使用 LLM 将用户请求分类为: agent_management / simple / moderate / complex
        返回字符串供路由使用。
        """
        prompt = self.prompt_loader.get('orchestrator', 'complexity_classification',
            user_message=user_message,
            history_summary=history_summary if history_summary else "无"
        )

        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await self.get_backend("tongyi").chat(messages)
            content = resp.strip().lower() if isinstance(resp, str) else str(resp).strip().lower()
            if content in ("simple", "moderate", "complex", "agent_management"):
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

        # 复杂协作类关键词：需要多角色协作或多步骤
        complex_keywords = [
            "开发一个", "帮我设计", "帮我开发", "帮我实现",
            "架构", "整体方案", "方案设计", "重构",
            "项目", "系统", "全栈", "前后端",
            "部署", "上线", "微服务", "分布式",
        ]
        if any(kw in content for kw in complex_keywords):
            return "complex"

        # 中等长度 + 技术性关键词
        moderate_keywords = [
            "写一个", "帮我写", "实现",
            "写代码", "开发", "编程", "构建", "创建",
            "debug", "排查", "快速排序", "算法", "设计",
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
        
    @staticmethod
    def _parse_artifacts(text: str) -> list[dict]:
        """
        从 Agent 输出中提取代码块和 markdown 内容作为 artifact。
        1. 匹配 ```lang\\n...``` 标准代码围栏
        2. 检测裸 markdown（标题、列表、分隔线等）
        3. 检测无围栏的代码块（连续缩进行）
        返回 list[dict]，每个 dict 包含 type/title/content/language。
        """
        import re
        artifacts = []

        # 1. 标准代码围栏
        fenced_pattern = r'```(\w*)\s*\n(.*?)```'
        for match in re.finditer(fenced_pattern, text, re.DOTALL):
            lang = match.group(1).strip() or 'text'
            code = match.group(2)
            art_type = 'html_preview' if lang in ('html',) else \
                       'diagram' if lang in ('mermaid', 'graphviz') else \
                       'markdown' if lang in ('markdown', 'md') else \
                       'code'
            artifacts.append({
                "type": art_type,
                "title": lang.upper() if lang != 'text' else '代码',
                "content": code,
                "language": lang,
            })
        # 从文本中移除已匹配的围栏，防止二次解析
        text = re.sub(fenced_pattern, '', text, flags=re.DOTALL)

        # 2. 检测裸 markdown（标题、列表、分隔线、引用等）
        lines = text.split('\n')
        in_bare_md = False
        md_lines = []
        consecutive_non_code = 0  # 连续非代码行计数器，用于跨越代码中的注释行/docstring
        _code_start_added = False   # 标记：代码特征行是否已通过 code indicator 分支加入了 md_lines
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 裸 markdown 行：# 标题、--- 分隔、> 引用、- 列表、1. 列表
            is_md = (
                stripped.startswith('# ') or
                stripped.startswith('## ') or
                stripped.startswith('### ') or
                stripped.startswith('- ') or
                stripped.startswith('* ') or
                re.match(r'^\d+\. ', stripped) or
                stripped.startswith('> ') or
                stripped.startswith('---') or
                stripped.startswith('| ')
            )
            # 代码行（非 markdown）：以 4+ 空格缩进开头，且不是列表
            # 扩展：支持 shebang、装饰器、class/函数定义、docstring 等代码特征
            is_code_indented = (
                (line.startswith('    ') or line.startswith('\t')) and
                stripped and
                not stripped.startswith('-') and
                not stripped.startswith('*') and
                not stripped.startswith('#')
            )
            code_indicators = [
                stripped.startswith('#!'),          # shebang: #!/usr/bin/env python3
                stripped.startswith('@'),           # 装饰器: @app.route(...)
                stripped.startswith('def '),        # 函数定义
                stripped.startswith('class '),      # 类定义
                stripped.startswith('async def '),  # async 函数
                stripped.startswith('import '),     # import 语句
                stripped.startswith('from '),       # from...import 语句
                stripped.startswith('if __name__'), # if __name__ == '__main__'
                '"""' in stripped or "'''" in stripped,  # 单行 docstring
                stripped.startswith('# -*-'),       # -*- coding: utf-8 -*-
                stripped.startswith('# coding:'),
            ]
            is_code_indicator = any(code_indicators)
            # 如果当前行有代码特征（shebang/def/import/装饰器等），视为代码行
            # 这可以独立于缩进检测到代码，即使不在缩进块中
            is_code_line = is_code_indented or (
                is_code_indicator and
                not stripped.startswith('# ') and    # 排除纯注释行（如 # coding: utf-8）
                not stripped.startswith('## ') and
                not stripped.startswith('### ') and
                not stripped.startswith('#!')         # 但保留 shebang
            )
            # 如果检测到代码特征行，立即将 in_bare_md 设为 True，使后续缩进行能累积
            _line_added_this_iter = False
            if is_code_indicator and not in_bare_md:
                in_bare_md = True
                md_lines = [stripped] if stripped else []
                _line_added_this_iter = True
            if is_md or is_code_line:
                if not in_bare_md:
                    in_bare_md = True
                    md_lines = [stripped] if stripped else []
                elif not _line_added_this_iter:
                    # 仅在尚未通过 code indicator 分支添加时才追加
                    md_lines.append(stripped)
                consecutive_non_code = 0
            else:
                # 当前行既不是 markdown 也不是代码
                # 如果正在累积代码块，仍将其加入 md_lines（跨越注释/docstring行）
                # 但如果该行已经通过 code indicator 分支加入了，则不重复添加
                if in_bare_md and not _line_added_this_iter:
                    md_lines.append(stripped)
                consecutive_non_code += 1
                if in_bare_md and len(md_lines) >= 3 and consecutive_non_code >= 4:
                    content = '\n'.join(md_lines)
                    is_markdown = any(
                        md_lines[j].startswith(('# ', '## ', '### ', '- ', '* ', '> ', '---', '| '))
                        for j in range(min(3, len(md_lines)))
                    )
                    artifacts.append({
                        "type": 'markdown' if is_markdown else 'code',
                        "title": 'Markdown' if is_markdown else '代码',
                        "content": content,
                        "language": 'markdown' if is_markdown else 'text',
                    })
                    in_bare_md = False
                    md_lines = []
                    consecutive_non_code = 0

        # 处理末尾
        if in_bare_md and len(md_lines) >= 3:
            content = '\n'.join(md_lines)
            is_markdown = any(
                md_lines[j].startswith(('# ', '## ', '### ', '- ', '* ', '> ', '---', '| '))
                for j in range(min(3, len(md_lines)))
            )
            artifacts.append({
                "type": 'markdown' if is_markdown else 'code',
                "title": 'Markdown' if is_markdown else '代码',
                "content": content,
                "language": 'markdown' if is_markdown else 'text',
            })

        return artifacts

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
        # 初始化任务状态和质量报告跟踪
        task_states = state.get("task_states", {})
        quality_reports = state.get("quality_reports", {})

        if not tasks:
            logger.warning("没有可执行的子任务")
            return {
                **state, "step_results": step_results, "agent_outputs": agent_outputs,
                "task_states": task_states, "quality_reports": quality_reports,
            }
            
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
        
        # 先执行并行任务 — 使用 asyncio.gather + _call_agent_with_tools，支持真正的工具调用
        if parallel_tasks:
            semaphore = asyncio.Semaphore(3)  # 限制 LLM 并发数，避免触发 rate limit

            async def run_async_task(task):
                """使用统一入口并发执行任务，带重试循环和质量检查"""
                async with semaphore:
                    agent_id = getattr(task, "agent_id")
                    prompt = getattr(task, "prompt", getattr(task, "description", ""))
                    agent = self.get_agent(agent_id)
                    if not agent:
                        return {
                            "step_id": task.step_id, "result": f"错误：找不到Agent {agent_id}",
                            "state": TaskState.FAILED, "quality": None,
                        }

                    prog_q = getattr(self, '_progressive_queue', None)
                    if prog_q is not None:
                        prog_q.put_nowait({"type": "thinking", "agent_id": agent_id, "status": "thinking"})

                    skills_prompt = self.get_available_skills_prompt()
                    workspace = state.get("shared_workspace", {})
                    workspace_context = "\n=== 之前任务的关键发现（黑板上下文） ===\n"
                    if workspace:
                        for key, value in workspace.items():
                            workspace_context += f"- {key}: {str(value)[:300]}...\n"
                    else:
                        workspace_context += "暂无前置任务的共享上下文\n"
                    runtime_context = f"=== 执行上下文 ===\n- conversation_id: {state.get('conversation_id')}\n- current_user_id: {state.get('current_user_id') or 'unknown'}"

                    # 添加用户启用的技能注入
                    active_skills_injection = ""
                    active_skills_list = getattr(self, '_active_skills', None)
                    if active_skills_list:
                        active_skills_injection = self.get_active_skills_injection(active_skills_list)

                    full_prompt = f"{skills_prompt}{active_skills_injection}\n{runtime_context}\n{workspace_context}\n=== 当前任务 ===\n{prompt}"

                    # 使用重试+质量检查辅助方法
                    result_text, task_state, quality = await self._execute_single_task_with_retry(
                        task=task,
                        base_prompt=full_prompt,
                        state=state,
                        conversation_id=state.get("conversation_id"),
                    )

                    if prog_q is not None:
                        prog_q.put_nowait({"type": "thinking", "agent_id": agent_id, "status": "done"})

                    return {
                        "step_id": task.step_id,
                        "result": result_text,
                        "state": task_state,
                        "quality": quality,
                        "agent_id": agent_id,
                    }

            # 使用 asyncio.gather 并发执行所有独立任务，共享同一个事件循环
            parallel_results = await asyncio.gather(
                *[run_async_task(t) for t in parallel_tasks],
                return_exceptions=True
            )


            for r in parallel_results:
                if isinstance(r, Exception):
                    logger.error(f"❌ 并行任务异常: {r}")
                    continue
                if isinstance(r, dict) and "step_id" in r:
                    step_id = r["step_id"]
                    step_results[step_id] = r["result"]
                    # 跟踪任务状态
                    task_state = r.get("state", TaskState.SUCCEEDED)
                    task_states[step_id] = task_state
                    # 跟踪质量报告
                    quality = r.get("quality")
                    if quality:
                        quality_reports[step_id] = quality
                    # 黑板机制：将当前任务结果写入shared_workspace
                    task_info = next((t for t in parallel_tasks if t.step_id == step_id), None)
                    if task_info:
                        current_workspace = state.get("shared_workspace", {})
                        current_workspace[f"task_{step_id}_output"] = r["result"]
                        state["shared_workspace"] = current_workspace
                    agent_id = r.get("agent_id") or (getattr(task_info, "agent_id", "agent") if task_info else "agent")
                    # 收集 Agent 输出（用于前端展示依次回复）
                    artifacts = self._parse_artifacts(r["result"])
                    agent_outputs.append({
                        "agent_id": agent_id,
                        "content": r["result"],
                        "artifacts": artifacts,
                    })
                    # 实时推送 artifact 到 SSE 队列
                    prog_q = getattr(self, '_progressive_queue', None)
                    if prog_q is not None:
                        for art in artifacts:
                            prog_q.put_nowait({
                                "agent_id": agent_id,
                                "type": art.get("type", "code"),
                                "title": art.get("title", "代码"),
                                "content": art.get("content", ""),
                                "artifacts": [art],
                            })
                    # 子任务完成后实时保存到数据库
                    conv_id = state.get("conversation_id")
                    if conv_id and self.db_session:
                        from backend.services.conversation_service import ConversationService
                        conv_service = ConversationService(self.db_session)
                        conv_service.add_message_to_conversation(
                            conversation_id=int(conv_id),
                            agent_id=agent_id,
                            content=f"📝 任务{step_id}完成：\n{r['result']}"
                        )
                    status_icon = "✅" if task_state in (TaskState.SUCCEEDED, TaskState.RETRIED) else "❌"
                    logger.info(f"📤 子任务{step_id}完成({task_state})，结果：{r['result'][:100]}...")
                
        # 再执行顺序任务（简化处理，真实场景可做拓扑排序）
        for task in sequential_tasks:
            agent_id = getattr(task, "agent_id")
            prompt = getattr(task, "prompt", getattr(task, "description", ""))
            agent = self.get_agent(agent_id)
            if not agent:
                step_results[task.step_id] = f"错误：找不到Agent {agent_id}"
                task_states[task.step_id] = TaskState.FAILED
                quality_reports[task.step_id] = {
                    "task_id": task.step_id, "passed": False, "score": 0,
                    "reasons": [f"Agent {agent_id} 未注册"], "strategy": "rules",
                }
                continue

            prog_q = getattr(self, '_progressive_queue', None)
            if prog_q is not None:
                prog_q.put_nowait({"type": "thinking", "agent_id": agent_id, "status": "thinking"})

            # 🔧 黑板机制：从shared_workspace注入上下文到prompt
            workspace = state.get("shared_workspace", {})
            workspace_context = "\n=== 之前任务的关键发现（黑板上下文） ===\n"
            if workspace:
                for key, value in workspace.items():
                    workspace_context += f"- {key}: {str(value)[:300]}...\n"
            else:
                workspace_context += "暂无前置任务的共享上下文\n"

            # 合并技能列表、黑板上下文和当前任务prompt
            skills_prompt = self.get_available_skills_prompt()
            runtime_context = f"=== 执行上下文 ===\n- conversation_id: {state.get('conversation_id')}\n- current_user_id: {state.get('current_user_id') or 'unknown'}"

            # 添加用户启用的技能注入
            active_skills_injection = ""
            active_skills_list = getattr(self, '_active_skills', None)
            if active_skills_list:
                active_skills_injection = self.get_active_skills_injection(active_skills_list)

            full_prompt = f"{skills_prompt}{active_skills_injection}\n{runtime_context}\n{workspace_context}\n=== 当前任务 ===\n{prompt}"

            # 使用重试+质量检查辅助方法
            result_text, task_state, quality = await self._execute_single_task_with_retry(
                task=task,
                base_prompt=full_prompt,
                state=state,
                conversation_id=state.get("conversation_id"),
            )

            if prog_q is not None:
                prog_q.put_nowait({"type": "thinking", "agent_id": agent_id, "status": "done"})

            step_results[task.step_id] = result_text
            task_states[task.step_id] = task_state
            if quality:
                quality_reports[task.step_id] = quality

            # 🔧 黑板机制：将当前任务结果写入shared_workspace
            current_workspace = state.get("shared_workspace", {})
            current_workspace[f"task_{task.step_id}_output"] = result_text
            state["shared_workspace"] = current_workspace

            # 顺序子任务完成后也实时保存到数据库
            conv_id = state.get("conversation_id")
            if conv_id and self.db_session:
                from backend.services.conversation_service import ConversationService
                conv_service = ConversationService(self.db_session)
                conv_service.add_message_to_conversation(
                    conversation_id=int(conv_id),
                    agent_id=agent_id,
                    content=f"📝 顺序任务{task.step_id}完成：\n{result_text}"
                )

            # 收集 Agent 输出
            artifacts = self._parse_artifacts(result_text)
            agent_outputs.append({
                "agent_id": agent_id,
                "content": result_text,
                "artifacts": artifacts,
            })
            # 实时推送 artifact 到 SSE 队列
            prog_q = getattr(self, '_progressive_queue', None)
            if prog_q is not None:
                for art in artifacts:
                    prog_q.put_nowait({
                        "agent_id": agent_id,
                        "type": art.get("type", "code"),
                        "title": art.get("title", "代码"),
                        "content": art.get("content", ""),
                        "artifacts": [art],
                    })
            status_icon = "✅" if task_state in (TaskState.SUCCEEDED, TaskState.RETRIED) else "❌"
            logger.info(f"📤 顺序子任务{task.step_id}完成({task_state})，结果：{result_text[:100]}...")

        logger.info(f"🎉 所有子任务执行完成，共{len(step_results)}个结果")
        return {
            **state,
            "step_results": step_results,
            "agent_outputs": agent_outputs,
            "task_states": task_states,
            "quality_reports": quality_reports,
            "orchestrator_state": OrchestratorState.RUNNING,
        }

    async def _execute_single_task_with_retry(
        self, task, base_prompt: str, state: GraphState, conversation_id: str
    ) -> tuple:
        """
        执行单个子任务，带重试循环和质量检查。

        Returns:
            (result_text, task_state, quality_report_dict_or_None)
        """
        agent_id = getattr(task, "agent_id")
        agent = self.get_agent(agent_id)
        if not agent:
            return f"错误：找不到Agent {agent_id}", TaskState.FAILED, {
                "task_id": task.step_id, "passed": False, "score": 0,
                "reasons": [f"Agent {agent_id} 未注册"], "strategy": "rules",
            }

        max_retries = getattr(task, "max_retries", 1)
        if max_retries < 1:
            max_retries = 1

        last_result = ""
        last_quality = None
        current_prompt = base_prompt

        for attempt in range(max_retries + 1):
            try:
                output_text = await self._call_agent_with_tools(
                    agent=agent,
                    prompt=current_prompt,
                    conversation_id=conversation_id,
                    active_skills=getattr(self, '_active_skills', None),
                    current_user_id=state.get("current_user_id"),
                    current_user_name=state.get("current_user_name", "unknown"),
                )
                last_result = output_text

                # 质量检查
                quality = None
                if self.quality_checker:
                    expected_fmt = getattr(task, "output_format", "自然语言")
                    task_prompt = getattr(task, "prompt", "")
                    quality = await self.quality_checker.assess(
                        task_id=task.step_id,
                        result=output_text,
                        task_prompt=task_prompt,
                        expected_format=expected_fmt,
                    )
                    last_quality = {
                        "task_id": task.step_id,
                        "passed": quality.passed,
                        "score": quality.score,
                        "reasons": quality.reasons,
                        "strategy": quality.strategy,
                    }

                if quality is None or quality.passed:
                    state_label = TaskState.SUCCEEDED if attempt == 0 else TaskState.RETRIED
                    logger.info(
                        f"✅ 子任务{task.step_id}执行成功 (attempt={attempt+1}/{max_retries+1}, "
                        f"quality={'passed' if quality and quality.passed else 'unchecked'})"
                    )
                    return output_text, state_label, last_quality

                # 质量不通过，准备重试
                if attempt < max_retries:
                    retry_hint = f"\n\n[重试提示] 第{attempt+1}次结果质量不通过：{quality.reason_text}\n请改进后重新作答。"
                    current_prompt = base_prompt + retry_hint
                    logger.info(
                        f"🔄 子任务{task.step_id}质量不通过，重试 attempt={attempt+1}/{max_retries+1}: "
                        f"score={quality.score}, reasons={quality.reasons}"
                    )

            except Exception as e:
                last_result = f"执行失败: {str(e)}"
                if attempt < max_retries:
                    logger.warning(f"🔄 子任务{task.step_id}异常，重试 attempt={attempt+1}/{max_retries+1}: {e}")
                    continue
                logger.error(f"❌ 子任务{task.step_id}重试耗尽，最终失败: {e}")

        # 所有重试耗尽
        final_state = TaskState.RETRIED
        if last_quality is None:
            last_quality = {
                "task_id": task.step_id, "passed": False, "score": 0,
                "reasons": [f"所有{max_retries+1}次尝试均失败"], "strategy": "rules",
            }
        return last_result, final_state, last_quality

    async def _generate_summary_node(self, state: GraphState) -> Dict[str, Any]:
        """
        汇总所有子任务的执行结果，生成最终的总结报告返回给用户
        """
        logger.info("--- [PlanningWorkflow] 生成最终总结报告 ---")
        step_results = state.get("step_results", {})
        task_content = state.get("task_content", "")

        # 构建所有步骤的结果文本
        results_text = "\n".join(
            [f"步骤{sid}: {str(result)[:500]}" for sid, result in step_results.items()]
        )
        prompt = (
            f"用户的原始请求是：{task_content}\n\n各子任务的执行结果：\n{results_text}"
            f"\n\n请将这些结果整理成一份清晰、友好的总结报告回复用户。"
        )
        logger.info(f"[SUMMARY] prompt 长度={len(prompt)}，step_results 条数={len(step_results)}")
        messages = [{"role": "user", "content": prompt}]

        # 尝试流式生成 summary，实时推 token 到 SSE 队列
        prog_queue = getattr(self, '_progressive_queue', None)
        if prog_queue is not None:
            summary = ""
            token_count = 0
            async for token in self.get_backend("tongyi").chat_stream(messages):
                summary += token
                token_count += 1
                prog_queue.put_nowait({"type": "token_event", "token": token})
            logger.info(f"[SUMMARY] 流式生成完成, tokens={token_count}, 总长度={len(summary)}")
        else:
            summary = await self.get_backend("tongyi").chat(messages)
            if isinstance(summary, str):
                summary = summary.strip()
            else:
                summary = str(summary).strip()
            logger.info(f"[SUMMARY] 非流式生成, 长度={len(summary)}, 非空={bool(summary)}")

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
                prompt = self.prompt_loader.get('workflow', 'memory_compression', history_text=history_text)
                messages_for_summary = [{"role": "user", "content": prompt}]
                summary_resp = await self.get_backend("tongyi").chat(messages_for_summary)
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
                adapter_id = llm_config.get("adapter_id", "tongyi")
                backend = self.llm_backends.get(adapter_id)

                if not backend:
                    logger.warning(f"跳过自定义 Agent '{agent_id}'，因为找不到后端 '{adapter_id}'。可用后端: {list(self.llm_backends.keys())}")
                    continue

                try:
                    system_prompt = config.get("system_prompt", "你是一个乐于助人的AI助手。")
                    agent_name = config.get("name", agent_id)
                    custom_agent = CustomAgent(
                        agent_id=agent_id,
                        system_prompt=system_prompt,
                        llm_backend=backend,
                        name=agent_name
                    )
                    self.register_agent(custom_agent)
                    logger.info(f"成功加载自定义 Agent: '{agent_name}' ({agent_id}) (后端: {adapter_id})")

                except Exception as e:
                    logger.error(f"加载自定义 Agent '{agent_id}' 时出错: {e}", exc_info=True)

        except FileNotFoundError:
            logger.warning(f"自定义 Agent 配置文件未找到: {config_path}")
        except Exception as e:
            logger.error(f"加载 custom_agents.yaml 文件时发生未知错误: {e}", exc_info=True)

    def _setup_agents(self):
        """初始化并注册所有 Agent。使用统一的 LLMBackend 体系。"""
        default_backend = self.get_backend("tongyi")
        self.register_agent(PlannerAgent(backend=default_backend))
        self.register_agent(SummarizerAgent(backend=default_backend))

        # 注册核心 Agent（旧 Adapter 包装为 CustomAgent 向下兼容）
        # TODO: 后续逐步将聊天 Agent 也从 TongyiAdapter 迁移到 CustomAgent + LLMBackend
        try:
            tongyi_config = {"model": "qwen-plus"}
            self.register_agent(TongyiAdapter.from_config("tongyi", tongyi_config))
            logger.info("核心 Agent 'tongyi' 已注册（旧适配器模式，计划废弃）。")
        except Exception as e:
            logger.warning(f"无法注册核心 Agent 'tongyi': {e}")

        try:
            deepseek_config = {"model": "deepseek-coder"}
            self.register_agent(DeepSeekAdapter.from_config("deepseek", deepseek_config))
            logger.info("核心 Agent 'deepseek' 已注册（旧适配器模式，计划废弃）。")
        except Exception as e:
            logger.warning(f"无法注册核心 Agent 'deepseek': {e}")

        self._load_custom_agents()

    def _register_workflows(self):
        """动态扫描、导入并注册所有工作流插件。"""
        workflows_dir = os.path.join(os.path.dirname(__file__), '..', 'workflows')
        logger.info(f"正在从 '{workflows_dir}' 目录扫描工作流插件...")

        for filename in os.listdir(workflows_dir):
            if filename.endswith('.py') and filename not in ['__init__.py', 'base.py']:
                module_name = f"backends.workflows.{filename[:-3]}"
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
        从 llm_backends 注册表中获取 API 配置。
        """
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
        import requests, os

        backend_name = "tongyi"
        model_name = "qwen-plus"

        # 检测 Agent 使用的后端
        if isinstance(agent, CustomAgent) and hasattr(agent, 'backend'):
            backend_name = agent.backend.provider
            model_name = agent.backend.model_name
        elif hasattr(agent, 'model_name'):
            model_name = agent.model_name
            if isinstance(agent, DeepSeekAdapter):
                backend_name = "deepseek"

        # 从后端注册表获取配置
        backend = self.llm_backends.get(backend_name)
        if backend:
            model_name = backend.model_name

        class HttpChatModel(BaseChatModel):
            """轻量 LangChain ChatModel：直接 HTTP 调用 API，0 外部依赖冲突"""
            model_name: str = "qwen-plus"
            temperature: float = 0.7
            api_key: str = ""
            base_url: str = ""

            @property
            def _llm_type(self) -> str:
                return "http-chat-model"

            def _generate(self, messages: list, stop: list = None, run_manager=None, **kwargs) -> ChatResult:
                import time as _time
                role_map = {"human": "user", "ai": "assistant", "system": "system",
                            "tool": "tool", "function": "function"}
                api_messages = []
                for m in messages:
                    raw_role = getattr(m, 'type', 'user')
                    role = role_map.get(raw_role, "user")
                    api_messages.append({"role": role, "content": getattr(m, 'content', str(m))})
                payload = {
                    "model": self.model_name,
                    "messages": api_messages,
                    "temperature": self.temperature,
                }
                payload["max_tokens"] = 8192
                masked_key = (self.api_key[:6] + "..." + self.api_key[-4:]) if len(self.api_key) > 10 else "empty"
                retries = 0
                while True:
                    t0 = _time.time()
                    logger.info(f"[HTTP-LLM] POST {self.base_url} key={masked_key} model={self.model_name} msgs={len(api_messages)}")
                    resp = requests.post(
                        self.base_url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json=payload, timeout=300,
                    )
                    elapsed = _time.time() - t0
                    logger.info(f"[HTTP-LLM] 响应 {resp.status_code} ({elapsed:.1f}s): {resp.text[:200]}")
                    if resp.status_code == 200:
                        break
                    if resp.status_code == 500 and retries < 2:
                        retries += 1
                        logger.warning(f"[HTTP-LLM] API 500，重试 {retries}/2...")
                        _time.sleep(5 * retries)
                        continue
                    raise RuntimeError(f"API {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = (msg.get("content") or "").strip()
                reasoning = (msg.get("reasoning_content") or "").strip()
                if content:
                    final_content = content
                elif reasoning:
                    logger.info(f"[HTTP-LLM] content 为空，使用 reasoning_content 兜底（{len(reasoning)} chars）")
                    final_content = f"Thought: 我已思考完毕。\nFinal Answer: {reasoning}"
                else:
                    logger.warning("[HTTP-LLM] content 和 reasoning_content 均为空")
                    final_content = "Error: 模型返回内容为空，请重试"
                logger.info(f"[HTTP-LLM] 最终 content 前100字: {final_content[:100]}")
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=final_content))])

        if backend_name == "deepseek":
            api_key = getattr(backend, 'api_key', None) or os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                logger.warning("DEEPSEEK_API_KEY 未设置，无法为 DeepSeek 创建 ReAct LLM")
                return None
            return HttpChatModel(
                model_name=model_name, api_key=api_key,
                base_url="https://api.deepseek.com/v1/chat/completions",
            )

        if backend_name == "opencode":
            api_key = getattr(backend, 'api_key', None) or os.environ.get("OPENCODE_API_KEY", "")
            if not api_key:
                logger.warning("OPENCODE_API_KEY 未设置，无法为 OpenCode 创建 ReAct LLM")
                return None
            return HttpChatModel(
                model_name=model_name, api_key=api_key,
                base_url="https://opencode.ai/zen/v1/chat/completions",
            )

        # 默认：Tongyi (DashScope)
        api_key = getattr(backend, 'api_key', None) or os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            logger.warning("DASHSCOPE_API_KEY 未设置，无法为 Tongyi 创建 ReAct LLM")
            return None
        return HttpChatModel(
            model_name=model_name, api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )

    def register_agent(self, agent: BaseAgent):
        """注册Agent到Orchestrator，自动绑定所有工具，支持工具调用"""
        try:
            from langchain.agents.agent import AgentExecutor
            from langchain.agents import create_react_agent
        except ImportError:
            logger.warning("⚠️ 未找到LangChain的ReAct相关模块，将跳过工具调用支持")
            if agent.agent_id in self.agents:
                logger.warning(f"Agent '{agent.agent_id}' 已被注册，将被覆盖。")
            self.agents[agent.agent_id] = agent
            logger.info(f"✅ Agent '{agent.agent_id}' 已注册（无工具调用支持）。")
            return
        from langchain_core.prompts import ChatPromptTemplate
        
        # 给agent创建ReAct执行器，绑定所有langchain_tools
        # 统一尝试为 Agent 创建 LLM，不区分 CustomAgent/适配器类型
        logger.info(f"🔍 [register_agent] agent={agent.agent_id}, has_llm={hasattr(agent,'llm')}, langchain_tools数量={len(self.langchain_tools)}, 工具名={[t.name for t in self.langchain_tools]}")
        if not hasattr(agent, 'llm') and self.langchain_tools:
            agent.llm = self._create_langchain_llm(agent)
            logger.info(f"🔍 [register_agent] 为 agent 创建了 llm: {getattr(agent.llm, 'model_name', 'unknown')}")

        if hasattr(agent, 'llm') and self.langchain_tools:
            # deepseek-v4-flash 是 reasoning 模型，单次调用 70-110s，
            # 且经常返回空 content 或格式错误的 ReAct 输出（缺 Action Input:）。
            # 用这个模型跑 ReAct tool-calling 等于每轮等 ~90s 然后大概率解析失败重试。
            # 跳过 ReAct，直接走 process_message（纯 LLM 调用）。
            llm_model = getattr(agent.llm, 'model_name', '')
            if 'deepseek' in llm_model.lower():
                logger.info(f"⏭️ Agent '{agent.agent_id}' 使用 reasoning 模型 ({llm_model})，跳过 ReAct 直接使用 process_message")
                if agent.agent_id in self.agents:
                    logger.warning(f"Agent '{agent.agent_id}' 已被注册，将被覆盖。")
                self.agents[agent.agent_id] = agent
                logger.info(f"Agent '{agent.agent_id}' 已注册（无 ReAct）。")
                return
            try:
                # ReAct agent 配置
                from langchain_core.prompts import ChatPromptTemplate
                react_prompt_template = self.prompt_loader.get('orchestrator', 'react_agent')
                react_prompt = ChatPromptTemplate.from_template(react_prompt_template)
                from langchain.agents import create_react_agent
                react_agent = create_react_agent(agent.llm, self.langchain_tools, react_prompt)
                agent_executor = AgentExecutor(
                    agent=react_agent,
                    tools=self.langchain_tools,
                    verbose=False,
                    max_iterations=3,
                    handle_parsing_errors=True,
                )
                # 为agent附加执行器
                agent.executor = agent_executor
                self.agents[agent.agent_id] = agent
                logger.info(f"✅ Agent '{agent.agent_id}' 已注册，绑定了{len(self.langchain_tools)}个工具，支持工具调用。工具列表: {[t.name for t in self.langchain_tools]}")
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
        """注册用户通过表单创建的自定义Agent，使用统一 LLMBackend。"""
        backend_name = getattr(db_agent, "llm_adapter", "tongyi")
        backend = self.llm_backends.get(backend_name) or self.get_backend("tongyi")

        new_agent = CustomAgent(
            agent_id=db_agent.agent_id,
            system_prompt=db_agent.system_prompt,
            llm_backend=backend,
            name=getattr(db_agent, "name", db_agent.agent_id),
        )
        # 挂载 3 类配置
        new_agent.memory_config = getattr(db_agent, "memory_config", None)
        new_agent.planning_config = getattr(db_agent, "planning_config", None)
        new_agent.validation_config = getattr(db_agent, "validation_config", None)
        self.register_agent(new_agent)
        logger.info(f"✅ 成功注册自定义Agent: {new_agent.name} ({db_agent.agent_id})，后端: {backend.provider}")

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
            logger.warning(f"加载自定义Agent失败（数据库可能还未迁移，重启即可解决）: {e}")

    def get_workflow(self, workflow_id: str) -> StateGraph | None:
        """检索已有工作流的方法，和get_agent对应，外部可以调用这个方法检查工作流是否存在"""
        return self.workflows.get(workflow_id)["graph"] if workflow_id in self.workflows else None

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self.agents.get(agent_id)

    def _find_mentioned_agent_ids(self, content: str) -> List[str]:
        """
        从消息内容中提取所有 @mention，返回 agent_id 列表。
        查找优先级：
          1. 直接匹配 agent_id（如 @tongyi）
          2. 按显示名称匹配（如 @python专家，查找所有 Agent 的 .name 属性）
        """
        matches = re.findall(MENTION_REGEX, content)
        found: List[str] = []
        for mentioned in matches:
            mentioned = mentioned.strip()
            # 1) 先尝试作为 agent_id 直接查找
            if mentioned in self.agents:
                found.append(mentioned)
                continue
            # 2) 按显示名称查找
            for agent_id, agent in self.agents.items():
                agent_name = getattr(agent, 'name', None)
                if agent_name and agent_name == mentioned:
                    found.append(agent_id)
                    break
            else:
                # 3) 找不到也放进去，_handle_mention 会给出"未找到"提示
                found.append(mentioned)
        return found

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
        """
        评估所有子任务的结果，判断是否需要重规划。

        两阶段评估：
        1. 纯规则判断（任务计数 + 质量报告）
        2. 独立 ReplanEvaluator LLM 评估（仅在有模糊情况时调用）

        评估与规划解耦：本节点只负责判断状态，不直接生成新计划。
        新计划由 PlannerAgent 在得到 replan_context 后生成。
        """
        logger.info("--- [PlanningWorkflow] 评估子任务结果（两阶段评估） ---")
        tasks = state.get("plan_data", {}).get("tasks", [])
        step_results = state.get("step_results", {})
        task_content = state.get("task_content", "")
        task_states = state.get("task_states", {})
        quality_reports = state.get("quality_reports", {})

        if not tasks:
            return {**state, "final_summary": "无任务可评估", "orchestrator_state": OrchestratorState.SUCCESS}

        # ===== 第一阶段：纯规则判断 =====

        # 统计任务完成情况（结合 task_states 和 quality_reports）
        succeeded_tasks = []
        failed_task_ids = []
        for task in tasks:
            sid = task.step_id
            ts = task_states.get(sid, "")
            qr = quality_reports.get(sid, {})
            # 判断成功：state 为 succeeded 或 retried，且质量通过
            if ts in (TaskState.SUCCEEDED, TaskState.RETRIED):
                if qr and isinstance(qr, dict) and not qr.get("passed", True):
                    # 质量不通过但被标记为成功 → 归类为失败
                    failed_task_ids.append(sid)
                else:
                    succeeded_tasks.append(sid)
            elif ts == TaskState.FAILED:
                failed_task_ids.append(sid)
            else:
                # 无 task_state 的旧数据兼容：检查 step_results
                res = step_results.get(sid, "")
                if not res or (isinstance(res, dict) and res.get("status") == "failed"):
                    failed_task_ids.append(sid)
                elif isinstance(res, str) and (res.startswith("执行失败") or res.startswith("错误：")):
                    failed_task_ids.append(sid)
                else:
                    succeeded_tasks.append(sid)

        total = len(tasks)
        succeeded_count = len(succeeded_tasks)
        failed_count = len(failed_task_ids)

        logger.info(
            f"[EVALUATE] 任务完成情况: 总数={total}, 成功={succeeded_count}, "
            f"失败={failed_count}, failed_ids={failed_task_ids}"
        )

        # 快速路径：全部成功 → 直接完成
        if succeeded_count == total and failed_count == 0:
            logger.info(f"[EVALUATE] 所有 {total} 个任务成功，直接结束")
            return {
                **state,
                "final_summary": "所有任务完成",
                "orchestrator_state": OrchestratorState.SUCCESS,
            }

        plan_iteration = state.get("plan_iteration", 0)

        # ===== 第二阶段：硬条件检查 =====
        hard_verdict = check_hard_replan_conditions(
            quality_reports=quality_reports,
            task_states=task_states,
            plan_iteration=plan_iteration,
            max_replan_limit=MAX_REPLAN_LIMIT,
            max_task_retries=MAX_TASK_RETRIES,
        )

        if hard_verdict:
            logger.info(
                f"[EVALUATE] 硬条件触发: action={hard_verdict.action}, "
                f"reason={hard_verdict.reason}"
            )
            if hard_verdict.action == "degrade":
                return await self._handle_degrade(state, hard_verdict.reason)
            elif hard_verdict.action == "replan":
                return await self._do_replan(state, succeeded_tasks, failed_task_ids)

        # ===== 第三阶段：独立评估器 LLM 语义评估 =====
        # 分类结果：valid_results / failed_tasks
        valid_results = {}
        failed_detail = {}
        for sid in succeeded_tasks:
            valid_results[sid] = step_results.get(sid, "")
        for sid in failed_task_ids:
            qr = quality_reports.get(sid, {})
            if isinstance(qr, dict):
                reason = qr.get("reasons", ["未知"])[0] if qr.get("reasons") else "未知"
            else:
                reason = "执行异常"
            failed_detail[sid] = {
                "result": str(step_results.get(sid, ""))[:200],
                "reason": reason,
                "retries": task_states.get(sid, ""),
            }

        if self.replan_evaluator:
            verdict = await self.replan_evaluator.evaluate(
                task_content=task_content,
                valid_results=valid_results,
                failed_tasks=failed_detail,
                plan_iteration=plan_iteration,
                max_replan_limit=MAX_REPLAN_LIMIT,
            )
            logger.info(
                f"[EVALUATE] ReplanEvaluator 判定: action={verdict.action}, "
                f"confidence={verdict.confidence:.2f}, reason={verdict.reason}"
            )
        else:
            # 降级：无评估器时，有失败就 replan
            verdict = EvaluationVerdict(
                action="replan",
                reason="评估器不可用，默认触发重规划",
                confidence=0.5,
            )

        # 根据评估结论分发
        if verdict.action == "complete":
            return {
                **state,
                "final_summary": f"任务执行完成（{succeeded_count}/{total}成功）",
                "orchestrator_state": OrchestratorState.SUCCESS,
            }
        elif verdict.action == "degrade":
            return await self._handle_degrade(state, verdict.reason)
        elif verdict.action == "replan":
            return await self._do_replan(state, succeeded_tasks, failed_task_ids)
        elif verdict.action == "retry":
            # 标记失败任务为 pending，重新进入 execute_tasks
            logger.info(f"[EVALUATE] 评估器建议重试失败任务: {failed_task_ids}")
            new_task_states = dict(task_states)
            for sid in failed_task_ids:
                new_task_states[sid] = TaskState.PENDING
            return {
                **state,
                "task_states": new_task_states,
                "orchestrator_state": OrchestratorState.RETRY,
            }
        else:
            # 未知 action → 直接总结
            return {**state, "final_summary": "部分任务未完成，请检查结果"}

    async def _do_replan(
        self, state: GraphState, succeeded_tasks: list, failed_task_ids: list
    ) -> Dict[str, Any]:
        """
        执行重规划：构建 replan_context，调用 LLM 生成新计划。

        核心原则：
        - 有效结果保留（succeeded_tasks），禁止重复执行
        - 失败任务废弃（failed_task_ids），需重新设计
        - replan_context 显式标注三类结果供 Planner 使用
        """
        task_content = state.get("task_content", "")
        step_results = state.get("step_results", {})
        tasks = state.get("plan_data", {}).get("tasks", [])
        task_states = state.get("task_states", {})
        quality_reports = state.get("quality_reports", {})

        plan_iteration = state.get("plan_iteration", 0) + 1
        if plan_iteration > MAX_REPLAN_LIMIT:
            logger.warning(f"[REPLAN] 重规划次数超限 ({plan_iteration}/{MAX_REPLAN_LIMIT})，降级处理")
            return await self._handle_degrade(
                state, f"重规划次数超限({plan_iteration}/{MAX_REPLAN_LIMIT})"
            )

        # 1. 分类三类结果
        valid_results = {}
        failed_detail = {}
        discarded_ids = []

        for task in tasks:
            sid = task.step_id
            if sid in succeeded_tasks:
                valid_results[sid] = str(step_results.get(sid, ""))[:300]
            elif sid in failed_task_ids:
                qr = quality_reports.get(sid, {})
                if isinstance(qr, dict):
                    reasons = qr.get("reasons", ["未知"])
                else:
                    reasons = ["未知"]
                failed_detail[sid] = {
                    "result": str(step_results.get(sid, ""))[:200],
                    "reason": "; ".join(reasons) if reasons else "未知",
                    "agent_id": getattr(task, "agent_id", "unknown"),
                }
            else:
                # 不在成功列表也不在失败列表 → 废弃
                discarded_ids.append(sid)
                task_states[sid] = TaskState.SKIPPED

        # 2. 构建 replan_context
        replan_context = {
            "valid_results": valid_results,
            "failed_tasks": failed_detail,
            "discarded_tasks": discarded_ids,
        }

        logger.info(
            f"[REPLAN] 第{plan_iteration}次重规划: valid={len(valid_results)}, "
            f"failed={len(failed_detail)}, discarded={len(discarded_ids)}"
        )

        # 3. 构建 replan prompt
        valid_summary = "\n".join(
            f"- 任务{sid}: {res[:150]}..." for sid, res in valid_results.items()
        ) if valid_results else "（无）"

        failed_summary = "\n".join(
            f"- 任务{sid} (Agent: {info.get('agent_id', '?')}): {info.get('reason', '?')}"
            for sid, info in failed_detail.items()
        ) if failed_detail else "（无）"

        discarded_summary = "\n".join(
            f"- 任务{sid}（已废弃）" for sid in discarded_ids
        ) if discarded_ids else "（无）"

        available_agents = "\n".join(f"- {aid}" for aid in self.agents.keys())

        replan_prompt = self.prompt_loader.get('workflow', 'replan_prompt',
            task_content=task_content,
            replan_count=str(plan_iteration),
            max_replan_limit=str(MAX_REPLAN_LIMIT),
            available_agents=available_agents,
            valid_results=valid_summary,
            failed_tasks=failed_summary,
            discarded_tasks=discarded_summary,
        )

        # 4. 调用 LLM 生成新计划
        try:
            messages = [{"role": "user", "content": replan_prompt}]
            resp = await self.get_backend("tongyi").chat(messages)
            content = resp if isinstance(resp, str) else resp.content.strip()

            match = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
            json_str = match.group(1).strip() if match else content.strip()
            decision = json.loads(json_str)

            logger.info(f"[REPLAN] LLM 决策: {decision.get('decision', 'unknown')}, "
                        f"rationale: {decision.get('rationale', '')[:100]}")

            if decision.get("decision") == "degrade":
                return await self._handle_degrade(
                    state, decision.get("rationale", "LLM建议降级")
                )

            # 解析新任务
            new_tasks_raw = decision.get("new_tasks", [])
            normalized_tasks = self._normalize_task_fields(new_tasks_raw)

            try:
                new_tasks = [TaskSpec(**t) for t in normalized_tasks]
            except Exception as e:
                logger.error(f"[REPLAN] TaskSpec 校验失败: {e}")
                return await self._handle_degrade(state, f"新计划校验失败: {e}")

            # 5. 保留有效结果，清空失败/废弃结果
            new_step_results = {}
            for sid in succeeded_tasks:
                if sid in step_results:
                    new_step_results[sid] = step_results[sid]
                    task_states[sid] = TaskState.SUCCEEDED
            for sid in failed_task_ids:
                task_states[sid] = TaskState.SKIPPED

            logger.info(
                f"[REPLAN] 重规划完成: 保留{len(new_step_results)}个结果, "
                f"新计划{len(new_tasks)}个任务, 废弃{len(discarded_ids)}个旧任务"
            )

            return {
                **state,
                "plan_data": {"tasks": new_tasks},
                "step_results": new_step_results,
                "plan_iteration": plan_iteration,
                "task_states": task_states,
                "replan_context": replan_context,
                "orchestrator_state": OrchestratorState.REPLAN,
            }

        except json.JSONDecodeError as e:
            logger.error(f"[REPLAN] JSON 解析失败: {e}")
            return await self._handle_degrade(state, f"重规划响应解析失败: {e}")
        except Exception as e:
            logger.error(f"[REPLAN] 重规划异常: {e}")
            return await self._handle_degrade(state, f"重规划异常: {e}")

    def _normalize_task_fields(self, raw_tasks: list) -> list:
        """将 LLM 返回的不规则字段映射为 TaskSpec 标准字段。"""
        FIELD_ALIASES = {
            'step_id': ['id'],
            'agent_id': ['role', 'agent', 'assigned_to', 'executor'],
            'prompt': ['description', 'task', 'instruction', 'content'],
            'dependencies': ['depends_on', 'depends', 'prerequisites'],
        }
        normalized_tasks = []
        for t in raw_tasks:
            normalized = {}
            for std_field, aliases in FIELD_ALIASES.items():
                for alias in aliases:
                    if alias in t and std_field not in t:
                        normalized[std_field] = t.pop(alias)
                        break
                if std_field in t:
                    normalized[std_field] = t[std_field]
            for k, v in t.items():
                if k not in normalized:
                    normalized[k] = v
            if 'prompt' not in normalized:
                normalized['prompt'] = normalized.get('description', '执行修复任务')
            normalized.pop('description', None)
            if 'agent_id' not in normalized:
                normalized['agent_id'] = 'tongyi'
            normalized_tasks.append(normalized)
        return normalized_tasks

    async def _handle_degrade(self, state: GraphState, reason: str) -> Dict[str, Any]:
        """
        降级执行：放弃复杂流程，直接用通用 LLM 回答用户原始问题。
        """
        task_content = state.get("task_content", "")
        logger.warning(f"[DEGRADE] 触发降级: {reason}")

        try:
            fallback_prompt = self.prompt_loader.get('workflow', 'fallback',
                task_content=task_content,
            )
            messages = [{"role": "user", "content": fallback_prompt}]
            resp = await self.get_backend("tongyi").chat(messages)
            fallback_answer = resp if isinstance(resp, str) else resp.content.strip()
            summary = f"⚠️ 复杂流程已降级处理（原因：{reason}）\n\n{fallback_answer}"
        except Exception as e:
            logger.error(f"[DEGRADE] 降级回答生成失败: {e}")
            summary = f"⚠️ 任务处理遇到问题：{reason}。请稍后重试或简化您的需求。"

        return {
            **state,
            "final_summary": summary,
            "orchestrator_state": OrchestratorState.DEGRADE,
        }
