# 日志规范

> **📎 何时读此文件**: 任何代码修改时、写新函数时、Debug 加日志时
> **对应原则**: DEV-01（详尽的日志）、DEV-02（错误日志不写死）、DEV-05（调用计时）
> **相关文件**: `skill/debugging.md`, `skill/code-generation.md`

## 核心原则

> **每个函数必须在开始、关键分支、结束处添加日志。错误日志不得写死，必须指向直接报错点。**

---

## 日志级别定义

| 级别 | 用途 | 示例 |
|------|------|------|
| DEBUG | 调试信息，开发时使用 | 变量值、中间状态 |
| INFO | 正常流程记录 | 函数开始/结束、操作完成 |
| WARNING | 异常情况，但可以恢复 | 降级处理、配置缺失 |
| ERROR | 错误，需要处理 | 异常、失败、数据错误 |
| CRITICAL | 严重错误，系统可能不可用 | 数据库连接失败、核心服务崩溃 |

---

## 日志内容规范

### 必须包含的信息

1. **上下文**：哪个模块、哪个函数、哪个操作
2. **数据**：输入参数、输出结果、关键变量
3. **状态**：成功/失败、耗时、影响范围
4. **错误详情**：完整异常信息、堆栈（`exc_info=True`）

### 日志模板

```python
# 函数入口
logger.info(f"[MODULE] {func_name} 开始，参数: {safe_params}")

# 关键分支
logger.info(f"[MODULE] {func_name} 进入 {branch} 分支，条件: {condition}")

# 操作完成
logger.info(f"[MODULE] {func_name} 完成，结果: {safe_result}，耗时: {elapsed}s")

# 错误处理
logger.error(f"[MODULE] {func_name} 失败: {e}", exc_info=True)
logger.error(f"[MODULE] {func_name} 失败详情: input={input}, state={state}")

# 降级处理
logger.warning(f"[MODULE] {func_name} 主方案失败，降级到: {fallback}")
logger.info(f"[MODULE] {func_name} 降级完成，结果: {result}")
```

---

## 错误日志规范

### ❌ 禁止写法

```python
# 错误：写死错误描述
except Exception as e:
    logger.error("出错了")  # 没有 e
    
# 错误：只记录部分信息
except Exception as e:
    logger.error(f"失败: {e}")  # 没有上下文
    
# 错误：不记录异常类型
except Exception as e:
    logger.error(f"错误: {str(e)[:50]}")  # 截断
```

### ✅ 正确写法

```python
# 正确：包含完整异常和上下文
except Exception as e:
    logger.error(f"[PDF-CONVERT] to_pdf 失败，输入: {input_path}, 错误: {e}", exc_info=True)

# 正确：记录失败降级
except Exception as e:
    logger.warning(f"[PDF-CONVERT] weasyprint 失败: {e}，降级到 fpdf2")
    try:
        # 降级方案
        result = fallback_method()
        logger.info(f"[PDF-CONVERT] fpdf2 成功，输出: {result}")
    except Exception as e2:
        logger.error(f"[PDF-CONVERT] fpdf2 也失败: {e2}", exc_info=True)
        raise
```

---

## 性能日志

每次调用大模型或耗时操作，必须记录：

```python
import time

start = time.time()
result = await llm.chat(messages)
elapsed = time.time() - start

logger.info(f"[LLM] {model_name} 调用完成，耗时: {elapsed:.1f}s，输入: {len(messages)}条，输出: {len(result)}字")
```

---

## 调试日志

临时调试代码必须包含 `#TEMP_DEBUG#`：

```python
# 临时调试
logger.debug(f"#TEMP_DEBUG# 变量值: {var}")

# 任务完成后删除
```

**任务完成后**：
1. 搜索 `#TEMP_DEBUG#`
2. 删除所有匹配行
3. 确认日志系统正常

---

## 日志检查清单

新增功能时，检查以下日志点：

- [ ] 函数开始：输入参数
- [ ] 关键分支：进入条件
- [ ] 函数结束：输出结果、耗时
- [ ] 错误处理：完整异常、上下文
- [ ] 降级处理：降级原因、降级结果
- [ ] 性能关键：耗时、吞吐量
- [ ] 外部调用：输入、输出、耗时
- [ ] 状态变更：旧状态 → 新状态

---

## 日志格式

推荐格式：

```
2026-06-10 20:18:04,016-core INFO-orchestrator.py:996-[ARTIFACT-DEBUG] progressive_queue is None? False
```

组成：
- `时间戳`
- `模块名`
- `级别`
- `文件名:行号`
- `[标签]` 业务标签
- `消息`

---

> ⚠️ **重要**：日志是排查问题的生命线。没有日志，就是黑盒调试。
