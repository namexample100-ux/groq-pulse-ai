import fitz  # PyMuPDF
import logging
import io

log = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Извлекает текст из PDF файла."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text.strip()
        except Exception as e:
            log.error(f"Error parsing PDF: {e}")
            return f"⚠️ Ошибка при чтении PDF: {str(e)}"

    @staticmethod
    async def extract_text_from_txt(txt_bytes: bytes) -> str:
        """Извлекает текст из TXT файла."""
        try:
            return txt_bytes.decode('utf-8', errors='ignore').strip()
        except Exception as e:
            log.error(f"Error parsing TXT: {e}")
            return f"⚠️ Ошибка при чтении TXT: {str(e)}"

    async def get_document_content(self, file_bytes: bytes, file_name: str) -> str:
        """Определяет тип файла и извлекает контент."""
        if file_name.lower().endswith('.pdf'):
            return await self.extract_text_from_pdf(file_bytes)
        elif file_name.lower().endswith('.txt'):
            return await self.extract_text_from_txt(file_bytes)
        else:
            return "❌ Поддерживаются только PDF и TXT файлы."

doc_tool = DocumentService()
