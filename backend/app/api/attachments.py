# app/api/attachments.py
"""
聊天附件与网页预览 API

功能：
- 文件上传（图片、文档、附件）
- 网页预览卡片解析（URL → 标题/描述/图片/图标）
"""

import os
import uuid
import hashlib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import requests

from backend.app.dependencies import get_db
from backend.app.api.auth import get_current_user
from backend.models.user import User as UserModel
from backend.utils.logger import logger

router = APIRouter()

# 上传目录
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'attachments')
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg',  # 图片
    '.pdf', '.txt', '.md', '.docx', '.xlsx', '.pptx', '.csv', '.json', '.zip',  # 文档/附件
    '.mp3', '.mp4', '.wav', '.webm', '.mov',  # 音视频
}


def _ensure_upload_dir(user_id: int):
    path = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[-1].lower()
    return ext in ALLOWED_EXTENSIONS


def _save_file(content: bytes, user_id: int, original_name: str) -> dict:
    """保存文件到磁盘，返回元数据"""
    user_dir = _ensure_upload_dir(user_id)
    file_hash = hashlib.md5(content).hexdigest()[:8]
    ext = os.path.splitext(original_name)[-1].lower()
    unique_name = f"{file_hash}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(user_dir, unique_name)
    with open(file_path, 'wb') as f:
        f.write(content)
    return {
        "filename": unique_name,
        "original_name": original_name,
        "path": file_path,
        "size": len(content),
        "mime_type": _guess_mime_type(ext),
    }


def _guess_mime_type(ext: str) -> str:
    mapping = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
        '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
        '.pdf': 'application/pdf', '.txt': 'text/plain', '.md': 'text/markdown',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.csv': 'text/csv', '.json': 'application/json', '.zip': 'application/zip',
        '.mp3': 'audio/mpeg', '.mp4': 'video/mp4', '.wav': 'audio/wav',
        '.webm': 'video/webm', '.mov': 'video/quicktime',
    }
    return mapping.get(ext, 'application/octet-stream')


def _is_image(ext: str) -> bool:
    return ext.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    上传文件（图片、文档、附件）
    返回文件元数据，供前端插入到消息中。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件名")

    if not _allowed_file(file.filename):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {os.path.splitext(file.filename)[-1]}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")

    meta = _save_file(content, current_user.id, file.filename)
    ext = os.path.splitext(file.filename)[-1].lower()
    is_image = _is_image(ext)

    # 构建相对 URL（前端通过 /attachments/{user_id}/{filename} 访问）
    relative_url = f"/attachments/{current_user.id}/{meta['filename']}"

    logger.info(f"📎 用户{current_user.id} 上传文件: {meta['original_name']} ({meta['size']} bytes)")

    return {
        "ok": True,
        "file": {
            "url": relative_url,
            "original_name": meta['original_name'],
            "size": meta['size'],
            "mime_type": meta['mime_type'],
            "is_image": is_image,
        }
    }


@router.get("/attachments/{user_id}/{filename}/download")
async def download_file(
    user_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    认证下载文件。
    仅允许文件所有者或同一会话参与者下载。
    """
    # 权限检查：只能下载自己的文件，或者管理员
    if current_user.id != user_id and not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="无权下载此文件")

    file_path = os.path.join(UPLOAD_DIR, str(user_id), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    # 防止目录遍历
    real_path = os.path.realpath(file_path)
    upload_base = os.path.realpath(UPLOAD_DIR)
    if not real_path.startswith(upload_base):
        raise HTTPException(status_code=403, detail="非法路径")

    ext = os.path.splitext(filename)[-1].lower()
    mime_type = _guess_mime_type(ext)
    original_name = filename.split('_', 1)[-1] if '_' in filename else filename
    # 尝试从原始文件名中提取（如果有的话）

    from fastapi.responses import FileResponse
    return FileResponse(
        file_path,
        media_type=mime_type,
        filename=original_name,
        headers={"Content-Disposition": f'attachment; filename="{original_name}"'}
    )


@router.post("/preview")
async def preview_url(
    url: str = Form(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    解析网页 URL，返回预览卡片数据（标题、描述、图片、图标）
    """
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="无效的 URL")

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[PREVIEW] 抓取 URL 失败: {url} - {e}")
        raise HTTPException(status_code=400, detail=f"无法抓取该 URL: {e}")

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')

        title = soup.find('title')
        title = title.get_text(strip=True) if title else url

        description = None
        meta_desc = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
        if meta_desc:
            description = meta_desc.get('content', '')
        if not description:
            # 尝试从第一个 p 标签提取
            first_p = soup.find('p')
            if first_p:
                description = first_p.get_text(strip=True)[:200]

        image = None
        og_image = soup.find('meta', attrs={'property': 'og:image'})
        if og_image:
            image = og_image.get('content', '')
        if not image:
            # 尝试找第一个大图片
            img = soup.find('img', src=True)
            if img:
                src = img['src']
                if src.startswith('http'):
                    image = src
                elif src.startswith('/'):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    image = f"{parsed.scheme}://{parsed.netloc}{src}"

        favicon = None
        icon_link = soup.find('link', rel=lambda x: x and 'icon' in x.lower())
        if icon_link:
            favicon = icon_link.get('href', '')
        if not favicon:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            favicon = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

        provider = None
        og_site = soup.find('meta', attrs={'property': 'og:site_name'})
        if og_site:
            provider = og_site.get('content', '')
        if not provider:
            from urllib.parse import urlparse
            provider = urlparse(url).netloc

        return {
            "ok": True,
            "preview": {
                "url": url,
                "title": title,
                "description": description or '',
                "image": image,
                "favicon": favicon,
                "provider": provider,
            }
        }
    except Exception as e:
        logger.error(f"[PREVIEW] 解析 HTML 失败: {url} - {e}")
        raise HTTPException(status_code=500, detail=f"解析网页失败: {e}")
