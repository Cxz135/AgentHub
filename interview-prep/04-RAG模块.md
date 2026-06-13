# 面试准备：RAG 模块

---

## Q0: 请简单介绍一下 AgentHub 的 RAG 模块

**参考答复：**

AgentHub 的 RAG（检索增强生成）模块实现了基于向量搜索的知识库问答能力。用户可以上传文档（.txt / .pdf），系统自动做文本分割、向量化存储到 ChromaDB，然后在对话中通过语义检索 + LLM 生成的方式回答知识库相关的问题。

技术栈：ChromaDB（向量存储）+ DashScopeEmbeddings（text-embedding-v4，嵌入模型）+ RecursiveCharacterTextSplitter（文本分割）+ LangChain Chroma wrapper（检索接口）。

核心流程：
1. **文档入库**：上传 → MD5 去重 → TextLoader 加载 → RecursiveCharacterTextSplitter 分块 → DashScopeEmbeddings 向量化 → ChromaDB 持久化
2. **知识检索**：用户提问 → 嵌入向量 → ChromaDB 语义搜索（按 user_id + course 过滤 + top-k）→ 返回相关文档块
3. **答案生成**：检索到的文档块 + 用户问题 → 拼入 prompt → LLM 生成回答

RAG 同时被封装为 LangChain Tool（`rag_retrieval`），Agent 可以在 ReAct 循环中主动调用，实现"按需检索"而非"每次都检索"。

---

## Q1: 为什么选择 ChromaDB 作为向量数据库？和其他向量数据库（Pinecone/Milvus/Weaviate）对比有什么优劣？

**参考答复：**

选择 ChromaDB 的核心原因是 **嵌入式部署** 和 **Python 原生**。

**ChromaDB 的优势**：
- 零运维：PersistentClient 直接读写本地文件，不需要启动额外服务
- Python 原生：API 完全 Pythonic，学习成本低
- 与 LangChain 深度集成：`langchain_chroma.Chroma` wrapper 开箱即用
- 支持 metadata 过滤：可以按 user_id、文档来源等维度过滤
- 轻量：适合中小规模（几万到几十万向量）

**对比其他数据库**：
- Pinecone：性能好但需要外网访问 + 付费，在本地开发场景不友好
- Milvus：功能强大但部署复杂（需要 etcd + MinIO），对单机场景过重
- Weaviate：功能全面但 Go 编写，Python 集成不够原生

对于 AgentHub 的目标场景（个人/小团队使用，单机部署），ChromaDB 是最合适的选择。如果未来需要扩展到生产级大规模场景，可以考虑迁移到 Milvus 或 ChromaDB 的服务化部署。

---

## Q2: 文档入库的完整流程是怎样的？如何处理重复文档？

**参考答复：**

文档入库流程：

1. **文件扫描**：`listdir_with_allowed_type()` 遍历 `data/` 目录，只处理 `.txt` 和 `.pdf` 文件
2. **MD5 去重**：计算文件 MD5，与 `data/md5_hex_store` 文件中已处理的 MD5 列表对比：
   - 已存在 → 跳过，记录日志
   - 不存在 → 继续处理，处理完后写入 MD5 记录
3. **文档加载**：根据文件类型选择 loader（`txt_loader` 或 `pdf_loader`），生成 LangChain `Document` 对象
4. **文本分割**：`RecursiveCharacterTextSplitter` 按配置的 chunk_size/chunk_overlap/separators 分割
5. **向量化入库**：通过 DashScopeEmbeddings 将文本块转为向量，存入 ChromaDB `all_documents` collection
6. **映射记录**：更新 `data/doc_mapping.json`，记录文档 ID 和文件路径的映射关系

去重的关键是 **MD5 内容哈希** 而非文件名：即使文件被重命名或移动，只要内容不变就不会重复入库。

---

## Q3: RecursiveCharacterTextSplitter 的参数是如何配置的？chunk_size 和 overlap 的选择有什么考量？

**参考答复：**

配置在 `config/chroma.yaml` 中：

