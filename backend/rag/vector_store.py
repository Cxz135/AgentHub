#rag/vector_store.py


from langchain_chroma import Chroma
from backend.utils.config_handler import chroma_config
from typing import Optional
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_community.embeddings import DashScopeEmbeddings
from backend.utils.path_tool import get_abs_path
from backend.utils.file_handler import txt_loader, pdf_loader, listdir_with_allowed_type, get_file_md5_hex
from backend.utils.logger import logger
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from datetime import datetime


import os
import json

load_dotenv()
class EmbeddingsFactory:
    def generator(self) -> Embeddings:
        return DashScopeEmbeddings(model = "text-embedding-v4",
                                   dashscope_api_key=os.getenv("DASHSCOPE_API_KEY"),)

embed_model = EmbeddingsFactory().generator()


class VectorStoreService:
    def __init__(self):
        os.makedirs(chroma_config["persist_directory"], exist_ok=True)
        self.vector_store = Chroma(
            collection_name = "all_documents",
            embedding_function = embed_model,
            persist_directory = chroma_config["persist_directory"],
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size = chroma_config["chunk_size"],
            chunk_overlap = chroma_config["chunk_overlap"],
            separators = chroma_config["separators"],
        )
        self.mapping_file = "data/doc_mapping.json"
        self.doc_mapping = self._load_mapping()

    def _load_mapping(self):
        """加载文档ID和文件路径的映射"""
        if os.path.exists(self.mapping_file):
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}


    def load_document(self):

        def check_md5_hex(md5_for_check: str):
            if not os.path.exists(get_abs_path(chroma_config["md5_hex_store"])):
                open(get_abs_path(chroma_config["md5_hex_store"]), "w", encoding="utf-8").close()
                return False

            with open(get_abs_path(chroma_config["md5_hex_store"]), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line == md5_for_check:
                        return True
                return False

        def save_md5_hex(md5_for_check: str):
            with open(get_abs_path(chroma_config["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")
                f.close()

        def get_file_documents(read_path: str):
            if read_path.endswith(".txt"):
                return txt_loader(read_path)
            elif read_path.endswith(".pdf"):
                return pdf_loader(read_path)
            return []

        allowed_file_path: list[str] = listdir_with_allowed_type(
            get_abs_path(chroma_config["data_path"]),
            tuple(chroma_config["allowed_files_type"]),
        )

        for path in allowed_file_path:
            md5_hex = get_file_md5_hex(path)

            if check_md5_hex(md5_hex):
                logger.info(f"{path} exists already, skip.")
                continue

            try:
                documents: list[Document] = get_file_documents(path)
                if not documents:
                    logger.warning(f"{path} has no documents, skip.")
                    continue

                split_document: list[Document] = self.splitter.split_documents(documents)

                if not split_document:
                    logger.warning(f"{path} has no documents, skip.")
                    continue

                self.vector_store.add_documents(split_document)
                save_md5_hex(md5_hex)
                logger.info(f"{path} has documents added successfully.")

            except Exception as e:
                logger.error("Fail to load {path}: {str(e)}", exc_info=True)
                continue

    def get_retriever(self, course: str, user_id: Optional[str] = 'default'):
        """
        获取检索器，可按课程/用户过滤
        """

        search_kwargs = {"k": 5}
        if not course:
            course = "未分类"
            logger.warning(f"未指定课程，使用默认: {course}")

            # 构建过滤条件
        filter_dict = {
            "$and": [
                {"course": {"$eq": course}},
                {"user_id": {"$eq": user_id or "default"}}
            ]
        }

        search_kwargs["filter"] = filter_dict
        logger.info(f"🔍 检索过滤条件: course={course}, user_id={user_id}")

        return self.vector_store.as_retriever(search_kwargs=search_kwargs)

    def _save_mapping(self):
        """保存文档映射"""
        os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.doc_mapping, f, ensure_ascii=False, indent=2)

    def add_document(self, file_path: str, course: str, user_id: str = "default") -> list:
        """
        添加文档到向量库
        :param file_path: 文件路径
        :param course: 课程名称
        :param user_id: 用户ID
        :return: 文档ID列表
        """
        # 1. 加载文档
        if file_path.endswith('.pdf'):
            documents = pdf_loader(file_path)
        elif file_path.endswith('.txt'):
            documents = txt_loader(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {file_path}")

        # 2. 添加元数据
        for doc in documents:
            doc.metadata.update({
                "course": course,
                "user_id": user_id,
                "source": os.path.basename(file_path),
                "upload_time": str(datetime.now())
            })

        # 3. 分割
        splits = self.splitter.split_documents(documents)

        # 4. 添加到向量库
        ids = self.vector_store.add_documents(splits)

        # 5. 保存映射关系
        file_key = f"{user_id}:{course}:{os.path.basename(file_path)}"
        self.doc_mapping[file_key] = {
            "doc_ids": ids,
            "file_path": file_path,
            "course": course,
            "user_id": user_id,
            "upload_time": str(datetime.now())
        }
        self._save_mapping()

        logger.info(f"✅ 文档已添加到课程【{course}】：{os.path.basename(file_path)}")
        return ids

    def delete_document(self, file_path: str, course: str, user_id: str = "default") -> bool:
        """
        从向量库删除文档
        :param file_path: 文件路径
        :param course: 课程名称
        :param user_id: 用户ID
        :return: 是否成功
        """
        try:
            # 查找对应的文档ID
            file_key = f"{user_id}:{course}:{os.path.basename(file_path)}"
            mapping = self.doc_mapping.get(file_key)

            if mapping and mapping.get("doc_ids"):
                # 从向量库删除
                self.vector_store.delete(ids=mapping["doc_ids"])

                # 删除映射记录
                del self.doc_mapping[file_key]
                self._save_mapping()

                logger.info(f"✅ 已从向量库删除文档: {file_path}")
                return True
            else:
                logger.warning(f"未找到文档映射: {file_path}")
                return False

        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    def delete_course_documents(self, course: str, user_id: str) -> bool:
        """
        删除课程的所有文档
        """
        try:
            # 找出该课程的所有文档
            to_delete = []
            for key, mapping in list(self.doc_mapping.items()):
                if mapping.get("course") == course and mapping.get("user_id") == user_id:
                    if mapping.get("doc_ids"):
                        to_delete.extend(mapping["doc_ids"])
                    del self.doc_mapping[key]

            if to_delete:
                # 从向量库删除
                self.vector_store.delete(ids=to_delete)
                self._save_mapping()
                logger.info(f"✅ 已删除课程【{course}】的 {len(to_delete)} 个文档片段")

            return True

        except Exception as e:
            logger.error(f"删除课程文档失败: {e}")
            return False


