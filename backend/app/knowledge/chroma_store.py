"""ChromaDB vector store (OpenExecutive-style, skills-focused)."""
from __future__ import annotations

import logging
import os
import shutil
import tarfile
import threading
from pathlib import Path
from typing import Any

_EMBED_BATCH = 4
_embedding_function_lock = threading.Lock()
_shared_embedding_function: Any = None
_log = logging.getLogger(__name__)

_ONNX_FILES = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "vocab.txt",
)
_ARCHIVE = "onnx.tar.gz"
_PART = "onnx.tar.gz.part"


def _chroma_default_cache() -> Path:
    return Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"


def _app_cache() -> Path:
    from app.core.config import DATA_DIR

    return DATA_DIR / "chroma_cache"


def _candidate_cache_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("CHROMA_CACHE_DIR")
    if env:
        dirs.append(Path(env).expanduser())
    dirs.append(_chroma_default_cache())
    dirs.append(_app_cache())
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d.resolve()) if d.exists() else str(d)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _extracted_complete(cache_dir: Path) -> bool:
    extracted = cache_dir / "onnx"
    return all((extracted / f).is_file() for f in _ONNX_FILES)


def _resolve_onnx_cache_dir() -> Path:
    """Prefer an existing local model; otherwise use a stable writable cache."""
    for d in _candidate_cache_dirs():
        if _extracted_complete(d):
            _log.info("Using existing Chroma ONNX model at %s", d)
            return d

    env = os.environ.get("CHROMA_CACHE_DIR")
    if env:
        path = Path(env).expanduser()
    else:
        # Prefer Chroma's default home cache so Docker/local share one copy.
        path = _chroma_default_cache()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _find_local_archive(sha: str) -> Path | None:
    """Return a complete onnx.tar.gz if one already exists locally."""
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import _verify_sha256

    for d in _candidate_cache_dirs():
        archive = d / _ARCHIVE
        if archive.is_file() and _verify_sha256(str(archive), sha):
            return archive
    return None


def _find_partial_download() -> Path | None:
    """Largest incomplete download across cache dirs (resume from furthest progress)."""
    best: Path | None = None
    best_size = 0
    for d in _candidate_cache_dirs():
        for name in (_PART, _ARCHIVE):
            path = d / name
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > best_size:
                best, best_size = path, size
    return best


def _remote_size(url: str) -> int | None:
    import httpx

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code >= 400:
                resp = client.get(url, headers={"Range": "bytes=0-0"})
            length = resp.headers.get("content-length")
            if resp.status_code == 206:
                content_range = resp.headers.get("content-range") or ""
                # bytes 0-0/79300000
                if "/" in content_range:
                    total = content_range.rsplit("/", 1)[-1]
                    if total.isdigit():
                        return int(total)
            if length and length.isdigit():
                return int(length)
    except Exception:
        _log.debug("Could not probe Chroma ONNX remote size", exc_info=True)
    return None