```yaml
chunk_size: 500        # 每个文本块的最大字符数
chunk_overlap: 50      # 相邻块之间的重叠字符数
separators: ["\n\n", "\n", "。", ".", " ", ""]  # 分割符优先级
```

**chunk_size 的选择**：
- 太小（如 100）→ 语义碎片化，检索到的块可能缺少完整上下文
- 太大（如 2000）→ 检索精度下降，无关内容占比高，且嵌入模型对长文本的表示能力有限
- 500 是一个经验值，在中文场景下约等于一段话的长度，语义相对完整

**chunk_overlap 的选择**：
- 10%（50/500）的重叠率是常见实践
- 保证关键信息在分块边界处不会被切断
- 例如：一段话被切在两块之间，overlap 确保关键词在相邻块中都出现

**separators 优先级**：`\n\n` → `\n` → `。` → `.` → ` ` → `""`，从大到小的分割粒度，尽量在自然边界处分割，避免在句子中间切断。

---

## Q4: RAG 检索的过滤机制是怎样的？为什么需要 user_id 和 course 过滤？

**参考答复：**

检索过滤通过 ChromaDB 的 metadata 过滤实现：

```python
retriever = vector_store.as_retriever(
    search_kwargs={
        "k": top_k,
        "filter": {
            "user_id": user_id,
            "course": course_name
        }
    }
)
```

**user_id 过滤**：确保用户只能检索自己上传的文档，实现数据隔离。
**course 过滤**：支持按"知识库"分类管理，用户可以将不同项目的文档归入不同 course。

两层过滤的好处：
1. **安全性**：多用户场景下不会串数据
2. **准确性**：缩小检索范围，提高命中率（避免在无关文档中检索）
3. **性能**：metadata 过滤在向量搜索前执行，减少需要计算相似度的向量数量

---

## Q5: DashScopeEmbeddings 是什么？为什么选择它？

**参考答复：**

DashScopeEmbeddings 是阿里云的文本嵌入模型服务，使用的是 `text-embedding-v4` 模型。

**选择理由**：
1. **中文优化**：阿里云的嵌入模型对中文文本做了专门优化，在中文语义检索场景表现优于 OpenAI 的 text-embedding-ada-002
2. **与 Qwen 生态一致**：项目中 LLM 默认后端也是 Tongyi/Qwen，使用同一提供商的嵌入模型减少跨平台复杂性
3. **性价比**：中文嵌入场景性价比高
4. **LangChain 原生支持**：`langchain_community.embeddings.DashScopeEmbeddings` 可以直接集成

**技术细节**：嵌入模型将文本映射到固定维度的向量空间，语义相似的文本在向量空间中距离更近（cosine 相似度更高）。

---

## Q6: RAG 工作流（RAGWorkflow）的 LangGraph 实现是怎样的？

**参考答复：**

RAG 工作流是一个两节点的 LangGraph StateGraph：

**节点1：retrieve_knowledge**
- 从 GraphState 中获取用户 query
- 调用 `VectorStoreService.get_retriever()` 获取 retriever
- 使用 `DocumentCompressorPipeline` 对检索结果做重排序和压缩
- 将检索结果写入 GraphState

**节点2：summarize_content**
- 从 GraphState 中获取检索到的文档块
- 拼入 RAG prompt 模板（包含文档内容 + 用户问题 + 回答指令）
- 调用 LLM 生成最终回答
- 将回答写入 GraphState

**流转**：retrieve_knowledge → summarize_content → END

这个工作流被注册为固定工作流，当用户输入匹配 RAG 关键词（"什么是"、"解释一下"、"知识库"等）且得分超过阈值时自动触发。

---

## Q7: RAG 检索结果的质量如何保证？有没有 re-ranking 机制？

**参考答复：**

质量保证通过多个环节：

