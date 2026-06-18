# 废弃方案: 使用 fpdf2 生成 PDF

**废弃日期**: 2026-06-10

**废弃原因**: 
1. fpdf2 对中文支持不佳（`uni=True` 已弃用，去掉后中文丢失）
2. 使用 `.ttc` 字体时子集问题导致乱码
3. 已替换为 reportlab + Arial Unicode.ttf

**替代方案**: reportlab + Arial Unicode.ttf

**历史代码**: 
```python
# 旧代码（已废弃）
from fpdf import FPDF

pdf = FPDF()
pdf.add_page()

# 加载字体（需要 uni=True，但已弃用）
pdf.add_font('Hiragino', fname='/System/Library/Fonts/Hiragino Sans GB.ttc', uni=True)
pdf.set_font('Hiragino', size=12)

# 写入内容
pdf.cell(0, 6, text, ln=True)

pdf.output(str(output_path))
```

**已知问题**:
- `uni=True` 已弃用，但去掉后中文无法渲染
- `.ttc` 字体文件在 `uni=True` 模式下子集问题导致乱码
- 不支持 emoji 字符
- 不支持复杂排版（表格、图片）

**注意事项**: 
- 如果未来 fpdf2 修复了 Unicode 支持，可以重新评估
- 当前项目优先使用 reportlab
- 紧急情况下可以降级到 fpdf2（中文会显示为方块或乱码）

**相关文件**: 
- `backend/utils/file_converter.py`（已删除 fpdf2 优先逻辑，降为最后手段）

---

**废弃决策记录**: 
- 决策日期: 2026-06-10
- 决策人: AI + 用户
- 影响: 需要安装 `reportlab` 依赖
- 迁移工作: 已自动完成（`to_pdf` 函数已修改）
