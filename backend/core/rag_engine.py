import os
from pathlib import Path
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from config import config

class RAGEngine:
    def __init__(self):
        # Initialize embeddings using a fast, local HuggingFace model
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={},
        )
        self.persist_directory = config.VECTOR_DB_DIR
        self.collection_name = "sales_knowledge"
        
        # Initialize Chroma DB
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=100,
            length_function=len
        )

    def process_document(self, file_path, module_id=None, document_id=None):
        """Extracts text from PDF, splits it, and adds to ChromaDB."""
        try:
            documents = self._load_documents(file_path)
            
            # Split documents into chunks
            chunks = self.text_splitter.split_documents(documents)
            if not chunks:
                return False, "No text could be extracted from the document. It might be a scanned PDF or empty.", 0

            for chunk_index, chunk in enumerate(chunks):
                chunk.metadata.update({
                    "module_id": module_id or "default",
                    "document_id": document_id or Path(file_path).stem,
                    "source": file_path,
                    "chunk_index": chunk_index,
                    "filename": Path(file_path).name,
                })
            
            # Add chunks to vector store
            self.vector_store.add_documents(chunks)
            
            return True, f"Successfully processed and embedded {len(chunks)} chunks.", len(chunks)
        except Exception as e:
            print(f"Error processing document: {e}")
            return False, str(e), 0

    def retrieve_context(self, query, top_k=3, module_id=None):
        """Retrieves most relevant chunks for a given query."""
        try:
            filter_kwargs = {"module_id": module_id} if module_id else None
            results = self.vector_store.similarity_search(query, k=top_k, filter=filter_kwargs)
            context = "\n\n".join([doc.page_content for doc in results])
            return context
        except Exception as e:
            print(f"Error retrieving context: {e}")
            return ""

    def get_all_context_for_module(self, module_id, max_chars=20000):
        """Retrieves all document chunks for a module, up to a char limit, for summarization/curriculum generation."""
        try:
            matches = self.vector_store.get(where={"module_id": module_id})
            docs = matches.get("documents", [])
            if not docs:
                return ""
            
            # Combine chunks until we hit the character limit
            full_text = ""
            for text in docs:
                if len(full_text) + len(text) > max_chars:
                    break
                full_text += text + "\n\n"
            return full_text.strip()
        except Exception as e:
            print(f"Error retrieving all module context: {e}")
            return ""

    def delete_document_vectors(self, module_id, document_id):
        try:
            matches = self.vector_store.get(where={"$and": [{"module_id": module_id}, {"document_id": document_id}]})
            ids = matches.get("ids", [])
            if ids:
                self.vector_store.delete(ids=ids)
            return True, len(ids)
        except Exception as e:
            print(f"Error deleting document vectors: {e}")
            return False, 0

    def delete_module_vectors(self, module_id):
        try:
            matches = self.vector_store.get(where={"module_id": module_id})
            ids = matches.get("ids", [])
            if ids:
                self.vector_store.delete(ids=ids)
            return True, len(ids)
        except Exception as e:
            print(f"Error deleting module vectors: {e}")
            return False, 0

    def _load_documents(self, file_path):
        suffix = Path(file_path).suffix.lower()
        if suffix == ".pdf":
            return PyMuPDFLoader(file_path).load()
        if suffix in {".txt", ".md"}:
            text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
            return [Document(page_content=text, metadata={"source": file_path})]
        raise ValueError("Only PDF, TXT, and Markdown files are supported.")

rag_engine = RAGEngine()