1. **chunk 设计**：合适的 chunk_size 和 overlap 保证每个块的语义完整性
2. **metadata 过滤**：先按 user_id 和 course 缩小范围，再向量搜索
3. **top_k 限制**：只返回最相关的 k 个文档块，避免无关内容干扰
4. **DocumentCompressorPipeline**：LangChain 的压缩管道，在检索后对结果做进一步的相关性过滤和内容压缩
5. **LLM prompt 约束**：RAG prompt 中明确要求"如果文档内容不足以回答问题，请诚实说明"

当前没有实现专门的 re-ranking 模型（如 Cohere Rerank），`DocumentCompressorPipeline` 提供了基本的压缩能力。在文档量较大时，引入专门的 re-ranking 模型会是下一步优化方向。

---

## Q8: RAG 作为 LangChain Tool 是怎么被 Agent 调用的？

**参考答复：**

RAG 被封装为 `rag_retrieval` 工具函数，注册在 Orchestrator 的 tool_skills 中，最终成为 LangChain Tool：

```python
@tool
def rag_retrieval(query: str) -> str:
    # 调用 VectorStoreService 做检索
    # 返回格式化的文档内容字符串
```

在 ReAct 循环中，Agent 的思考过程：
1. **Thought**: 用户问的是关于项目架构的问题，我需要查询知识库
2. **Action**: rag_retrieval
3. **Action Input**: "AgentHub 项目架构"
4. **Observation**: [工具返回相关文档内容]
5. **Thought**: 根据检索到的文档，我可以回答……
6. **Final Answer**: 根据知识库，AgentHub 的架构是……

这个设计的关键是：RAG 是 Agent 的**可选工具**而非**强制流程**。Agent 可以自主判断是否需要检索知识库，而不是每个问题都先检索。这让 token 消耗更加可控。

---

## Q9: 文档删除是如何实现的？删除后向量数据是否同步清理？

**参考答复：**

文档删除通过 `VectorStoreService.delete_document()` 实现：

1. 从 `doc_mapping.json` 查找文档 ID 对应的文件路径
2. 调用 ChromaDB 的 `collection.delete(ids=[...])` 方法删除对应的向量数据
3. 删除本地文件
4. 更新 `doc_mapping.json` 和 `md5_hex_store`

删除是同步的，向量数据立即从 ChromaDB 中移除。ChromaDB 的 `delete` 方法会同时删除向量和对应的 metadata，不会留下孤儿数据。

需要注意的：ChromaDB 的删除标记了数据，但实际磁盘空间可能需要 compaction 才能释放（类似 SQLite 的 VACUUM）。

---

## Q10: 如果文档更新了（同一路径覆盖了新版本），如何处理？

**参考答复：**

当前实现的去重逻辑是基于 MD5 哈希的，所以：

1. 如果用户覆盖了文件，新文件的 MD5 与旧文件不同
2. 旧的 MD5 记录在 `md5_hex_store` 中，新的 MD5 不在
3. 系统会以为这是一个新文档，再次入库
4. 结果：旧版本的向量数据仍然存在 + 新版本的向量数据也被添加

这是一个**待改进项**。正确的处理应该是：
1. 检测到相同路径的文件更新
2. 先删除旧版本的向量数据（通过 doc_mapping 找到旧的 document IDs）
3. 再入库新版本
4. 更新 MD5 记录和映射

目前的 workaround 是：用户需要先通过 API 删除旧文档，再上传新版本。

---

## Q11: RAG 的检索是怎么和对话上下文结合的？

**参考答复：**

RAG 在工作流中与上下文结合的方式：

1. **工作流触发时**：用户消息作为 query，独立于对话历史进行检索
2. **文档注入 prompt**：检索到的文档块被拼入 RAG 的 summarization prompt，作为"参考资料"放在用户问题之前
3. **Agent 调用时**：如果 Agent 在 ReAct 循环中调用 `rag_retrieval` 工具，检索结果作为 Observation 返回给 Agent，Agent 综合对话历史和检索结果生成回答

当前实现中，RAG 检索的 query 是当前用户消息，没有利用对话历史做 query 改写（如 HyDE 或 multi-query retrieval）。这是后续可以增强的方向——用对话历史改写 query 可以提高检索准确性。