def _download_resumable(url: str, dest: Path, expected_sha: str) -> None:
    """Download onnx.tar.gz into dest, resuming from a local .part / partial file."""
    import httpx
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import _verify_sha256
    from tqdm import tqdm

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(_PART)

    # Migrate Chroma's incomplete onnx.tar.gz into the .part file we resume.
    if dest.is_file() and not _verify_sha256(str(dest), expected_sha):
        if not part.is_file() or part.stat().st_size < dest.stat().st_size:
            dest.replace(part)
        else:
            dest.unlink(missing_ok=True)

    remote = _remote_size(url)
    offset = part.stat().st_size if part.is_file() else 0
    if remote is not None and offset > remote:
        _log.warning("Discarding oversized Chroma ONNX partial (%s > %s)", offset, remote)
        part.unlink(missing_ok=True)
        offset = 0

    if remote is not None and offset == remote and part.is_file():
        if _verify_sha256(str(part), expected_sha):
            part.replace(dest)
            return
        _log.warning("Chroma ONNX partial matches size but not SHA; restarting download")
        part.unlink(missing_ok=True)
        offset = 0

    headers = {"Range": f"bytes={offset}-"} if offset else {}
    mode = "ab" if offset else "wb"
    if offset:
        _log.info("Resuming Chroma ONNX download from %s (%s bytes cached)", part, offset)
    else:
        _log.info("Downloading Chroma ONNX model to %s", part)

    with httpx.stream("GET", url, headers=headers, timeout=None, follow_redirects=True) as resp:
        resp.raise_for_status()
        if offset and resp.status_code == 200:
            # Server ignored Range — restart cleanly.
            _log.warning("Remote ignored Range; restarting Chroma ONNX download")
            part.unlink(missing_ok=True)
            offset = 0
            mode = "wb"
        total_header = resp.headers.get("content-length")
        total = int(total_header) + offset if total_header and total_header.isdigit() else remote
        with open(part, mode) as file, tqdm(
            desc=str(dest),
            total=total,
            initial=offset,
            unit="iB",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for data in resp.iter_bytes(chunk_size=1024 * 64):
                file.write(data)
                bar.update(len(data))

    if not _verify_sha256(str(part), expected_sha):
        # Keep the partial for a later resume if the size still looks short.
        size = part.stat().st_size if part.is_file() else 0
        if remote is not None and size < remote:
            raise ValueError(
                f"Chroma ONNX download incomplete ({size}/{remote} bytes); will resume next start"
            )
        part.unlink(missing_ok=True)
        raise ValueError(
            f"Downloaded file {part} does not match expected SHA256 hash. Corrupted download."
        )

    part.replace(dest)


def _mirror_verified_archive(archive: Path) -> None:
    """Keep a second verified copy under DATA_DIR so restarts/Docker can reuse it."""
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import _verify_sha256
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    sha = ONNXMiniLM_L6_V2._MODEL_SHA256
    for d in (_chroma_default_cache(), _app_cache()):
        target = d / _ARCHIVE
        if target.resolve() == archive.resolve():
            continue
        if target.is_file() and _verify_sha256(str(target), sha):
            continue
        try:
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, target)
            _log.info("Mirrored Chroma ONNX archive to %s", target)
        except OSError:
            _log.debug("Could not mirror Chroma ONNX archive to %s", target, exc_info=True)


def _embedding_function() -> Any:
    global _shared_embedding_function
    with _embedding_function_lock:
        if _shared_embedding_function is None:
            _shared_embedding_function = _build_embedding_function()
        return _shared_embedding_function


