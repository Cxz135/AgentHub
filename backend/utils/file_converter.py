#file_converter.py
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class FileConversionError(Exception):
    """文件转换异常基类"""
    pass


def from_pdf(file_path: str) -> Optional[str]:
    """
    从PDF提取文本，返回转换后的TXT文件路径
    依赖: pip install pymupdf
    """
    try:
        import fitz  # PyMuPDF
        input_path = Path(file_path).resolve()
        if not input_path.exists():
            raise FileConversionError(f"输入文件不存在: {file_path}")
        if input_path.suffix.lower() != ".pdf":
            raise FileConversionError(f"输入文件不是PDF格式: {file_path}")

        # 提取文本并保存
        output_path = input_path.parent / f"{input_path.stem}.txt"
        text = ""
        with fitz.open(input_path) as doc:
            for page in doc:
                text += page.get_text()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"✅ PDF转TXT成功: {input_path} -> {output_path}")
        return str(output_path)
    except ImportError:
        logger.error("请先安装PyMuPDF: pip install pymupdf")
        raise FileConversionError("缺少依赖库pymupdf")
    except Exception as e:
        logger.error(f"PDF转TXT失败: {e}")
        raise FileConversionError(f"转换失败: {str(e)}")


def to_pdf(file_path_or_content: str, output_dir: str = None, user_id: int = 0) -> Optional[str]:
    """
    将Markdown文本内容转成PDF文件，返回可下载的URL。
    
    当用户要求生成PDF、报告、文档时，直接调用此工具，将markdown文本内容作为输入，
    工具会自动生成PDF文件并返回可下载的URL。
    
    Args:
        file_path_or_content: 完整的markdown文本内容（不需要先写入文件），或已有文件路径
        output_dir: 可选，输出目录
        user_id: 用户ID，默认0
        
    Returns:
        可下载的PDF URL，格式如 /attachments/{user_id}/{filename}.pdf
    """


    import tempfile
    import hashlib
    import shutil
    import os
    import uuid

    content = None
    input_path = Path(file_path_or_content)
    is_content_mode = False

    # 检测输入是内容还是文件路径
    # 规则：输入长度超过500字节（正常路径不会这么长），或者路径不存在
    # 注意：必须先检查长度，因为 Path.exists() 对超长字符串会抛 OSError
    input_len = len(file_path_or_content.encode('utf-8'))
    if input_len > 500:
        is_content_mode = True
    elif not input_path.exists():
        is_content_mode = True

    if is_content_mode:
        content = file_path_or_content
        stem = hashlib.md5(content[:200].encode('utf-8')).hexdigest()[:12]
        if output_dir:
            output_dir_path = Path(output_dir)
        else:
            output_dir_path = Path(tempfile.gettempdir())
        output_path = output_dir_path / f"{stem}.pdf"
        input_path_display = f"<content:{len(content)}chars>"
    else:
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise FileConversionError(f"输入文件不存在: {file_path_or_content}")
        except OSError as e:
            if e.errno == 63:
                raise FileConversionError(f"文件名过长无法读取: {file_path_or_content}")
            raise

        stem = input_path.stem
        max_len = 200
        if len(stem.encode('utf-8')) > max_len:
            stem = hashlib.md5(stem.encode('utf-8')).hexdigest()[:8]
        if output_dir:
            output_dir_path = Path(output_dir)
        else:
            output_dir_path = input_path.parent
        output_path = output_dir_path / f"{stem}.pdf"
        input_path_display = str(input_path)

    # 注意：Emoji 过滤已删除，因为 reportlab 的 Arial Unicode.ttf 支持大部分字符
    # 如果某些字符导致问题，可以在 reportlab 的写入阶段处理

    # 方案1: 使用 reportlab（支持中文最好，优先使用）
    try:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.pagesizes import A4

        # 注册中文字体（使用 .ttf 格式，reportlab 不支持 .ttc 的 postscript outlines）
        font_candidates = [
            ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "ArialUnicode"),
            ("/System/Library/Fonts/LastResort.ttf", "LastResort"),
        ]
        font_name = None
        for font_path, font_label in font_candidates:
            if Path(font_path).exists():
                try:
                    pdfmetrics.registerFont(TTFont(font_label, font_path))
                    font_name = font_label
                    logger.info(f"[REPORTLAB] 已加载中文字体: {font_label}")
                    break
                except Exception as font_err:
                    logger.warning(f"[REPORTLAB] 字体 {font_path} 加载失败: {font_err}")
                    continue

        if not font_name:
            logger.warning("[REPORTLAB] 未找到中文字体，使用 Helvetica")
            font_name = "Helvetica"

        # 创建 PDF
        c = canvas.Canvas(str(output_path), pagesize=A4)
        width, height = A4
        margin = 50
        y = height - margin
        line_height = 14

        for line in content.split('\n'):
            line = line.strip()
            if not line:
                y -= line_height * 0.5
                continue

            # 设置字体大小
            if line.startswith('# '):
                c.setFont(font_name, 18)
                text = line[2:]
                y -= 6
            elif line.startswith('## '):
                c.setFont(font_name, 14)
                text = line[3:]
                y -= 4
            elif line.startswith('### '):
                c.setFont(font_name, 13)
                text = line[4:]
                y -= 2
            else:
                c.setFont(font_name, 12)
                text = line
                if line.startswith('- ') or line.startswith('* '):
                    text = '• ' + line[2:]
                elif line.startswith('> '):
                    text = line[2:]

            # 处理超长行
            if len(text) > 80:
                text = text[:80] + "..."

            # 写入文本
            c.drawString(margin, y, text)
            y -= line_height

            # 分页
            if y < margin:
                c.showPage()
                y = height - margin

        c.save()
        logger.info(f"✅ 文本/MD转PDF成功(reportlab): {input_path_display} -> {output_path}")
    except Exception as e:
        logger.warning(f"reportlab 不可用({e})，降级到 weasyprint")

        # 方案2: 使用 weasyprint
        try:
            import markdown
            from weasyprint import HTML
            html = markdown.markdown(content)
            HTML(string=html).write_pdf(output_path)
            logger.info(f"✅ 文本/MD转PDF成功(weasyprint): {input_path_display} -> {output_path}")
        except Exception as e2:
            logger.warning(f"weasyprint 不可用({e2})，降级到 fpdf2")

            # 方案3: 使用 fpdf2（最后手段）
            try:
                from fpdf import FPDF
                pdf = FPDF()
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                font_loaded = False
                try:
                    font_candidates = [
                        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "ArialUnicode"),
                    ]
                    for font_path, font_label in font_candidates:
                        if Path(font_path).exists():
                            try:
                                pdf.add_font(font_label, fname=font_path, uni=True)
                                pdf.set_font(font_label, size=12)
                                font_loaded = True
                                logger.info(f"[FPDF2] 已加载字体: {font_label}")
                                break
                            except Exception as font_err:
                                logger.warning(f"[FPDF2] 字体 {font_path} 加载失败: {font_err}")
                                continue
                except Exception as e:
                    logger.warning(f"[FPDF2] 字体检测失败: {e}")

                if not font_loaded:
                    pdf.set_font("Helvetica", size=12)
                    logger.warning("[FPDF2] 未找到中文字体，中文可能显示为方块")

                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        pdf.cell(0, 4, '', ln=True)
                        continue
                    if line.startswith('# '):
                        pdf.set_font_size(18)
                        text = line[2:]
                    elif line.startswith('## '):
                        pdf.set_font_size(14)
                        text = line[3:]
                    elif line.startswith('### '):
                        pdf.set_font_size(13)
                        text = line[4:]
                    else:
                        pdf.set_font_size(12)
                        text = line
                        if line.startswith('- ') or line.startswith('* '):
                            text = '• ' + line[2:]
                        elif line.startswith('> '):
                            pdf.set_text_color(80, 80, 80)
                            text = line[2:]
                    if len(text) > 1000:
                        text = text[:1000] + "..."
                    try:
                        pdf.cell(0, 6, text, ln=True)
                    except Exception as cell_err:
                        logger.warning(f"[FPDF2] 写入行失败，跳过: {cell_err}")
                        continue
                    pdf.set_text_color(0, 0, 0)
                pdf.output(str(output_path))
                logger.info(f"✅ 文本/MD转PDF成功(fpdf2): {input_path_display} -> {output_path}")
            except ImportError:
                logger.error("请先安装依赖: pip install reportlab")
                raise FileConversionError("缺少依赖库")
            except Exception as e:
                logger.error(f"转PDF失败: {e}")
                raise FileConversionError(f"转换失败: {str(e)}")

    # 生成后自动复制到 UPLOAD_DIR 并返回 URL
    try:
        from backend.app.api.attachments import UPLOAD_DIR
        user_dir = os.path.join(UPLOAD_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        ext = os.path.splitext(str(output_path))[-1].lower()
        with open(output_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:8]
        unique_name = f"{file_hash}_{uuid.uuid4().hex[:8]}{ext}"
        dest_path = os.path.join(user_dir, unique_name)
        shutil.copy2(str(output_path), dest_path)
        url = f"/attachments/{user_id}/{unique_name}"
        logger.info(f"✅ PDF已复制到 uploads: {output_path} -> {url}")
        return url
    except Exception as e:
        logger.error(f"[PDF-UPLOAD] 复制到 uploads 失败: {e}")
        return str(output_path)  # 降级返回原始路径


def from_md(file_path: str) -> Optional[str]:
    """从Markdown转纯文本，返回TXT文件路径"""
    try:
        input_path = Path(file_path).resolve()
        if not input_path.exists():
            raise FileConversionError(f"输入文件不存在: {file_path}")
        import markdown
        from bs4 import BeautifulSoup
        with open(input_path, "r", encoding="utf-8") as f:
            md_content = f.read()
        html = markdown.markdown(md_content)
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()
        output_path = input_path.parent / f"{input_path.stem}.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"✅ MD转TXT成功: {input_path} -> {output_path}")
        return str(output_path)
    except ImportError:
        logger.error("请先安装依赖: pip install markdown beautifulsoup4")
        raise FileConversionError("缺少依赖库")
    except Exception as e:
        logger.error(f"MD转TXT失败: {e}")
        raise FileConversionError(f"转换失败: {str(e)}")


def to_md(file_path: str) -> Optional[str]:
    """将纯文本转成格式化的Markdown，返回MD文件路径"""
    try:
        input_path = Path(file_path).resolve()
        if not input_path.exists():
            raise FileConversionError(f"输入文件不存在: {file_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read()
        md_content = text.replace("\\n\\n", "\\n\\n---\\n\\n")
        output_path = input_path.parent / f"{input_path.stem}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"✅ TXT转MD成功: {input_path} -> {output_path}")
        return str(output_path)
    except Exception as e:
        logger.error(f"TXT转MD失败: {e}")
        raise FileConversionError(f"转换失败: {str(e)}")


import tempfile
import hashlib
import os


def save_content_to_file(content: str, filename: str = None, output_format: str = "md") -> str:
    """
    将 AI 生成的内容保存到文件（自动生成短文件名，避免超长路径问题）。

    这是保存 AI 生成内容的正确方式，不要使用 to_pdf/to_md 来保存内容。

    Args:
        content: 要保存的内容（可以是 Markdown、纯文本等）
        filename: 可选，指定文件名（会自动截断超长部分）。如果为 None，则自动生成
        output_format: 输出格式 "md" | "txt" | "pdf"，默认 "md"

    Returns:
        保存后的文件路径

    Example:
        save_content_to_file("# 财报摘要\\n\\n这是内容...", filename="小米财报", output_format="md")
        -> "/tmp/xiaomi_cai_wu.md"
    """
    if not content or not content.strip():
        raise FileConversionError("内容不能为空")

    # 生成短文件名
    if filename:
        # 截断超长文件名
        safe_name = filename[:50].strip()
        # 移除非法字符
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in (' ', '_', '-', '。', '，')).strip()
        if not safe_name:
            safe_name = "output"
    else:
        # 自动生成：使用内容前30字的MD5
        safe_name = hashlib.md5(content[:100].encode('utf-8')).hexdigest()[:12]

    # 确保有正确的扩展名
    ext_map = {"md": ".md", "txt": ".txt", "pdf": ".pdf", "html": ".html"}
    ext = ext_map.get(output_format.lower(), ".md")
    if not safe_name.endswith(ext):
        safe_name += ext

    # 保存到临时目录
    output_dir = tempfile.gettempdir()
    output_path = os.path.join(output_dir, safe_name)

    # 如果文件已存在，用更唯一的名字
    if os.path.exists(output_path):
        unique_suffix = hashlib.md5(str(os.path.getmtime(output_path)).encode()).hexdigest()[:4]
        name_part = os.path.splitext(safe_name)[0]
        output_path = os.path.join(output_dir, f"{name_part}_{unique_suffix}{ext}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"✅ 内容已保存到文件: {output_path} ({len(content)} 字符)")
    return output_path


# 暴露所有可用的转换函数
__all__ = ["from_pdf", "to_pdf", "from_md", "to_md", "save_content_to_file", "FileConversionError"]