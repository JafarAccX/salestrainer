import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from config import config
from core.atomic_json import atomic_read, atomic_write


class DocumentStore:
    def __init__(self):
        self.base_dir = Path(config.KB_STORE_DIR)
        self.modules_file = self.base_dir / "modules.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.modules_file.exists():
            self._write_modules([])
        self._seed_core_modules()

    def _seed_core_modules(self):
        core_module_names = ["Product Knowledge", "Objection Handling", "Communication", "Closures"]
        modules = self._read_modules()
        existing_names = [m["name"] for m in modules]
        
        changed = False
        for name in core_module_names:
            if name not in existing_names:
                module = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "description": f"Core training module: {name}",
                    "documents": [],
                    "created_at": self._now(),
                    "updated_at": self._now(),
                }
                modules.append(module)
                (self.base_dir / module["id"]).mkdir(parents=True, exist_ok=True)
                changed = True
        
        if changed:
            self._write_modules(modules)

    def list_modules(self) -> list[dict[str, Any]]:
        return self._read_modules()

    def get_module(self, module_id: str) -> dict[str, Any] | None:
        return next((module for module in self._read_modules() if module["id"] == module_id), None)

    def create_module(self, name: str, description: str = "") -> dict[str, Any]:
        modules = self._read_modules()
        module = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "documents": [],
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        modules.append(module)
        self._write_modules(modules)
        (self.base_dir / module["id"]).mkdir(parents=True, exist_ok=True)
        return module

    def update_module(self, module_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any] | None:
        modules = self._read_modules()
        for module in modules:
            if module["id"] == module_id:
                if name is not None:
                    module["name"] = name
                if description is not None:
                    module["description"] = description
                module["updated_at"] = self._now()
                self._write_modules(modules)
                return module
        return None

    def delete_module(self, module_id: str) -> dict[str, Any] | None:
        modules = self._read_modules()
        module = next((item for item in modules if item["id"] == module_id), None)
        if not module:
            return None
        remaining = [item for item in modules if item["id"] != module_id]
        self._write_modules(remaining)
        shutil.rmtree(self.base_dir / module_id, ignore_errors=True)
        return module

    async def add_document(self, module_id: str, file: UploadFile) -> dict[str, Any] | None:
        modules = self._read_modules()
        module = next((item for item in modules if item["id"] == module_id), None)
        if not module:
            return None

        document_id = str(uuid.uuid4())
        filename = self._safe_filename(file.filename or f"{document_id}.pdf")
        extension = Path(filename).suffix.lower()
        stored_name = f"{document_id}{extension}"
        module_dir = self.base_dir / module_id
        module_dir.mkdir(parents=True, exist_ok=True)
        file_path = module_dir / stored_name

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        document = {
            "id": document_id,
            "module_id": module_id,
            "filename": filename,
            "path": str(file_path),
            "content_type": file.content_type,
            "size_bytes": file_path.stat().st_size,
            "status": "uploaded",
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        module["documents"].append(document)
        module["updated_at"] = self._now()
        self._write_modules(modules)
        return document

    def mark_document_indexed(self, module_id: str, document_id: str, chunk_count: int) -> dict[str, Any] | None:
        return self._update_document(module_id, document_id, {"status": "indexed", "chunk_count": chunk_count})

    def mark_document_failed(self, module_id: str, document_id: str, error: str) -> dict[str, Any] | None:
        return self._update_document(module_id, document_id, {"status": "failed", "error": error})

    def delete_document(self, module_id: str, document_id: str) -> dict[str, Any] | None:
        modules = self._read_modules()
        for module in modules:
            if module["id"] != module_id:
                continue
            document = next((item for item in module["documents"] if item["id"] == document_id), None)
            if not document:
                return None
            module["documents"] = [item for item in module["documents"] if item["id"] != document_id]
            module["updated_at"] = self._now()
            self._write_modules(modules)
            try:
                Path(document["path"]).unlink(missing_ok=True)
            except OSError:
                pass
            return document
        return None

    def _update_document(self, module_id: str, document_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        modules = self._read_modules()
        for module in modules:
            if module["id"] != module_id:
                continue
            for document in module["documents"]:
                if document["id"] == document_id:
                    document.update(updates)
                    document["updated_at"] = self._now()
                    module["updated_at"] = self._now()
                    self._write_modules(modules)
                    return document
        return None

    def _read_modules(self) -> list[dict[str, Any]]:
        return atomic_read(self.modules_file)

    def _write_modules(self, modules: list[dict[str, Any]]) -> None:
        atomic_write(self.modules_file, modules)

    def _safe_filename(self, filename: str) -> str:
        allowed = [char for char in filename if char.isalnum() or char in "._- "]
        cleaned = "".join(allowed).strip()
        return cleaned or "document.pdf"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


document_store = DocumentStore()