---

## Q12: 项目中文本分割的 separators 是怎么选择的？为什么是这个顺序？

**参考答复：**

配置的 separators 顺序：`["\n\n", "\n", "。", ".", " ", ""]`

这个顺序体现了从大到小的分割粒度，确保文本在"自然边界"处被切分：

1. `\n\n`（双换行）→ 段落边界，最优选择
2. `\n`（单换行）→ 行边界，次优
3. `。`（中文句号）→ 句子边界
4. `.`（英文句号）→ 句子边界
5. ` `（空格）→ 词边界
6. `""`（空字符串）→ 字符级分割，最后的兜底

RecursiveCharacterTextSplitter 的处理逻辑是：先用第一个 separator 尝试分割，如果分出来的块仍然超过 chunk_size，再用下一个 separator 对超出部分继续分割，递归处理，确保每个块都不超过 chunk_size。

---

## Q13: 嵌入模型 text-embedding-v4 的维度和能力如何？对中文的支持怎样？

**参考答复：**

`text-embedding-v4` 是阿里云 DashScope 提供的最新版文本嵌入模型：

- **向量维度**：1024 维（v4 版本）
- **最大输入长度**：支持较长的文本输入
- **中文优化**：针对中文语义做了专门优化，在中英混合、中文口语化等场景表现优秀
- **多语言支持**：除中文外也支持英文和其他语言

相比 v3 的改进：语义理解更准确，特别是对专业术语和技术文档的理解。在 AgentHub 的技术文档问答场景中，v4 的检索命中率明显优于 v3。

---

## Q14: RAG 检索的 top_k 是如何选择的？为什么是 5？

**参考答复：**

top_k=5 的选择是在实验中平衡的结果：

- **太少（k=1-2）**：可能遗漏相关信息，特别是当答案分散在多个文档块中时
- **太多（k=10+）**：无关内容占比增加，稀释有用信息，且增加 LLM 的 token 消耗
- **k=5**：在大多数场景下能覆盖完整的答案上下文，同时保持 prompt 的精简

这个值是可配置的（在 `augment_context` 的 limit 参数中），可以根据实际场景调整。对于技术文档类问答，5 个块通常足够；对于需要综合大量信息的场景，可以调整为 8-10。

---

## Q15: RAG 模块有哪些性能优化空间？

**参考答复：**

当前 RAG 模块的性能优化方向：

1. **嵌入缓存**：对常见 query 的嵌入向量做缓存，避免重复调用嵌入 API
2. **异步嵌入**：将嵌入调用改为异步（DashScope API 支持），减少阻塞
3. **HyDE（假设文档嵌入）**：用 LLM 先生成一个假设答案，再拿假设答案做嵌入检索，提高检索准确性
4. **Query 改写**：利用对话历史改写用户 query（如指代消解），提高检索命中率
5. **Re-ranking**：引入专门的 re-ranking 模型（如 bge-reranker），对初检结果做精排
6. **分层检索**：先用小模型做粗排，再用大模型做精排（减少大模型的调用次数）

对于当前规模（个人/小团队使用），ChromaDB 的本地 HNSW 索引已经足够快，性能瓶颈主要在嵌入 API 调用和 LLM 生成环节。

---

## Q16: 如何评估 RAG 系统的检索质量？

**参考答复：**

评估 RAG 检索质量的方法：

1. **召回率（Recall）**：在所有相关文档中，被检索到的比例
2. **精确率（Precision）**：在检索到的文档中，真正相关的比例
3. **MRR（Mean Reciprocal Rank）**：第一个相关文档排在第几位的倒数
4. **人工评估**：准备测试集（query + 已知的相关文档），人工标注检索结果是否相关

在 AgentHub 中，目前没有系统化的 RAG 质量评估流程。实际使用中通过观察 LLM 的回答质量间接判断：如果 LLM 经常回答"文档中没有相关信息"，可能是检索没命中；如果 LLM 回答与文档无关的内容，可能是检索回了无关文档。

