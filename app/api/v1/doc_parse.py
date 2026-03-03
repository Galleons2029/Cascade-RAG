# -*- coding: utf-8 -*-
# @Time    : 2025/07/08 3:19 AM
# @Author  : Galleons
# @File    : doc_parse.py

"""
文件解析 API
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
import os
import io
from abc import ABC, abstractmethod

router = APIRouter()


class ParseResponse(BaseModel):
    content: str


# 抽象基类
class DocumentParser(ABC):
    @abstractmethod
    async def parse(self, file: UploadFile) -> str:
        pass


# 各类型解析器
class TxtParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        content = await file.read()
        return content.decode("utf-8", errors="ignore")


class MdParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        content = await file.read()
        return content.decode("utf-8", errors="ignore")


class JsonParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        content = await file.read()
        return content.decode("utf-8", errors="ignore")


class CsvParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        content = await file.read()
        return content.decode("utf-8", errors="ignore")


class PdfParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        try:
            import PyPDF2
        except ImportError:
            raise HTTPException(status_code=500, detail="PyPDF2 is not installed. Please install it.")
        content = await file.read()
        with io.BytesIO(content) as pdf_stream:

            def extract():
                reader = PyPDF2.PdfReader(pdf_stream)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                return text

            return await run_in_threadpool(extract)


class DocxParser(DocumentParser):
    async def parse(self, file: UploadFile) -> str:
        try:
            import docx
        except ImportError:
            raise HTTPException(status_code=500, detail="python-docx is not installed. Please install it.")
        content = await file.read()
        with io.BytesIO(content) as docx_stream:

            def extract():
                doc = docx.Document(docx_stream)
                text = "\n".join([para.text for para in doc.paragraphs])
                return text

            return await run_in_threadpool(extract)


# 工厂类
class DocumentParserFactory:
    _parsers = {
        "txt": TxtParser(),
        "md": MdParser(),
        "json": JsonParser(),
        "csv": CsvParser(),
        "pdf": PdfParser(),
        "docx": DocxParser(),
    }

    @staticmethod
    def get_parser(ext: str) -> DocumentParser:
        parser = DocumentParserFactory._parsers.get(ext)
        if not parser:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {ext}")
        return parser


def get_ext(filename: str) -> str:
    return os.path.splitext(filename)[-1][1:].lower()


@router.post("/parse", response_model=ParseResponse)
async def parse_document(file: UploadFile = File(...)):
    ext = get_ext(file.filename)
    parser = DocumentParserFactory.get_parser(ext)
    content = await parser.parse(file)
    return ParseResponse(content=content)