def _build_embedding_function() -> Any:
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import _verify_sha256

    cache_dir = _resolve_onnx_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    class _SharedMiniLM(ONNXMiniLM_L6_V2):  # type: ignore[misc]
        DOWNLOAD_PATH = str(cache_dir)
        _session: Any = None
        _session_lock = threading.Lock()

        @staticmethod
        def name() -> str:
            return "default"

        def get_config(self) -> dict[str, Any]:
            return {}

        def _download_model_if_not_exists(self) -> None:
            if _extracted_complete(Path(self.DOWNLOAD_PATH)):
                return

            dest = Path(self.DOWNLOAD_PATH)
            dest.mkdir(parents=True, exist_ok=True)
            archive = dest / self.ARCHIVE_FILENAME

            # Prefer a verified archive from any local cache.
            if not archive.is_file() or not _verify_sha256(str(archive), self._MODEL_SHA256):
                local = _find_local_archive(self._MODEL_SHA256)
                if local is not None and local.resolve() != archive.resolve():
                    _log.info("Copying local Chroma ONNX archive from %s", local)
                    shutil.copy2(local, archive)

            # Resume any partial download instead of discarding progress.
            if not archive.is_file() or not _verify_sha256(str(archive), self._MODEL_SHA256):
                partial = _find_partial_download()
                part_path = dest / _PART
                if (
                    partial is not None
                    and partial.resolve() != part_path.resolve()
                    and (not part_path.is_file() or part_path.stat().st_size < partial.stat().st_size)
                ):
                    _log.info("Reusing cached Chroma ONNX partial from %s", partial)
                    shutil.copy2(partial, part_path)
                _download_resumable(self.MODEL_DOWNLOAD_URL, archive, self._MODEL_SHA256)

            _mirror_verified_archive(archive)

            with tarfile.open(name=str(archive), mode="r:gz") as tar:
                tar.extractall(path=str(dest), filter="data")

            if not _extracted_complete(dest):
                raise RuntimeError(
                    f"Chroma ONNX model extraction incomplete under {dest / 'onnx'}"
                )

        @property
        def model(self) -> Any:
            with self._session_lock:
                if self._session is None:
                    self._download_model_if_not_exists()
                    so = self.ort.SessionOptions()
                    so.log_severity_level = 3
                    so.graph_optimization_level = self.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                    so.enable_cpu_mem_arena = False
                    providers = [
                        p
                        for p in self.ort.get_available_providers()
                        if p != "CoreMLExecutionProvider"
                    ]
                    self._session = self.ort.InferenceSession(
                        os.path.join(
                            self.DOWNLOAD_PATH, self.EXTRACTED_FOLDER_NAME, "model.onnx"
                        ),
                        providers=providers,
                        sess_options=so,
                    )
                return self._session

        def _forward(self, documents: list[str], batch_size: int = _EMBED_BATCH) -> Any:
            return super()._forward(documents, batch_size=_EMBED_BATCH)

    return _SharedMiniLM()


class ChromaDBStore:
    BUILTIN_COLLECTION = "builtin_knowledge"
    COMPANY_COLLECTION = "company_docs"
    SKILLS_COLLECTION = "skills"

    def __init__(self, persist_directory: str) -> None:
        import chromadb
        from chromadb.config import Settings

        self._client = chromadb.PersistentClient(
            path=str(persist_directory),
            settings=Settings(anonymized_telemetry=False),
        )

    def _get_or_create_collection(self, name: str) -> Any:
        return self._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=_embedding_function(),
        )

    def query(
        self,
        query_text: str,
        collection: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search. Returns [{text, metadata, distance, id}, ...]."""
        if not query_text.strip():
            return []
        try:
            col = self._get_or_create_collection(collection)
            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": max(1, n_results),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            raw = col.query(**kwargs)
        except Exception:
            _log.exception("chroma query failed for %s", collection)
            return []
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]
        out: list[dict[str, Any]] = []
        for text, meta, dist, cid in zip(docs, metas, dists, ids, strict=False):
            out.append(
                {
                    "text": text or "",
                    "metadata": dict(meta) if isinstance(meta, dict) else {},
                    "distance": dist,
                    "id": cid,
                }
            )
        return out

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
        collection: str,
    ) -> None:
        col = self._get_or_create_collection(collection)
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            col.upsert(
                documents=texts[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
                ids=ids[i : i + batch_size],
            )

    def delete_documents(self, collection: str, where: dict[str, Any]) -> None:
        try:
            col = self._get_or_create_collection(collection)
            col.delete(where=where)
        except Exception:
            pass

    def iter_chunk_metadata(
        self, collection: str, where: dict[str, Any] | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        try:
            col = self._get_or_create_collection(collection)
            rows = (
                col.get(where=where, include=["metadatas"])
                if where
                else col.get(include=["metadatas"])
            )
        except Exception:
            return []
        ids = rows.get("ids") or []
        metas = rows.get("metadatas") or []
        return [
            (str(cid), dict(md) if isinstance(md, dict) else {})
            for cid, md in zip(ids, metas, strict=False)
        ]

    def delete_by_ids(self, collection: str, ids: list[str]) -> int:
        if not ids:
            return 0
        try:
            col = self._get_or_create_collection(collection)
            col.delete(ids=ids)
            return len(ids)
        except Exception:
            logging.getLogger(__name__).exception(
                "delete_by_ids failed for %d id(s) in %s", len(ids), collection
            )
            return 0
