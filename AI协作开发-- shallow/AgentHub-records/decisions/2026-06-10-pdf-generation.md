# 决策: 使用 reportlab 作为 PDF 生成首选

**日期**: 2026-06-10
**状态**: 已采纳
**决策人**: AI + 用户

## 背景

项目需要生成中文 PDF 文件。尝试了 fpdf2、weasyprint、reportlab 三种方案。

## 考虑的方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| fpdf2 | 轻量、纯 Python | 中文支持差、ttc 字体问题、uni=True 已弃用 | ❌ 废弃 |
| weasyprint | 支持 HTML/CSS | 依赖系统库（pango）、macOS 中文字体问题 | ⚠️ 降级（最后手段） |
| reportlab | 中文支持好、稳定、商业级 | 稍重、需要安装 | ✅ 首选 |

## 测试过程

1. **fpdf2 测试**:
   - 使用 `uni=True` + Hiragino Sans GB.ttc → 乱码（字体子集问题）
   - 去掉 `uni=True` → 中文丢失（完全不渲染）
   - 结论：fpdf2 无法正确生成中文 PDF

2. **weasyprint 测试**:
   - 系统依赖 `libpango-1.0-0` 缺失
   - macOS 安装复杂
   - 结论：作为降级方案，但安装门槛高

3. **reportlab 测试**:
   - 使用 Arial Unicode.ttf → 中文正确
   - 文本提取验证：内容完整
   - 结论：首选方案

## 决策

使用 **reportlab** 作为 PDF 生成首选方案，**Arial Unicode.ttf** 作为字体。

**优先级**:
1. reportlab（首选）
2. weasyprint（降级，需要系统依赖）
3. fpdf2（最后手段，中文可能乱码）

## 影响

- `backend/utils/file_converter.py` 已修改
- 需要安装 `reportlab` 依赖
- 新增依赖: `pip install reportlab`

## 代码变更

```python
# 新方案
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('ArialUnicode', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
c = canvas.Canvas(str(output_path))
c.setFont('ArialUnicode', 12)
c.drawString(100, 700, text)
c.save()
```

## 注意事项

- 字体文件路径是系统依赖（macOS 路径）
- 如果部署到 Linux，需要更换字体路径
- 可以考虑将字体文件放入项目目录

## 后续

- 监控 reportlab 的性能和稳定性
- 如果未来需要更复杂的排版（HTML/CSS），可以重新评估 weasyprint
- 考虑将字体文件打包到项目中，避免系统依赖

---

**相关文件**: `backend/utils/file_converter.py`
