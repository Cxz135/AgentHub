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


def to_pdf(file_path: str) -> Optional[str]:
    """
    将Markdown/文本转成PDF，返回生成的PDF路径
    依赖: pip install markdown weasyprint
    """
    try:
        import markdown
        from weasyprint import HTML
        input_path = Path(file_path).resolve()
        if not input_path.exists():
            raise FileConversionError(f"输入文件不存在: {file_path}")

        # 先转成HTML，再生成PDF
        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()
        html = markdown.markdown(content)
        output_path = input_path.parent / f"{input_path.stem}.pdf"
        HTML(string=html).write_pdf(output_path)
        logger.info(f"✅ 文本/MD转PDF成功: {input_path} -> {output_path}")
        return str(output_path)
    except ImportError:
        logger.error("请先安装依赖: pip install markdown weasyprint")
        raise FileConversionError("缺少依赖库markdown/weasyprint")
    except Exception as e:
        logger.error(f"转PDF失败: {e}")
        raise FileConversionError(f"转换失败: {str(e)}")


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
        # 简单格式化，给段落加换行，支持基础的MD格式化
        md_content = text.replace("\\n\\n", "\\n\\n---\\n\\n")
        output_path = input_path.parent / f"{input_path.stem}.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"✅ TXT转MD成功: {input_path} -> {output_path}")
        return str(output_path)
    except Exception as e:
        logger.error(f"TXT转MD失败: {e}")
        raise FileConversionError(f"转换失败: {str(e)}")


# 暴露所有可用的转换函数
__all__ = ["from_pdf", "to_pdf", "from_md", "to_md", "FileConversionError"]