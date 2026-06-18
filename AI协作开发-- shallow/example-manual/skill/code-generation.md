# 代码生成技能

> **📎 何时读此文件**: 写新代码、实现新功能、创建新模块时
> **对应原则**: KNW-04（复用优先）、DEV-01（详尽的日志）
> **相关文件**: `rules/logging.md`, `rules/testing.md`, `spec/tech-stack.md`

## 技能定义

**名称**: `code-generation`
**描述**: 代码生成技能，要求 AI 生成的代码符合项目规范、可测试、可维护
**触发条件**: 任何功能实现、模块开发、代码修复

---

## 生成规范

### 1. 代码风格

- 使用项目已有的代码风格（PEP 8）
- 函数名使用 snake_case
- 类名使用 PascalCase
- 常量使用 UPPER_CASE

### 2. 函数设计

- **单一职责**：每个函数只做一件事
- **参数明确**：参数名有明确含义，有类型注解
- **返回值明确**：返回类型明确，有文档字符串
- **错误处理**：使用异常而非错误码

```python
# 正确示例
def generate_pdf(content: str, user_id: int = 0) -> str:
    """
    生成 PDF 文件并返回下载 URL。
    
    Args:
        content: Markdown 文本内容
        user_id: 用户 ID，默认 0
        
    Returns:
        可下载的 PDF URL，如 /attachments/{user_id}/{filename}.pdf
        
    Raises:
        FileConversionError: 转换失败时抛出
    """
    pass

# 错误示例
def pdf_gen(data):
    """生成 PDF"""
    pass
```

### 3. 日志要求

每个函数必须包含：
- 入口日志（参数）
- 关键分支日志
- 出口日志（结果/耗时）
- 错误日志（异常 + 上下文）

### 4. 测试准备

生成的代码必须：
- 可测试（依赖可注入）
- 有明确输入输出
- 无副作用（或副作用可控）

---

## 复用检查

实现任何功能前，必须检查：

1. **搜索已有实现**：
   ```bash
   grep -r "def.*pdf" backend/
   grep -r "class.*Agent" backend/
   ```

2. **检查工具函数**：
   - `utils/` 目录是否有类似功能
   - `services/` 目录是否有类似功能

3. **避免重复**：
   - 如果已有类似功能，复用或扩展
   - 如果已有工具函数，直接调用

---

## 代码审查清单

生成代码后，自检：

- [ ] 函数是否有明确职责
- [ ] 参数是否有类型注解
- [ ] 返回值是否有类型注解
- [ ] 是否有文档字符串
- [ ] 是否处理了异常情况
- [ ] 是否有日志记录
- [ ] 是否复用了已有代码
- [ ] 是否引入了循环导入
- [ ] 是否修改了已有函数签名
- [ ] 是否删除了"看起来没用"的代码

---

## 示例

**用户**: "帮我生成一个函数，将用户上传的图片转换为缩略图"

**AI 思考过程**:
1. 搜索已有实现：`grep -r "thumbnail" backend/` → 无结果
2. 搜索图片处理：`grep -r "PIL\|Pillow\|Image" backend/` → 无结果
3. 检查 `utils/` 目录 → 无图片处理工具
4. 创建新函数

```python
# 生成代码
from PIL import Image
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def generate_thumbnail(image_path: str, max_size: int = 200) -> str:
    """
    生成图片缩略图。
    
    Args:
        image_path: 原始图片路径
        max_size: 缩略图最大尺寸，默认 200
        
    Returns:
        缩略图路径
        
    Raises:
        FileNotFoundError: 图片不存在
        ValueError: 不是有效的图片
    """
    logger.info(f"[THUMBNAIL] 开始生成缩略图: {image_path}, max_size={max_size}")
    
    input_path = Path(image_path)
    if not input_path.exists():
        logger.error(f"[THUMBNAIL] 图片不存在: {image_path}")
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    try:
        with Image.open(input_path) as img:
            # 保持比例缩放
            img.thumbnail((max_size, max_size))
            
            # 生成缩略图路径
            output_path = input_path.parent / f"thumb_{input_path.name}"
            img.save(output_path)
            
            logger.info(f"[THUMBNAIL] 缩略图生成成功: {output_path}")
            return str(output_path)
    except Exception as e:
        logger.error(f"[THUMBNAIL] 生成失败: {image_path}, 错误: {e}", exc_info=True)
        raise ValueError(f"生成缩略图失败: {e}")
```

---

> 💡 **提示**：生成代码前，先想清楚函数的输入、输出、职责。不要边写边想。
