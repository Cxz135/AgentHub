# Skill Creator（技能创建助手）

## 触发条件
当用户说以下内容时，自动识别并创建新 Skill：
- "我想创建名为xx的skill"
- "创建一个skill，名字是xx"
- "新建一个skill叫xx"
- "我想创建一个可以xxx的skill"

## 识别模式
```
(我想创建名为|创建名为|新建一个|创建一个).*?(skill|技能)
```

## 执行流程
1. 解析用户输入，提取：
   - `name`: Skill 名称（从"名为xx"或"叫xx"中提取）
   - `description`: 功能描述（从"可以xxx"或"能xxx"中提取）
2. 调用工具 `manage_skill.create_skill` 创建 Skill

## 工具调用格式
```json
{
  "name": "技能显示名称",
  "description": "功能描述",
  "category": "分类（可选，默认 general）"
}
```

## 示例对话

**用户**：`我想创建一个名为 code_comment 的 skill，可以自动为代码添加中文注释`

**助手**：
调用 `manage_skill.create_skill`：
```json
{
  "name": "代码注释助手",
  "description": "自动为代码添加清晰、准确的中文注释，保持代码整洁易读",
  "category": "programming"
}
```

## 注意事项
- 如果用户只说了名称没说功能，引导补充："好的，请描述一下这个 Skill 的功能"
- 如果用户说了功能没说名称，自动生成一个合适的名称
- 名称会转为 slug 格式（如 code_comment）
- 创建成功后告知用户 Skill 的完整信息