系统化评估是后续的改进方向。

---

## Q17: RAG 和记忆系统的 ChromaDB 是如何共存的？会互相干扰吗？

**参考答复：**

两者使用不同的 ChromaDB collection，完全隔离：

- RAG：使用 `all_documents` collection
- 记忆：使用 `agent_memories_v2` 和 `episodic_memories_v2` collection

它们共享同一个 ChromaDB PersistentClient（同一个 `chroma_db/` 目录），但通过不同的 collection 名称完全隔离。ChromaDB 的 collection 是独立的命名空间，不会互相干扰。

嵌入模型也相同（DashScopeEmbeddings），这保证了 RAG 文档和记忆条目的向量在同一空间，理论上可以进行跨 collection 的联合检索——虽然当前没有实现这个功能。

---

## Q18: 如果用户上传了一个大 PDF（几百页），系统会怎么处理？

**参考答复：**

大 PDF 的处理流程：

1. **PDF 解析**：`pdf_loader` 使用 PDF 解析库（如 PyPDF2 或 pdfplumber）逐页提取文本
2. **文本分割**：RecursiveCharacterTextSplitter 将提取出的全部文本按 chunk_size=500 分割成多个块
3. **批量向量化**：所有文本块通过 DashScopeEmbeddings 做嵌入（批量调用）
4. **批量入库**：所有向量和 metadata 批量写入 ChromaDB

**潜在问题**：
- 嵌入 API 调用量大：几百页 PDF → 可能几千个 chunk → 大量 API 调用，耗时且消耗额度
- 前端无进度反馈：当前是同步处理，用户上传后需要等待较长时间
- 内存占用：大文件解析可能消耗大量内存

**改进方向**：异步处理 + 进度通知 + 分批嵌入。

---

## Q19: RAG 工作流的关键词匹配是如何设计的？如何避免误触发？

**参考答复：**

RAG 工作流注册时的关键词配置：

```python
"keywords": ["什么是", "解释一下", "知识库", "查询", "搜索", "关于", "是什么", "怎么用"]
```

匹配逻辑在 `_auto_match_workflow()` 中：遍历关键词，每个匹配 +1 分。但触发有阈值限制（`WORKFLOW_TRIGGER_THRESHOLD = 6`），需要足够多的关键词匹配才会触发。

但实际上 6 分的阈值对于 RAG 过于严格——“什么是微服务架构”只匹配到 2 个关键词（"什么是" + "是什么"），得分为 2，达不到阈值 6，不会触发 RAG 工作流。实际路由中，这类问题更多走 LLM 复杂度分类 → moderate/simple → 默认聊天路径。

这个是已知的问题：RAG 工作流的关键词匹配阈值需要降低或改为更智能的语义匹配。当前 RAG 功能更多地通过 Agent 在 ReAct 循环中主动调用 `rag_retrieval` 工具来使用，而非依赖工作流自动触发。

---

## Q20: 如果要实现多模态 RAG（支持图片检索），你会如何设计？

**参考答复：**

多模态 RAG 的设计方案：

1. **文档解析扩展**：在 `txt_loader` 和 `pdf_loader` 基础上，增加图片解析器（提取图片中的文字 OCR + 生成图片描述）
2. **多模态嵌入**：使用支持图片的嵌入模型（如 CLIP 或 DashScope 的多模态嵌入 API），将图片和文本映射到同一向量空间
3. **元数据增强**：每个 chunk 增加 modal_type 字段（text/image），检索时可按类型过滤
4. **混合检索**：用户 query 同时检索文本和图片，合并排序后返回
5. **前端渲染**：RAG 回答中包含图片引用时，前端能渲染图片预览

对于 AgentHub 当前的技术栈（ChromaDB + DashScopeEmbeddings），切换到多模态需要：嵌入模型升级为多模态版本 + ChromaDB 的 metadata 增加 modal_type 字段 + 前端支持图片渲染。核心架构（VectorStoreService 抽象层）不需要大改。
