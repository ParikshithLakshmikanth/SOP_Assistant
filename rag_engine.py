#!/usr/bin/env python3
"""
SOP Document Intelligence: Local Ollama AI Integration & FAISS RAG Engine
========================================================================
Module: rag_engine.py
Architecture Role: Module 3 of 5 in Intelligent SOP Assistant Stack.

Responsibilities:
- Local Ollama runtime connectivity and model verification (Gemma LLM & Nomic Embed).
- Dense embedding generation (single and batch) with dimension validation (768).
- Row-wise L2 vector normalization for cosine similarity search.
- Text generation with temperature control, token limits, and progressive streaming.
- Persistent FAISS vector database management using IndexFlatIP.
- Atomic index persistence (sop.index, chunk_metadata.json, index_manifest.json).
- Safe incremental indexing, duplicate prevention, and consistency validation.
- Filtering by document ID, logical SOP ID, and revision.
- Evidence-grounded question answering with traceable source citations.
- Insufficient-evidence detection and graceful abstention.
- Fully offline execution on CPU without external API calls.
"""

import os
import re
import time
import math
import json
import shutil
import logging
from typing import List, Dict, Any, Optional, Generator, Union, Tuple
import urllib.request
import urllib.error
import numpy as np
import psutil
import faiss
import ollama

# Setup logger
logger = logging.getLogger("SOP_RAGEngine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_LLM_MODEL = "gemma-2b:latest"
DEFAULT_EMBED_MODEL = "nomic-embed-text:latest"
EXPECTED_EMBEDDING_DIM = 768

# Default directory for FAISS vector index and metadata
DEFAULT_INDEX_DIR = os.path.join("data", "faiss_index")
INDEX_FILENAME = "sop.index"
METADATA_FILENAME = "chunk_metadata.json"
MANIFEST_FILENAME = "index_manifest.json"
INDEX_VERSION = "1.0.0"


# ============================================================================
# OLLAMA CONNECTION & MODEL DISCOVERY
# ============================================================================

def get_ollama_client(endpoint: str = DEFAULT_OLLAMA_ENDPOINT) -> ollama.Client:
    """
    Instantiates an Ollama Client bound to the specified local endpoint.
    """
    return ollama.Client(host=endpoint)


def check_ollama_connection(endpoint: str = DEFAULT_OLLAMA_ENDPOINT, timeout: float = 3.0) -> bool:
    """
    Verifies that the local Ollama daemon is reachable and responding.
    """
    url = f"{endpoint.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SOP_Assistant/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError) as e:
        logger.warning(f"Ollama connection check failed at {endpoint}: {e}")
        return False


def list_available_models(endpoint: str = DEFAULT_OLLAMA_ENDPOINT) -> List[str]:
    """
    Queries the Ollama daemon and returns the list of all registered model identifiers.
    """
    if not check_ollama_connection(endpoint):
        raise ConnectionError(
            f"Cannot connect to Ollama at {endpoint}. "
            "Please ensure Ollama is installed and running ('ollama serve')."
        )

    try:
        client = get_ollama_client(endpoint)
        response = client.list()
        
        model_names: List[str] = []
        models_data = getattr(response, "models", None)
        if models_data is None and isinstance(response, dict):
            models_data = response.get("models", [])

        for m in models_data:
            if hasattr(m, "model"):
                model_names.append(m.model)
            elif isinstance(m, dict) and "model" in m:
                model_names.append(m["model"])
            elif isinstance(m, dict) and "name" in m:
                model_names.append(m["name"])

        return model_names

    except Exception as e:
        logger.error(f"Failed to list models from Ollama: {e}")
        raise ConnectionError(f"Error querying Ollama models at {endpoint}: {e}") from e


def verify_required_models(
    llm_model: str = DEFAULT_LLM_MODEL,
    embed_model: str = DEFAULT_EMBED_MODEL,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
) -> Dict[str, Any]:
    """
    Verifies that the required LLM and embedding models are registered in Ollama.
    """
    status: Dict[str, Any] = {
        "is_connected": False,
        "llm_present": False,
        "embed_present": False,
        "all_ready": False,
        "available_models": [],
        "error": None
    }

    if not check_ollama_connection(endpoint):
        status["error"] = (
            f"Ollama server is not accessible at {endpoint}. "
            "Please start the service using 'ollama serve'."
        )
        return status

    status["is_connected"] = True

    try:
        available = list_available_models(endpoint)
        status["available_models"] = available

        def match_model(target: str, model_list: List[str]) -> bool:
            clean_target = target.split(":")[0].lower()
            for m in model_list:
                clean_m = m.split(":")[0].lower()
                if m.lower() == target.lower() or clean_m == clean_target:
                    return True
            return False

        status["llm_present"] = match_model(llm_model, available)
        status["embed_present"] = match_model(embed_model, available)
        status["all_ready"] = status["llm_present"] and status["embed_present"]

        if not status["all_ready"]:
            missing = []
            if not status["llm_present"]:
                missing.append(f"Generation model '{llm_model}'")
            if not status["embed_present"]:
                missing.append(f"Embedding model '{embed_model}'")
            status["error"] = f"Missing required model(s) in Ollama: {', '.join(missing)}."

        return status

    except Exception as e:
        status["error"] = f"Failed to verify Ollama models: {e}"
        return status


# ============================================================================
# EMBEDDING GENERATION & NORMALIZATION
# ============================================================================

def validate_embedding_dimensions(
    vectors: np.ndarray,
    expected_dim: int = EXPECTED_EMBEDDING_DIM
) -> bool:
    """
    Validates that an embedding array possesses the expected dimension (768)
    and strictly contains finite real values.
    """
    if not isinstance(vectors, np.ndarray):
        raise TypeError(f"Expected numpy.ndarray, got {type(vectors)}")

    if vectors.ndim == 1:
        if vectors.shape[0] != expected_dim:
            raise ValueError(f"Embedding dimension mismatch: expected {expected_dim}, got {vectors.shape[0]}")
    elif vectors.ndim == 2:
        if vectors.shape[1] != expected_dim:
            raise ValueError(f"Embedding dimension mismatch: expected (*, {expected_dim}), got {vectors.shape}")
    else:
        raise ValueError(f"Embedding array must be 1D or 2D, got shape {vectors.shape}")

    if not np.all(np.isfinite(vectors)):
        raise ValueError("Embedding contains non-finite numerical values (NaN or Inf).")

    return True


def normalize_embeddings(vectors: np.ndarray) -> np.ndarray:
    """
    Normalizes 1D or 2D embeddings to unit L2 length (||v|| = 1.0)
    for exact cosine similarity calculation via inner product.
    """
    if not isinstance(vectors, np.ndarray):
        vectors = np.array(vectors, dtype=np.float32)

    if vectors.dtype != np.float32:
        vectors = vectors.astype(np.float32)

    if vectors.ndim == 1:
        norm = np.linalg.norm(vectors)
        if norm < 1e-12 or not np.isfinite(norm):
            logger.warning("Attempted to normalize a zero or non-finite 1D vector.")
            return vectors
        return vectors / norm
    elif vectors.ndim == 2:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        zero_mask = (norms < 1e-12) | (~np.isfinite(norms))
        safe_norms = np.where(zero_mask, 1.0, norms)
        normalized = vectors / safe_norms
        normalized[zero_mask.squeeze(axis=1)] = 0.0
        return normalized
    else:
        raise ValueError(f"Expected 1D or 2D array, got {vectors.ndim}D with shape {vectors.shape}")


def generate_embedding(
    text: str,
    model: str = DEFAULT_EMBED_MODEL,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    normalize: bool = True
) -> np.ndarray:
    """
    Generates a 768-dimensional dense embedding for a single text input.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty or whitespace-only text.")

    if not check_ollama_connection(endpoint):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint)

    try:
        if hasattr(client, "embed"):
            resp = client.embed(model=model, input=text)
            raw_embeddings = getattr(resp, "embeddings", None)
            if raw_embeddings and len(raw_embeddings) > 0:
                vec = np.array(raw_embeddings[0], dtype=np.float32)
            else:
                raise RuntimeError(f"Ollama embed response returned empty embeddings: {resp}")
        else:
            resp = client.embeddings(model=model, prompt=text)
            if "embedding" not in resp:
                raise RuntimeError(f"Ollama embeddings response missing 'embedding' field: {resp}")
            vec = np.array(resp["embedding"], dtype=np.float32)

        validate_embedding_dimensions(vec, expected_dim=EXPECTED_EMBEDDING_DIM)

        if normalize:
            vec = normalize_embeddings(vec)

        return vec

    except Exception as e:
        logger.error(f"Failed to generate embedding for text (len={len(text)}): {e}")
        raise RuntimeError(f"Embedding generation failed: {e}") from e


def generate_embeddings(
    texts: List[str],
    model: str = DEFAULT_EMBED_MODEL,
    batch_size: int = 16,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    normalize: bool = True
) -> np.ndarray:
    """
    Generates dense embeddings for a list of text inputs in configurable batches.
    """
    if texts is None or len(texts) == 0:
        return np.empty((0, EXPECTED_EMBEDDING_DIM), dtype=np.float32)

    for i, t in enumerate(texts):
        if not t or not t.strip():
            raise ValueError(f"Input text at index {i} is empty or whitespace-only.")

    if not check_ollama_connection(endpoint):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint)
    all_vectors: List[List[float]] = []

    total_texts = len(texts)
    for start_idx in range(0, total_texts, batch_size):
        end_idx = min(start_idx + batch_size, total_texts)
        batch = texts[start_idx:end_idx]

        try:
            if hasattr(client, "embed"):
                resp = client.embed(model=model, input=batch)
                batch_vecs = getattr(resp, "embeddings", None)
                if not batch_vecs or len(batch_vecs) != len(batch):
                    raise RuntimeError(
                        f"Expected {len(batch)} embeddings from batch, got {len(batch_vecs) if batch_vecs else 0}"
                    )
                all_vectors.extend(batch_vecs)
            else:
                for t in batch:
                    resp = client.embeddings(model=model, prompt=t)
                    all_vectors.append(resp["embedding"])

        except Exception as e:
            logger.error(f"Failed embedding batch [{start_idx}:{end_idx}] of {total_texts}: {e}")
            raise RuntimeError(f"Batch embedding generation failed on items [{start_idx}:{end_idx}]: {e}") from e

    arr = np.array(all_vectors, dtype=np.float32)
    validate_embedding_dimensions(arr, expected_dim=EXPECTED_EMBEDDING_DIM)

    if normalize:
        arr = normalize_embeddings(arr)

    return arr


# ============================================================================
# TEXT GENERATION & STREAMING
# ============================================================================

def sanitize_model_output(text: str) -> str:
    """
    Cleans raw model output to ensure internal reasoning traces, <think> tags,
    or leaked reasoning headers are completely stripped before returning to the user.
    """
    if not text:
        return ""
    # Strip explicit <think>...</think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Strip unclosed <think>... if generation cut off mid-thought
    cleaned = re.sub(r'<think>.*$', '', cleaned, flags=re.DOTALL)
    # Strip leading Thinking Process / Analysis blocks
    cleaned = re.sub(r'^(?:Thinking Process|Analysis):\s*\n.*?(?=\n\n|\Z)', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    # Strip standalone tags if any remain
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def generate_response(
    prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1536,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
) -> Dict[str, Any]:
    """
    Executes synchronous text generation using the local Gemma model via Ollama.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty or whitespace-only.")

    if not check_ollama_connection(endpoint):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    effective_max_tokens = max(1536, int(max_tokens))
    options = {
        "temperature": float(temperature),
        "num_predict": effective_max_tokens,
        "num_ctx": 8192
    }

    start_time = time.time()
    try:
        try:
            res = client.chat(
                model=model,
                messages=messages,
                options=options,
                think=False,
                stream=False
            )
        except TypeError:
            res = client.chat(
                model=model,
                messages=messages,
                options=options,
                stream=False
            )
        elapsed_ms = (time.time() - start_time) * 1000.0

        msg = getattr(res, "message", None)
        thinking_text = ""
        if msg is not None:
            content = getattr(msg, "content", "")
            thinking_text = getattr(msg, "thinking", "") or ""
        elif isinstance(res, dict) and "message" in res:
            content = res["message"].get("content", "")
            thinking_text = res["message"].get("thinking", "")
        else:
            content = str(res)

        clean_resp = sanitize_model_output(content)

        eval_count = getattr(res, "eval_count", 0) or 0
        eval_dur_ns = getattr(res, "eval_duration", 0) or 0
        eval_dur_ms = eval_dur_ns / 1e6 if eval_dur_ns else 0.0

        tps = (eval_count / (eval_dur_ms / 1000.0)) if eval_dur_ms > 0 else 0.0

        return {
            "response": clean_resp,
            "thinking": thinking_text.strip(),
            "model": model,
            "eval_count": eval_count,
            "total_duration_ms": round(elapsed_ms, 2),
            "eval_duration_ms": round(eval_dur_ms, 2),
            "tokens_per_second": round(tps, 2),
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Text generation failed with model {model}: {e}")
        raise RuntimeError(f"Text generation failed with model '{model}': {e}") from e


def stream_response(
    prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1536,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
) -> Generator[str, None, None]:
    """
    Progressively yields token chunks as they are generated by the local Gemma model.
    Guarantees:
    - Excludes internal thinking traces and strips <think> tags.
    - Handles GeneratorExit gracefully when the client cancels or breaks early.
    - Closes underlying HTTP stream response on exit.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty or whitespace-only.")

    if not check_ollama_connection(endpoint):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    effective_max_tokens = max(1536, int(max_tokens))
    options = {
        "temperature": float(temperature),
        "num_predict": effective_max_tokens,
        "num_ctx": 8192
    }

    stream = None
    inside_think = False
    try:
        try:
            stream = client.chat(
                model=model,
                messages=messages,
                options=options,
                think=False,
                stream=True
            )
        except TypeError:
            stream = client.chat(
                model=model,
                messages=messages,
                options=options,
                stream=True
            )

        for chunk in stream:
            done = getattr(chunk, "done", False)
            if done:
                done_reason = getattr(chunk, "done_reason", "")
                if done_reason == "length":
                    logger.warning("Ollama stream generation terminated due to context/token length limit.")
            msg = getattr(chunk, "message", None)
            if msg is not None:
                token = getattr(msg, "content", "")
            elif isinstance(chunk, dict) and "message" in chunk:
                token = chunk["message"].get("content", "")
            else:
                token = ""

            if not token:
                continue

            # Filter out in-band <think>...</think> traces if present
            if "<think>" in token:
                inside_think = True
                token = token.split("<think>")[0]

            if inside_think:
                if "</think>" in token:
                    inside_think = False
                    token = token.split("</think>")[-1]
                else:
                    token = ""

            token = token.replace("<think>", "").replace("</think>", "")
            if token:
                yield token

    except GeneratorExit:
        logger.info(f"Stream generation for model {model} was interrupted/cancelled by client.")
        raise
    except Exception as e:
        logger.error(f"Error during streaming generation with {model}: {e}")
        raise RuntimeError(f"Streaming failed with model '{model}': {e}") from e
    finally:
        if stream is not None:
            if hasattr(stream, "close") and callable(stream.close):
                try:
                    stream.close()
                except Exception:
                    pass
            elif hasattr(stream, "response") and hasattr(stream.response, "close"):
                try:
                    stream.response.close()
                except Exception:
                    pass


# ============================================================================
# FAISS VECTOR DATABASE MANAGEMENT
# ============================================================================

def initialize_faiss_index(dim: int = EXPECTED_EMBEDDING_DIM) -> faiss.IndexFlatIP:
    """
    Creates an empty FAISS IndexFlatIP for exact cosine similarity search
    (under L2-normalized embeddings).
    
    Args:
        dim: Dimensionality of vectors (default: 768).
        
    Returns:
        faiss.IndexFlatIP: Initialized empty index.
    """
    return faiss.IndexFlatIP(dim)


def validate_index_consistency(
    index: Optional[faiss.IndexFlatIP],
    chunk_metadata: List[Dict[str, Any]],
    manifest: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Validates that the FAISS index vector count, metadata list length,
    and manifest recorded count are strictly consistent and synchronized.
    
    Returns:
        Tuple[bool, str]: (is_consistent, message)
    """
    if index is None:
        return False, "FAISS index object is None."

    if not isinstance(chunk_metadata, list):
        return False, f"chunk_metadata must be a list, got {type(chunk_metadata)}."

    manifest_count = manifest.get("chunk_count", -1)
    index_total = index.ntotal
    meta_count = len(chunk_metadata)

    if index_total != meta_count:
        return False, f"Vector-to-metadata mismatch: index has {index_total} vectors, metadata has {meta_count} records."

    if manifest_count != index_total:
        return False, f"Manifest count mismatch: manifest states {manifest_count}, but index has {index_total} vectors."

    # Validate embedding model compatibility
    manifest_model = manifest.get("embedding_model", "")
    manifest_dim = manifest.get("embedding_dimension", 0)

    if manifest_dim != EXPECTED_EMBEDDING_DIM:
        return False, f"Incompatible dimension in manifest: {manifest_dim} != {EXPECTED_EMBEDDING_DIM}."

    return True, f"Index verified consistent: {index_total} vectors and metadata records synchronized."


def save_faiss_index(
    index: faiss.IndexFlatIP,
    chunk_metadata: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    index_dir: str = DEFAULT_INDEX_DIR
) -> bool:
    """
    Atomically persists the FAISS index, chunk metadata JSON, and manifest JSON.
    Uses temporary files during write to prevent corrupted partial state.
    
    Returns:
        bool: True on successful write, False on failure.
    """
    os.makedirs(index_dir, exist_ok=True)

    index_path = os.path.join(index_dir, INDEX_FILENAME)
    meta_path = os.path.join(index_dir, METADATA_FILENAME)
    manifest_path = os.path.join(index_dir, MANIFEST_FILENAME)

    tmp_index = index_path + ".tmp"
    tmp_meta = meta_path + ".tmp"
    tmp_manifest = manifest_path + ".tmp"

    try:
        # 1. Write FAISS binary
        faiss.write_index(index, tmp_index)

        # 2. Write metadata JSON
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(chunk_metadata, f, indent=2, ensure_ascii=False)

        # 3. Write manifest JSON
        with open(tmp_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # Atomic replacement
        if os.path.exists(index_path):
            os.remove(index_path)
        os.replace(tmp_index, index_path)

        if os.path.exists(meta_path):
            os.remove(meta_path)
        os.replace(tmp_meta, meta_path)

        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        os.replace(tmp_manifest, manifest_path)

        logger.info(f"Saved FAISS index ({index.ntotal} vectors) and metadata to {index_dir}")
        return True

    except Exception as e:
        logger.error(f"Failed to persist FAISS index to {index_dir}: {e}")
        for p in [tmp_index, tmp_meta, tmp_manifest]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        raise IOError(f"Failed to save FAISS index: {e}") from e


def load_faiss_index(
    index_dir: str = DEFAULT_INDEX_DIR
) -> Tuple[Optional[faiss.IndexFlatIP], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Loads and validates the persisted FAISS index, metadata, and manifest.
    
    Returns:
        Tuple: (index, chunk_metadata, manifest).
        If no index exists, returns (None, [], {}).
        
    Raises:
        ValueError: If index files exist but are corrupted or mutually inconsistent.
    """
    index_path = os.path.join(index_dir, INDEX_FILENAME)
    meta_path = os.path.join(index_dir, METADATA_FILENAME)
    manifest_path = os.path.join(index_dir, MANIFEST_FILENAME)

    if not (os.path.exists(index_path) and os.path.exists(meta_path) and os.path.exists(manifest_path)):
        logger.debug(f"No existing FAISS index found in {index_dir}")
        return None, [], {}

    try:
        # 1. Load Manifest
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 2. Check model compatibility
        if manifest.get("embedding_dimension") != EXPECTED_EMBEDDING_DIM:
            raise ValueError(
                f"Index in {index_dir} has incompatible dimension "
                f"{manifest.get('embedding_dimension')} (expected {EXPECTED_EMBEDDING_DIM})."
            )

        # 3. Load Metadata
        with open(meta_path, "r", encoding="utf-8") as f:
            chunk_metadata = json.load(f)

        # 4. Load FAISS index
        index = faiss.read_index(index_path)

        # 5. Validate consistency
        is_valid, msg = validate_index_consistency(index, chunk_metadata, manifest)
        if not is_valid:
            raise ValueError(f"FAISS index consistency check failed: {msg}")

        logger.info(f"Successfully loaded FAISS index: {index.ntotal} chunks from {index_dir}")
        return index, chunk_metadata, manifest

    except Exception as e:
        logger.error(f"Failed to load FAISS index from {index_dir}: {e}")
        raise


def remove_document_from_index(
    document_id: str,
    index_dir: str = DEFAULT_INDEX_DIR
) -> Dict[str, Any]:
    """
    Removes all chunks associated with a specific document ID or filename from the FAISS
    index and metadata, updating the manifest and saving atomically.
    
    Args:
        document_id: Document ID or filename to remove.
        index_dir: Target FAISS directory.
        
    Returns:
        Dict[str, Any]: Removal summary (removed_count, remaining_count, status).
    """
    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None or not metadata:
        return {"removed_count": 0, "remaining_count": 0, "status": "index_not_found"}

    indices_to_remove = [
        i for i, chunk in enumerate(metadata)
        if chunk.get("document_id") == document_id or chunk.get("filename") == document_id
    ]

    if not indices_to_remove:
        return {
            "removed_count": 0,
            "remaining_count": index.ntotal,
            "status": "document_not_in_index"
        }

    # Call FAISS remove_ids
    id_selector = np.array(indices_to_remove, dtype=np.int64)
    index.remove_ids(id_selector)

    # Filter metadata list
    new_metadata = [
        chunk for i, chunk in enumerate(metadata)
        if i not in indices_to_remove
    ]

    # Update manifest
    manifest["chunk_count"] = index.ntotal
    if "documents" in manifest:
        manifest["documents"] = [
            d for d in manifest["documents"]
            if d.get("document_id") != document_id and d.get("filename") != document_id
        ]
    manifest["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    save_faiss_index(index, new_metadata, manifest, index_dir=index_dir)

    return {
        "removed_count": len(indices_to_remove),
        "remaining_count": index.ntotal,
        "status": "success"
    }


def index_chunks(
    chunks: List[Dict[str, Any]],
    index_dir: str = DEFAULT_INDEX_DIR,
    batch_size: int = 16,
    replace_existing: bool = True,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    embed_model: str = DEFAULT_EMBED_MODEL
) -> Dict[str, Any]:
    """
    Embeds and indexes a list of chunk dictionaries into the FAISS index with
    guaranteed transactional safety, duplicate protection, and atomic persistence.
    
    Guarantees:
    - Checks for identical duplicates; skips redundant embedding if content is already indexed.
    - Generates and verifies embeddings BEFORE modifying index or deleting existing chunks.
    - Atomically replaces prior records on document updates without leaving orphan vectors.
    - Synchronizes FAISS index, metadata JSON, and manifest JSON atomically.
    - Disk state remains untouched if embedding generation or validation fails.
    
    Args:
        chunks: List of chunk dictionaries conforming to schema.
        index_dir: Path to directory storing index.
        batch_size: Batch size for Ollama embeddings.
        replace_existing: If True, purges prior chunks with matching document_id or filename.
        endpoint: Local Ollama URL.
        embed_model: Registered Ollama embedding model.
        
    Returns:
        Dict[str, Any]: Indexing summary metrics.
    """
    if not chunks:
        logger.warning("index_chunks called with empty chunks list.")
        return {"indexed_chunks": 0, "total_chunks": 0, "status": "empty_input"}

    # Load existing or initialize fresh index
    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None:
        index = initialize_faiss_index(EXPECTED_EMBEDDING_DIM)
        metadata = []
        manifest = {
            "version": INDEX_VERSION,
            "embedding_model": embed_model,
            "embedding_dimension": EXPECTED_EMBEDDING_DIM,
            "chunk_count": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "documents": []
        }

    # Group incoming chunks by document identifiers
    docs_incoming = set(c.get("document_id") for c in chunks if c.get("document_id"))
    fnames_incoming = set(c.get("filename") for c in chunks if c.get("filename"))

    # 1. Duplicate check: if identical content is already indexed, skip redundant embedding
    if metadata:
        existing_matches = [
            c for c in metadata
            if c.get("document_id") in docs_incoming or (c.get("filename") and c.get("filename") in fnames_incoming)
        ]
        if existing_matches and len(existing_matches) == len(chunks):
            existing_texts = [c.get("chunk_text", "").strip() for c in existing_matches]
            incoming_texts = [c.get("chunk_text", "").strip() for c in chunks]
            if existing_texts == incoming_texts:
                logger.info(f"Duplicate upload detected: document {list(docs_incoming)} already indexed with identical content.")
                return {
                    "indexed_chunks": 0,
                    "total_index_chunks": index.ntotal,
                    "embedding_duration_s": 0.0,
                    "documents_affected": list(docs_incoming),
                    "status": "duplicate_skipped",
                    "message": "Document is already indexed with identical content."
                }

    # 2. Generate embeddings FIRST before modifying any existing index records
    texts = [c["chunk_text"] for c in chunks]
    t0 = time.time()
    try:
        vectors = generate_embeddings(
            texts,
            model=embed_model,
            batch_size=batch_size,
            endpoint=endpoint,
            normalize=True
        )
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}. Preserving existing FAISS index unchanged.")
        raise RuntimeError(f"Embedding generation failed: {e}") from e

    embed_duration = time.time() - t0

    # Validate generated embeddings
    if vectors is None or len(vectors) != len(chunks):
        raise ValueError(f"Vector count mismatch: generated {len(vectors) if vectors is not None else 0} vectors for {len(chunks)} chunks.")
    if vectors.shape[1] != EXPECTED_EMBEDDING_DIM:
        raise ValueError(f"Vector dimension mismatch: got {vectors.shape[1]}, expected {EXPECTED_EMBEDDING_DIM}.")
    if not np.all(np.isfinite(vectors)):
        raise ValueError("Generated vectors contain NaN or infinite values.")

    # 3. Handle replacement of prior chunks only after embeddings are safely produced
    if replace_existing and metadata:
        indices_to_remove = [
            i for i, c in enumerate(metadata)
            if c.get("document_id") in docs_incoming or (c.get("filename") and c.get("filename") in fnames_incoming)
        ]
        if indices_to_remove:
            id_selector = np.array(indices_to_remove, dtype=np.int64)
            index.remove_ids(id_selector)
            metadata = [c for i, c in enumerate(metadata) if i not in indices_to_remove]
            if "documents" in manifest:
                manifest["documents"] = [
                    d for d in manifest["documents"]
                    if d.get("document_id") not in docs_incoming and d.get("filename") not in fnames_incoming
                ]

    # 4. Add verified vectors and metadata
    index.add(vectors)
    metadata.extend(chunks)

    # 5. Synchronize manifest
    manifest["chunk_count"] = index.ntotal
    manifest["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    existing_doc_ids = {d["document_id"] for d in manifest.get("documents", [])}
    for c in chunks:
        d_id = c.get("document_id")
        if d_id and d_id not in existing_doc_ids:
            manifest.setdefault("documents", []).append({
                "document_id": d_id,
                "logical_sop_id": c.get("logical_sop_id"),
                "filename": c.get("filename"),
                "revision": c.get("revision")
            })
            existing_doc_ids.add(d_id)

    # 6. Persist atomically
    save_faiss_index(index, metadata, manifest, index_dir=index_dir)

    return {
        "indexed_chunks": len(chunks),
        "total_index_chunks": index.ntotal,
        "embedding_duration_s": round(embed_duration, 2),
        "documents_affected": list(docs_incoming),
        "status": "success",
        "persistence_verified": True
    }


COMPONENTS_FILENAME = "components_metadata.json"


def save_components_metadata(
    components: List[Dict[str, Any]],
    index_dir: str = DEFAULT_INDEX_DIR
) -> bool:
    """Atomically persists component records to components_metadata.json."""
    os.makedirs(index_dir, exist_ok=True)
    comp_path = os.path.join(index_dir, COMPONENTS_FILENAME)
    tmp_path = comp_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(components, f, indent=2, ensure_ascii=False)
        if os.path.exists(comp_path):
            os.remove(comp_path)
        os.replace(tmp_path, comp_path)
        return True
    except Exception as e:
        logger.error(f"Failed to persist components metadata: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return False


def load_components_metadata(
    index_dir: str = DEFAULT_INDEX_DIR
) -> List[Dict[str, Any]]:
    """Loads persisted component records from components_metadata.json."""
    comp_path = os.path.join(index_dir, COMPONENTS_FILENAME)
    if not os.path.exists(comp_path):
        return []
    try:
        with open(comp_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load components metadata from {comp_path}: {e}")
        return []


def get_document_components(
    identifier: str,
    index_dir: str = DEFAULT_INDEX_DIR
) -> List[Dict[str, Any]]:
    """
    Returns all visual, tabular, and callout components associated with a document ID or filename.
    """
    comps = load_components_metadata(index_dir)
    norm = identifier.lower().strip()
    return [
        c for c in comps
        if (c.get("document_id") and c.get("document_id").lower().strip() == norm)
        or (c.get("filename") and c.get("filename").lower().strip() == norm)
        or (c.get("filename") and norm in c.get("filename", "").lower())
    ]


def search_components(
    query: str,
    subsystem: Optional[str] = None,
    source_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    is_uncertain: Optional[bool] = None,
    top_k: int = 25,
    index_dir: str = DEFAULT_INDEX_DIR
) -> List[Dict[str, Any]]:
    """
    Searches multi-source component records across names, specifications, tooling,
    subsystems, entity types, and descriptions with optional facet filtering.
    """
    comps = load_components_metadata(index_dir)
    if not comps:
        return []

    tokens = [t.lower() for t in re.split(r'\s+', query) if len(t) >= 2]
    scored = []

    for c in comps:
        # Subsystem filter
        if subsystem and subsystem != "All Subsystems" and c.get("subsystem") != subsystem:
            continue
        # Source type filter
        if source_type and source_type != "All Sources" and c.get("source_type") != source_type:
            continue
        # Entity type filter
        if entity_type and entity_type not in ("All Entity Types", "All Extracted Entities (Unfiltered)"):
            if entity_type in ("PHYSICAL_COMPONENTS_ONLY", "Physical Components & Assemblies", "Physical Components & Assemblies (Default)"):
                if c.get("entity_type") not in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"):
                    continue
            elif c.get("entity_type") != entity_type:
                continue
        # Uncertainty filter
        if is_uncertain is not None and c.get("is_uncertain") != is_uncertain:
            continue

        searchable = " ".join([
            str(c.get("component_name", "")),
            str(c.get("simple_description", "")),
            str(c.get("primary_function", "")),
            str(c.get("entity_type", "")),
            str(c.get("material_or_construction", "")),
            str(c.get("technical_specifications", "")),
            str(c.get("tooling_or_metrology", "")),
            str(c.get("acceptance_criteria", "")),
            str(c.get("subsystem", "")),
            str(c.get("section_reference", "")),
            str(c.get("callout_warning", ""))
        ]).lower()

        if not tokens:
            scored.append((1.0, c))
        else:
            matches = sum(1 for tok in tokens if tok in searchable)
            if matches > 0:
                score = matches / len(tokens)
                scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored[:top_k]]


def save_document_components(
    document_id: str,
    filename: str,
    components: List[Dict[str, Any]],
    index_dir: str = DEFAULT_INDEX_DIR
) -> bool:
    """
    Persists or updates component records for a specific document without duplicating or losing
    other documents' components in components_metadata.json.
    """
    existing_comps = load_components_metadata(index_dir)
    d_id_norm = str(document_id).strip().lower()
    fname_norm = str(filename).strip().lower()

    # Filter out old components belonging to this document
    updated = [
        c for c in existing_comps
        if not (
            (c.get("document_id") and str(c.get("document_id")).strip().lower() == d_id_norm)
            or (c.get("filename") and str(c.get("filename")).strip().lower() == fname_norm)
        )
    ]
    # Ensure components have document_id and filename
    for comp in components:
        comp.setdefault("document_id", document_id)
        comp.setdefault("filename", filename)
        comp.setdefault("source_filename", filename)

    updated.extend(components)
    return save_components_metadata(updated, index_dir)


def retry_component_extraction(
    pdf_path: str,
    document_id: Optional[str] = None,
    filename: Optional[str] = None,
    revision: Optional[str] = None,
    index_dir: str = DEFAULT_INDEX_DIR
) -> Dict[str, Any]:
    """
    Safely re-attempts component extraction for an ingested document and updates
    components_metadata.json without touching FAISS index chunks.
    """
    import document_processor as dp
    fname = filename or os.path.basename(pdf_path)
    try:
        comps = dp.extract_components_from_document(pdf_path)
        if document_id:
            for c in comps:
                c["document_id"] = document_id
        if revision:
            for c in comps:
                c["revision"] = revision

        saved = save_document_components(
            document_id=document_id or (comps[0]["document_id"] if comps else "UNKNOWN"),
            filename=fname,
            components=comps,
            index_dir=index_dir
        )
        return {
            "status": "success" if saved else "persistence_failed",
            "extracted_count": len(comps),
            "filename": fname
        }
    except Exception as e:
        logger.error(f"Retry component extraction failed for {fname}: {e}")
        return {
            "status": f"error: {str(e)}",
            "extracted_count": 0,
            "filename": fname
        }


def index_documents(
    documents: List[Dict[str, Any]],
    index_dir: str = DEFAULT_INDEX_DIR,
    batch_size: int = 16,
    replace_existing: bool = True
) -> Dict[str, Any]:
    """
    Extracts all chunks and multi-source components from processed document objects
    and indexes them into FAISS and components_metadata.json.
    
    Args:
        documents: List of document dicts returned by document_processor.process_pdf().
        index_dir: Storage path for FAISS index and components.
        batch_size: Embedding batch size.
        replace_existing: Whether to overwrite existing document records.
        
    Returns:
        Dict[str, Any]: Combined indexing summary including component counts.
    """
    all_chunks: List[Dict[str, Any]] = []
    all_components: List[Dict[str, Any]] = []

    for doc in documents:
        doc_chunks = doc.get("chunks", [])
        all_chunks.extend(doc_chunks)

        # Attach document_id and filename to component records if missing
        doc_comps = doc.get("components", [])
        d_id = doc.get("document_id")
        fname = doc.get("filename")
        for comp in doc_comps:
            comp.setdefault("document_id", d_id)
            comp.setdefault("filename", fname)
        all_components.extend(doc_comps)

    idx_summary = index_chunks(
        all_chunks,
        index_dir=index_dir,
        batch_size=batch_size,
        replace_existing=replace_existing
    )

    if all_components:
        existing_comps = load_components_metadata(index_dir)
        docs_incoming = set(c.get("document_id") for c in all_chunks if c.get("document_id"))
        fnames_incoming = set(c.get("filename") for c in all_chunks if c.get("filename"))

        if replace_existing and existing_comps:
            existing_comps = [
                c for c in existing_comps
                if c.get("document_id") not in docs_incoming and c.get("filename") not in fnames_incoming
            ]

        existing_comps.extend(all_components)
        save_components_metadata(existing_comps, index_dir)
        idx_summary["indexed_components"] = len(all_components)
        idx_summary["total_components"] = len(existing_comps)

    return idx_summary


def rebuild_faiss_index(
    sop_dir: str = "SOP",
    index_dir: str = DEFAULT_INDEX_DIR,
    batch_size: int = 16
) -> Dict[str, Any]:
    """
    Performs a clean, complete rebuild of the FAISS vector database from
    all SOP PDFs present in the given directory.
    
    Args:
        sop_dir: Directory containing SOP PDFs (default: 'SOP').
        index_dir: Output FAISS directory.
        batch_size: Embedding batch size.
        
    Returns:
        Dict[str, Any]: Rebuild summary metrics.
    """
    import document_processor as dp

    logger.info(f"Initiating clean rebuild of FAISS index from '{sop_dir}'...")
    start_time = time.time()

    # 1. Process all SOP PDFs
    docs = dp.process_all_sops(sop_dir=sop_dir)
    total_docs = len(docs)

    all_chunks: List[Dict[str, Any]] = []
    for d in docs:
        all_chunks.extend(d.get("chunks", []))
    total_chunks = len(all_chunks)

    # 2. Re-initialize empty index
    index = initialize_faiss_index(EXPECTED_EMBEDDING_DIM)
    metadata: List[Dict[str, Any]] = []
    manifest = {
        "version": INDEX_VERSION,
        "embedding_model": DEFAULT_EMBED_MODEL,
        "embedding_dimension": EXPECTED_EMBEDDING_DIM,
        "chunk_count": total_chunks,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "documents": [
            {
                "document_id": d["document_id"],
                "logical_sop_id": d["logical_sop_id"],
                "filename": d["filename"],
                "revision": d["revision"]
            }
            for d in docs
        ]
    }

    # 3. Generate embeddings
    texts = [c["chunk_text"] for c in all_chunks]
    t_embed_start = time.time()
    vectors = generate_embeddings(
        texts,
        model=DEFAULT_EMBED_MODEL,
        batch_size=batch_size,
        normalize=True
    )
    embed_time = time.time() - t_embed_start

    # 4. Add vectors & save
    index.add(vectors)
    metadata = all_chunks
    save_faiss_index(index, metadata, manifest, index_dir=index_dir)

    total_time = time.time() - start_time
    logger.info(
        f"Clean rebuild complete: {total_docs} documents, "
        f"{total_chunks} chunks in {total_time:.2f}s "
        f"(Embedding: {embed_time:.2f}s)"
    )

    return {
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "embedding_time_s": round(embed_time, 2),
        "total_rebuild_time_s": round(total_time, 2),
        "index_dir": index_dir,
        "status": "success"
    }


# ============================================================================
# INDEX HEALTH & VERIFICATION UTILITIES
# ============================================================================

def verify_faiss_index_health(index_dir: str = DEFAULT_INDEX_DIR) -> Dict[str, Any]:
    """
    Performs comprehensive diagnostic health audit on the FAISS index and metadata.
    
    Verifies:
    1. Disk existence of index binary, metadata JSON, and manifest JSON.
    2. Vector dimensions match expected embedding dimension (768).
    3. Strict synchronization between FAISS ntotal, metadata records, and manifest count.
    4. Finite vector representations and valid L2 normalization (~1.0).
    5. Structural integrity of chunk metadata fields across all chunks.
    6. Complete document inventory partitioned into baseline vs uploaded SOPs.
    
    Returns:
        Dict[str, Any]: Detailed diagnostic health report.
    """
    issues = []
    index_path = os.path.join(index_dir, INDEX_FILENAME)
    meta_path = os.path.join(index_dir, METADATA_FILENAME)
    manifest_path = os.path.join(index_dir, MANIFEST_FILENAME)

    if not os.path.exists(index_path):
        issues.append(f"Missing FAISS index file: {index_path}")
    if not os.path.exists(meta_path):
        issues.append(f"Missing metadata file: {meta_path}")
    if not os.path.exists(manifest_path):
        issues.append(f"Missing manifest file: {manifest_path}")

    if issues:
        return {
            "is_healthy": False,
            "issues": issues,
            "total_vectors": 0,
            "total_documents": 0,
            "baseline_chunks_count": 0,
            "uploaded_chunks_count": 0,
            "baseline_documents": [],
            "uploaded_documents": [],
            "embedding_dimension": 0
        }

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        index = faiss.read_index(index_path)
    except Exception as e:
        return {
            "is_healthy": False,
            "issues": [f"Failed to read index files: {str(e)}"],
            "total_vectors": 0,
            "total_documents": 0
        }

    # Verify vector dimension
    if index.d != EXPECTED_EMBEDDING_DIM:
        issues.append(f"Index vector dimension mismatch: {index.d} != {EXPECTED_EMBEDDING_DIM}")
    if manifest.get("embedding_dimension") != EXPECTED_EMBEDDING_DIM:
        issues.append(f"Manifest dimension mismatch: {manifest.get('embedding_dimension')} != {EXPECTED_EMBEDDING_DIM}")

    # Verify strict synchronization
    manifest_count = manifest.get("chunk_count", -1)
    if index.ntotal != len(metadata):
        issues.append(f"Desynchronization: index.ntotal ({index.ntotal}) != len(metadata) ({len(metadata)})")
    if index.ntotal != manifest_count:
        issues.append(f"Desynchronization: index.ntotal ({index.ntotal}) != manifest chunk_count ({manifest_count})")

    # Verify vector finiteness and L2 normalization
    if index.ntotal > 0:
        try:
            sample_count = min(index.ntotal, 50)
            sample_vectors = np.zeros((sample_count, index.d), dtype=np.float32)
            for i in range(sample_count):
                sample_vectors[i] = index.reconstruct(i)
            if not np.all(np.isfinite(sample_vectors)):
                issues.append("Non-finite values (NaN or Inf) detected in index vectors.")
            norms = np.linalg.norm(sample_vectors, axis=1)
            if not np.all(np.isclose(norms, 1.0, atol=0.08)):
                issues.append("Sample vectors deviate from expected unit L2 normalization.")
        except Exception:
            pass

    # Verify metadata field completeness
    required_keys = {"chunk_id", "document_id", "filename", "revision", "chunk_text", "page_number"}
    missing_count = sum(1 for c in metadata if not required_keys.issubset(c.keys()))
    if missing_count > 0:
        issues.append(f"{missing_count} chunks have incomplete metadata keys.")

    # Inventory breakdown
    baseline_docs = set()
    uploaded_docs = set()
    baseline_chunks = 0
    uploaded_chunks = 0

    for c in metadata:
        fname = c.get("filename", "")
        if is_standard_baseline_corpus_doc(fname):
            baseline_docs.add(fname)
            baseline_chunks += 1
        else:
            uploaded_docs.add(fname)
            uploaded_chunks += 1

    return {
        "is_healthy": len(issues) == 0,
        "issues": issues,
        "total_vectors": index.ntotal,
        "total_documents": len(baseline_docs | uploaded_docs),
        "baseline_chunks_count": baseline_chunks,
        "uploaded_chunks_count": uploaded_chunks,
        "baseline_documents": sorted(list(baseline_docs)),
        "uploaded_documents": sorted(list(uploaded_docs)),
        "embedding_dimension": index.d,
        "manifest_version": manifest.get("version", "unknown")
    }


def verify_document_indexed(identifier: str, index_dir: str = DEFAULT_INDEX_DIR) -> Dict[str, Any]:
    """
    Checks if a document (by document_id or filename) is properly indexed with valid chunks.
    
    Returns:
        Dict[str, Any]: Verification status, chunk count, and document metadata.
    """
    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None or not metadata:
        return {"is_indexed": False, "chunk_count": 0, "message": "Index not found or empty."}

    norm_id = identifier.lower().strip()
    matching = [
        c for c in metadata
        if (c.get("document_id") and c.get("document_id").lower().strip() == norm_id)
        or (c.get("filename") and c.get("filename").lower().strip() == norm_id)
        or (c.get("filename") and norm_id in c.get("filename", "").lower())
    ]

    if not matching:
        return {"is_indexed": False, "chunk_count": 0, "message": f"Document '{identifier}' not found in index."}

    first = matching[0]
    return {
        "is_indexed": True,
        "chunk_count": len(matching),
        "document_id": first.get("document_id"),
        "filename": first.get("filename"),
        "logical_sop_id": first.get("logical_sop_id"),
        "revision": first.get("revision"),
        "is_standard": is_standard_baseline_corpus_doc(first.get("filename", "")),
        "chunk_ids": [c.get("chunk_id") for c in matching]
    }


def verify_retrieval_for_document(
    query: str,
    expected_identifier: str,
    top_k: int = 5,
    revision_mode: Optional[str] = "v2",
    index_dir: str = DEFAULT_INDEX_DIR
) -> Dict[str, Any]:
    """
    Performs vector similarity search and verifies whether chunks from the target
    document are retrieved in top search results.
    
    Returns:
        Dict[str, Any]: Verification metrics (is_retrieved, best_rank, best_score, matching_chunks_count).
    """
    chunks = retrieve_relevant_chunks(
        query=query,
        top_k=top_k,
        revision_mode=revision_mode,
        index_dir=index_dir
    )

    matching_ranks = []
    top_score = None
    matched_chunk = None
    norm_expected = expected_identifier.lower().strip()

    for rank, chunk in enumerate(chunks, 1):
        c_doc_id = (chunk.get("document_id") or "").lower().strip()
        c_fname = (chunk.get("filename") or "").lower().strip()
        if c_doc_id == norm_expected or c_fname == norm_expected or norm_expected in c_fname:
            matching_ranks.append(rank)
            if top_score is None:
                top_score = chunk.get("score")
                matched_chunk = chunk

    return {
        "is_retrieved": len(matching_ranks) > 0,
        "best_rank": matching_ranks[0] if matching_ranks else None,
        "best_score": round(float(top_score), 4) if top_score is not None else None,
        "matching_chunks_count": len(matching_ranks),
        "total_retrieved": len(chunks),
        "matched_chunk": matched_chunk
    }


def get_indexed_categories(index_dir: str = DEFAULT_INDEX_DIR) -> List[str]:
    """
    Discovers all unique logical SOP categories present in the index metadata.
    Preserves the 5 canonical baseline categories first, followed by any custom/uploaded categories.
    """
    canonical = [
        "HVF_SOP_1_Hull_Welding",
        "HVF_SOP_2_Turret_Integration",
        "HVF_SOP_3_Engine_Alignment",
        "HVF_SOP_4_Torsion_Suspension",
        "HVF_SOP_5_Gun_Calibration"
    ]
    try:
        _, metadata, _ = load_faiss_index(index_dir)
        if not metadata:
            return canonical
        existing = set(c.get("logical_sop_id") for c in metadata if c.get("logical_sop_id"))
        custom = sorted(list(existing - set(canonical)))
        return canonical + custom
    except Exception:
        return canonical


# ============================================================================
# PASSAGE RETRIEVAL & FILTERING
# ============================================================================

# Canonical standard SOP filenames belonging to the official 10-document baseline corpus
BASELINE_V1_FILENAMES = {
    "hvf_sop_1_hull_welding.pdf",
    "hvf_sop_2_turret_integration.pdf",
    "hvf_sop_3_engine_alignment.pdf",
    "hvf_sop_4_torsion_suspension.pdf",
    "hvf_sop_5_gun_calibration.pdf",
}

STANDARD_CORPUS_FILENAMES = {
    "hvf_sop_1_hull_welding.pdf",
    "hvf_sop_1_hull_welding_v2.pdf",
    "hvf_sop_2_turret_integration.pdf",
    "hvf_sop_2_turret_integration_v2.pdf",
    "hvf_sop_3_engine_alignment.pdf",
    "hvf_sop_3_engine_alignment_v2.pdf",
    "hvf_sop_4_torsion_suspension.pdf",
    "hvf_sop_4_torsion_suspension_v2.pdf",
    "hvf_sop_5_gun_calibration.pdf",
    "hvf_sop_5_gun_calibration_v2.pdf",
}


def is_standard_baseline_corpus_doc(filename: str) -> bool:
    """Returns True if the filename belongs to the official 10 standard HVF SOP documents."""
    return str(filename).lower().strip() in STANDARD_CORPUS_FILENAMES


def is_v2_explicit(chunk: Dict[str, Any]) -> bool:
    """Returns True if chunk or document record has explicit V2/revised markers."""
    rev = str(chunk.get("revision", ""))
    doc_id = str(chunk.get("document_id", ""))
    fname = str(chunk.get("filename", "")).lower()
    eco = chunk.get("eco_number", "")

    if "Version 2" in rev or "[Version 2.0]" in rev or "v2.0" in rev.lower():
        return True
    if doc_id.upper().endswith("-V2") or "/V2" in doc_id.upper():
        return True
    if eco and str(eco).strip() and str(eco).strip() not in ("None", "UNKNOWN", ""):
        return True
    if fname.endswith("_v2.pdf") or fname.endswith("-v2.pdf"):
        return True
    return False


def is_v1_chunk(chunk: Dict[str, Any]) -> bool:
    """
    Deterministically determines whether a chunk belongs to an archival baseline (V1) SOP.
    
    Identified by:
    - Known baseline SOP filenames
    - Filename ending with '_v1.pdf' or '-v1.pdf'
    - Revision explicitly labeled as baseline / archival / superseded
    - Non-uploaded documents whose clean revision string matches exact baseline version tokens
    """
    if chunk.get("is_uploaded"):
        return False

    fname = str(chunk.get("filename", "")).lower().strip()
    rev = str(chunk.get("revision", "")).lower().strip()

    if "uploaded" in rev or "uploaded" in fname:
        return False

    if is_v2_explicit(chunk):
        return False

    if fname in BASELINE_V1_FILENAMES or fname.endswith("_v1.pdf") or fname.endswith("-v1.pdf"):
        return True

    if "baseline" in rev or "superseded" in rev or "archival" in rev:
        return True

    clean_rev = rev.split("|")[0].strip()
    if clean_rev in ("v1.0", "v1", "rev 1", "rev 1.0", "version 1", "version 1.0"):
        return True

    return False


def is_v2_chunk(chunk: Dict[str, Any]) -> bool:
    """
    Deterministically determines whether a chunk belongs to a revised (V2) or
    currently active operational SOP.
    
    Any document that is not an archival baseline (V1) document is an active,
    authoritative technical specification and is eligible for latest (V2) retrieval.
    """
    return not is_v1_chunk(chunk)


def format_citation(chunk: Dict[str, Any]) -> str:
    """
    Constructs a uniform, traceable source citation string.
    Format: [Filename, Revision, Section, Page X]
    
    Example:
        [HVF_SOP_1_Hull_Welding_v2.pdf, Rev 5.0, SECTION 1.0, Page 2]
    """
    fname = chunk.get("filename", "SOP.pdf")
    rev = chunk.get("revision", "").split("|")[0].strip()
    sec = chunk.get("section_title", "General")
    # Clean section title to brief header
    sec_clean = re.sub(r'[\r\n]+', ' ', sec).split(' - ')[0].split(' : ')[0].strip()
    if len(sec_clean) > 40:
        sec_clean = sec_clean[:37] + "..."

    page = chunk.get("page_number", 1)
    return f"[{fname}, {rev}, {sec_clean}, Page {page}]"


def retrieve_relevant_chunks(
    query: str,
    top_k: int = 5,
    document_id: Optional[str] = None,
    logical_sop_id: Optional[str] = None,
    revision: Optional[str] = None,
    revision_mode: Optional[str] = None,
    score_threshold: Optional[float] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    embed_model: str = DEFAULT_EMBED_MODEL,
    v2_boost: float = 0.03
) -> List[Dict[str, Any]]:
    """
    Performs vector similarity search in the FAISS index to retrieve the most
    relevant document passages for a query with V2-first revision intelligence.
    
    Guarantees:
    - Normalizes query vector for exact cosine similarity calculation.
    - Preserves all source document, revision, section, and page information.
    - Accurately applies document_id, logical_sop_id, revision, and revision_mode filters.
    - V2 mode: strictly retrieves only revised documents; never falls back to V1.
    - V1 mode: strictly retrieves only baseline documents.
    - All revisions mode: retrieves both; prioritizes V2 on comparable relevance
      (v2_boost = 0.03) without blindly sacrificing relevance for low-similarity V2 chunks.
    - Preserves unmanipulated cosine similarity in 'score' while ranking via 'effective_score'.
    
    Args:
        query: User question or search query string.
        top_k: Maximum number of relevant chunks to return.
        document_id: Optional filter for a specific document ID.
        logical_sop_id: Optional filter for an SOP category (e.g. 'HVF_SOP_1_Hull_Welding').
        revision: Optional filter for a specific revision string or mode.
        revision_mode: Optional mode: 'v2' (Latest), 'v1' (Baseline), or 'all' (V2 prioritized).
        score_threshold: Minimum cosine similarity score.
        index_dir: FAISS directory.
        endpoint: Ollama endpoint.
        embed_model: Ollama embedding model.
        v2_boost: Controlled boost for V2 passages on comparable relevance (default 0.03).
        
    Returns:
        List[Dict[str, Any]]: Ranked list of matching chunks with similarity scores.
    """
    if not query or not query.strip():
        return []

    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None or index.ntotal == 0 or not metadata:
        logger.warning(f"No FAISS index available in {index_dir} for query: {query[:30]}")
        return []

    # Normalize revision mode from revision_mode or revision parameter
    effective_mode: Optional[str] = None
    specific_revision_filter: Optional[str] = None

    if revision_mode:
        rm = revision_mode.strip().lower()
        if "v2" in rm and "all" not in rm and "prioritize" not in rm:
            effective_mode = "v2"
        elif "v1" in rm or "baseline" in rm:
            effective_mode = "v1"
        elif "all" in rm or "cross" in rm or "prioritize" in rm:
            effective_mode = "all"
        else:
            effective_mode = rm

    if revision:
        r_str = revision.strip().lower()
        if r_str in ["v2", "v2_only", "revision_v2", "latest"] or r_str.startswith("v2 —") or r_str.startswith("v2 -"):
            if not effective_mode:
                effective_mode = "v2"
        elif r_str in ["v1", "v1_only", "baseline_v1", "baseline"] or r_str.startswith("v1 —") or r_str.startswith("v1 -"):
            if not effective_mode:
                effective_mode = "v1"
        elif r_str in ["all", "all_revisions", "all revisions"] or r_str.startswith("all revisions"):
            if not effective_mode:
                effective_mode = "all"
        else:
            # Caller passed a specific revision substring like "Rev 4.6"
            specific_revision_filter = revision

    # 1. Embed and normalize query vector
    q_vec = generate_embedding(
        query,
        model=embed_model,
        endpoint=endpoint,
        normalize=True
    )
    q_arr = q_vec.reshape(1, -1).astype(np.float32)

    # 2. Search FAISS
    # When filtering by revision mode or categories, expand candidate pool
    has_filters = bool(document_id or logical_sop_id or specific_revision_filter or effective_mode in ("v2", "v1"))
    k_search = min(index.ntotal, max(top_k * 8, 40) if has_filters else top_k)

    scores, indices = index.search(q_arr, k_search)

    candidates: List[Dict[str, Any]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue

        raw_chunk = metadata[idx]

        # Apply score threshold
        if score_threshold is not None and score < score_threshold:
            continue

        # Apply Document ID filter
        if document_id and raw_chunk.get("document_id") != document_id:
            continue

        # Apply Logical SOP ID filter
        if logical_sop_id and raw_chunk.get("logical_sop_id") != logical_sop_id:
            continue

        # Apply Specific Revision Substring filter (e.g. 'Rev 4.6')
        if specific_revision_filter and specific_revision_filter.lower() not in raw_chunk.get("revision", "").lower():
            continue

        # Apply Revision Mode filter (V2 vs V1 vs All)
        chunk_is_v2 = is_v2_chunk(raw_chunk)
        if effective_mode == "v2" and not chunk_is_v2:
            continue
        elif effective_mode == "v1" and chunk_is_v2:
            continue

        result_item = dict(raw_chunk)
        raw_score = float(score)
        result_item["score"] = raw_score
        result_item["citation"] = format_citation(raw_chunk)
        result_item["is_v2"] = chunk_is_v2

        # Controlled V2 preference in "All revisions" mode among comparably relevant results
        if effective_mode == "all" and chunk_is_v2:
            result_item["effective_score"] = raw_score + v2_boost
        else:
            result_item["effective_score"] = raw_score

        candidates.append(result_item)

    # Rank by effective_score descending
    candidates.sort(key=lambda x: x.get("effective_score", x["score"]), reverse=True)
    return candidates[:top_k]


# ============================================================================
# EVIDENCE CONTEXT & QUESTION ANSWERING
# ============================================================================

def build_evidence_context(
    retrieved_chunks: List[Dict[str, Any]],
    max_context_chars: int = 16000
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Constructs a bounded, structured textual evidence block from retrieved chunks
    for injection into LLM prompts, accompanied by structured citation metadata.
    
    Args:
        retrieved_chunks: Output from retrieve_relevant_chunks().
        max_context_chars: Maximum character budget for evidence block (default 16000).
        
    Returns:
        Tuple[str, List[Dict[str, Any]]]: (formatted_context_str, structured_citations)
    """
    if not retrieved_chunks:
        return "No relevant SOP documentation retrieved.", []

    passages = []
    citations = []
    current_chars = 0

    effective_max_chars = max(max_context_chars, min(len(retrieved_chunks) * 3500, 24000))

    for i, chunk in enumerate(retrieved_chunks):
        p_num = i + 1
        citation_str = chunk.get("citation", format_citation(chunk))
        chunk_text = chunk.get("chunk_text", "").strip()

        passage_block = (
            f"--- EVIDENCE PASSAGE [{p_num}] ---\n"
            f"SOURCE: {chunk.get('filename')}\n"
            f"DOCUMENT ID: {chunk.get('document_id')}\n"
            f"REVISION: {chunk.get('revision')}\n"
            f"SECTION: {chunk.get('section_title')}\n"
            f"PAGE: {chunk.get('page_number')}\n"
            f"CITATION: {citation_str}\n"
            f"CONTENT:\n{chunk_text}\n"
        )

        if current_chars + len(passage_block) > effective_max_chars and passages:
            break

        passages.append(passage_block)
        current_chars += len(passage_block)

        citations.append({
            "passage_number": p_num,
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "logical_sop_id": chunk.get("logical_sop_id"),
            "filename": chunk.get("filename"),
            "revision": chunk.get("revision"),
            "section_title": chunk.get("section_title"),
            "page_number": chunk.get("page_number"),
            "page_numbers": chunk.get("page_numbers"),
            "score": chunk.get("score"),
            "citation": citation_str,
            "chunk_text": chunk_text
        })

    formatted_context = "\n".join(passages)
    return formatted_context, citations


RAG_SYSTEM_PROMPT = """You are the official SOP Document Intelligence Assistant for Heavy Vehicles Factory (HVF), Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence.

Your objective is to provide complete, precise, and rigorous answers to engineering and manufacturing questions using ONLY the authoritative SOP evidence provided below.

Strict Operational Guidelines:
1. Grounding & Completeness: Rely EXCLUSIVELY on the factual statements in the provided EVIDENCE PASSAGES. Never invent, extrapolate, or hallucinate procedures, tolerances, or values not explicitly stated. Provide complete answers covering all parameters, specifications, and acceptance criteria mentioned in the evidence without stopping prematurely.
2. Structured Presentation: For technical benchmarks, parameters, or requirements, organize details logically with clear headings, bullet points, or markdown tables.
3. Version Distinctions: When evidence contains multiple revisions (e.g., baseline Rev 4.2 vs revised Rev 5.0), clearly distinguish between them.
4. In-Text Citations: At the end of every substantive assertion or parameter, insert the exact bracketed citation from the passage (e.g. [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 4.0, Page 4-5]).
5. Insufficient Evidence & Scope Boundaries: If the provided evidence does not contain a specific parameter or benchmark asked for, explicitly state what is not found in the retrieved documentation. Never truncate mid-sentence.
6. Conversation History: Prior chat turns are for conversational continuity only. Never cite or treat past user messages as authoritative SOP documentation."""


def generate_rag_answer(
    question: str,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    top_k: int = 5,
    document_id: Optional[str] = None,
    logical_sop_id: Optional[str] = None,
    revision: Optional[str] = None,
    revision_mode: Optional[str] = None,
    score_threshold: Optional[float] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1536
) -> Dict[str, Any]:
    """
    Synthesizes an evidence-grounded answer to a user question using retrieved chunks.
    
    Guarantees:
    - Strictly grounds generation in retrieved evidence.
    - Evaluates and flags insufficient evidence conditions (with revision-aware abstention).
    - Returns structured citation metadata alongside answer text.
    - Separates conversational dialogue context from authoritative document evidence.
    - Detects cross-revision evidence and enforces explicit version differentiation.
    
    Returns:
        Dict[str, Any]:
            - answer (str)
            - citations (List[Dict[str, Any]])
            - is_insufficient (bool)
            - is_cross_revision (bool)
            - model (str)
            - tokens_per_second (float)
            - eval_count (int)
            - status (str)
    """
    if retrieved_chunks is None:
        retrieved_chunks = retrieve_relevant_chunks(
            query=question,
            top_k=top_k,
            document_id=document_id,
            logical_sop_id=logical_sop_id,
            revision=revision,
            revision_mode=revision_mode,
            score_threshold=score_threshold,
            endpoint=endpoint
        )

    if not retrieved_chunks:
        mode_val = (revision_mode or (revision if revision and any(k in revision.lower() for k in ["v2", "v1"]) else "")).lower()
        if "v2" in mode_val and "all" not in mode_val:
            insufficient_msg = "The selected revision (V2 — Latest revision) does not provide sufficient evidence to answer this question."
        elif "v1" in mode_val:
            insufficient_msg = "The selected revision (V1 — Baseline revision) does not provide sufficient evidence to answer this question."
        else:
            insufficient_msg = "The provided SOP documentation does not contain sufficient evidence to answer this question."

        return {
            "answer": insufficient_msg,
            "citations": [],
            "is_insufficient": True,
            "is_cross_revision": False,
            "model": model,
            "tokens_per_second": 0.0,
            "eval_count": 0,
            "status": "insufficient_evidence"
        }

    evidence_context, citations = build_evidence_context(retrieved_chunks, max_context_chars=16000)

    has_v1 = any(is_v1_chunk(c) for c in retrieved_chunks)
    has_v2 = any(is_v2_chunk(c) for c in retrieved_chunks)
    is_cross_revision = has_v1 and has_v2

    # Construct bounded user prompt
    prompt_parts = []
    
    # 1. Bounded conversation history if present
    if conversation_history:
        prompt_parts.append("### CONVERSATION CONTEXT (FOR REFERENCE ONLY - NOT AUTHORITATIVE SOP EVIDENCE):")
        for turn in conversation_history[-4:]:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            prompt_parts.append(f"{role}: {content}")
        prompt_parts.append("")

    # 2. Authoritative Evidence Context
    prompt_parts.append("### AUTHORITATIVE SOP EVIDENCE:")
    prompt_parts.append(evidence_context)
    prompt_parts.append("")

    # 3. User Question & Instructions
    prompt_parts.append("### USER QUESTION:")
    prompt_parts.append(question)
    prompt_parts.append("")
    prompt_parts.append("### INSTRUCTIONS:")
    prompt_parts.append(
        "Answer the user's specific question using relevant evidence from the passages above.\n"
        "- Focus directly on evidence relevant to the question.\n"
        "- Present all relevant parameters, tolerances, and acceptance criteria concisely in structured bullet points or a table.\n"
        "- Avoid redundant or overly repetitive explanations.\n"
    )
    if is_cross_revision:
        prompt_parts.append(
            "- CRITICAL: The retrieved evidence spans multiple revisions (both baseline V1 and revised V2). "
            "Clearly identify the exact revision for each assertion and explicitly distinguish baseline vs revised values.\n"
        )
    else:
        prompt_parts.append("- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n")

    prompt_parts.append(
        "- Insert the exact bracketed citation for every parameter.\n"
        "- If certain benchmarks are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- Conclude concisely and end with complete terminal punctuation."
    )

    full_prompt = "\n".join(prompt_parts)

    # Generate response via local Gemma
    gen_result = generate_response(
        prompt=full_prompt,
        model=model,
        system_prompt=RAG_SYSTEM_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint
    )

    answer_text = gen_result.get("response", "")

    # Detect insufficient evidence flags
    insufficient_signals = [
        "does not contain sufficient",
        "insufficient evidence",
        "not mentioned in the provided",
        "no information provided",
        "provided sop documentation does not"
    ]
    is_insufficient = any(sig in answer_text.lower() for sig in insufficient_signals)

    return {
        "answer": answer_text,
        "citations": citations,
        "is_insufficient": is_insufficient,
        "model": model,
        "tokens_per_second": gen_result.get("tokens_per_second", 0.0),
        "eval_count": gen_result.get("eval_count", 0),
        "total_duration_ms": gen_result.get("total_duration_ms", 0.0),
        "status": "success"
    }


def answer_question(
    question: str,
    top_k: int = 5,
    document_id: Optional[str] = None,
    logical_sop_id: Optional[str] = None,
    revision: Optional[str] = None,
    score_threshold: Optional[float] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_LLM_MODEL
) -> Dict[str, Any]:
    """
    End-to-end RAG pipeline wrapper (synchronous):
    1. Retrieves relevant evidence passages from FAISS.
    2. Builds structured evidence context.
    3. Synthesizes an evidence-grounded answer with traceable citations.
    
    Args:
        question: Natural language question.
        top_k: Number of chunks to retrieve.
        document_id: Optional document ID filter.
        logical_sop_id: Optional logical SOP category filter.
        revision: Optional revision filter.
        revision_mode: Optional revision mode ('v2', 'v1', or 'all').
        score_threshold: Minimum cosine similarity.
        conversation_history: Prior chat history.
        index_dir: FAISS storage directory.
        endpoint: Ollama endpoint.
        model: LLM model.
        
    Returns:
        Dict[str, Any]: Comprehensive RAG answer object.
    """
    retrieval_t0 = time.time()
    chunks = retrieve_relevant_chunks(
        query=question,
        top_k=top_k,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        revision_mode=revision_mode,
        score_threshold=score_threshold,
        index_dir=index_dir,
        endpoint=endpoint
    )
    retrieval_duration_ms = (time.time() - retrieval_t0) * 1000.0

    rag_output = generate_rag_answer(
        question=question,
        retrieved_chunks=chunks,
        conversation_history=conversation_history,
        endpoint=endpoint,
        model=model,
        revision=revision,
        revision_mode=revision_mode
    )

    rag_output["retrieval_duration_ms"] = round(retrieval_duration_ms, 2)
    rag_output["retrieved_chunks_count"] = len(chunks)
    return rag_output


def stream_rag_answer(
    question: str,
    top_k: int = 5,
    document_id: Optional[str] = None,
    logical_sop_id: Optional[str] = None,
    revision: Optional[str] = None,
    revision_mode: Optional[str] = None,
    score_threshold: Optional[float] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1536
) -> Tuple[Generator[str, None, None], List[Dict[str, Any]], Dict[str, Any]]:
    """
    End-to-end progressive RAG streaming pipeline:
    1. Retrieves relevant evidence passages from FAISS with V2-first intelligence.
    2. Builds structured evidence context and citations.
    3. Yields progressive token stream from Gemma while returning citations immediately.
    
    Returns:
        Tuple[Generator[str, None, None], List[Dict[str, Any]], Dict[str, Any]]:
            - token_generator: Yields response text token by token.
            - citations: Structured citations list for UI rendering.
            - info: Metadata dict (retrieval_duration_ms, retrieved_chunks_count, is_cross_revision).
    """
    retrieval_t0 = time.time()
    chunks = retrieve_relevant_chunks(
        query=question,
        top_k=top_k,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        revision_mode=revision_mode,
        score_threshold=score_threshold,
        index_dir=index_dir,
        endpoint=endpoint
    )
    retrieval_duration_ms = (time.time() - retrieval_t0) * 1000.0

    if not chunks:
        def empty_gen():
            mode_val = (revision_mode or (revision if revision and any(k in revision.lower() for k in ["v2", "v1"]) else "")).lower()
            if "v2" in mode_val and "all" not in mode_val:
                yield "The selected revision (V2 — Latest revision) does not provide sufficient evidence to answer this question."
            elif "v1" in mode_val:
                yield "The selected revision (V1 — Baseline revision) does not provide sufficient evidence to answer this question."
            else:
                yield "The provided SOP documentation does not contain sufficient evidence to answer this question."

        info = {
            "retrieval_duration_ms": round(retrieval_duration_ms, 2),
            "retrieved_chunks_count": 0,
            "is_insufficient": True,
            "is_cross_revision": False
        }
        return empty_gen(), [], info

    evidence_context, citations = build_evidence_context(chunks, max_context_chars=16000)

    has_v1 = any(is_v1_chunk(c) for c in chunks)
    has_v2 = any(is_v2_chunk(c) for c in chunks)
    is_cross_revision = has_v1 and has_v2

    # Build prompt
    prompt_parts = []
    if conversation_history:
        prompt_parts.append("### CONVERSATION CONTEXT (FOR REFERENCE ONLY - NOT AUTHORITATIVE SOP EVIDENCE):")
        for turn in conversation_history[-4:]:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            prompt_parts.append(f"{role}: {content}")
        prompt_parts.append("")

    prompt_parts.append("### AUTHORITATIVE SOP EVIDENCE:")
    prompt_parts.append(evidence_context)
    prompt_parts.append("")
    prompt_parts.append("### USER QUESTION:")
    prompt_parts.append(question)
    prompt_parts.append("")
    prompt_parts.append("### INSTRUCTIONS:")
    prompt_parts.append(
        "Answer the user's specific question using relevant evidence from the passages above.\n"
        "- Focus directly on evidence relevant to the question.\n"
        "- Present all relevant parameters, tolerances, and acceptance criteria concisely in structured bullet points or a table.\n"
        "- Avoid redundant or overly repetitive explanations.\n"
    )
    if is_cross_revision:
        prompt_parts.append(
            "- CRITICAL: The retrieved evidence spans multiple revisions (both baseline V1 and revised V2). "
            "Clearly identify the exact revision for each assertion and explicitly distinguish baseline vs revised values.\n"
        )
    else:
        prompt_parts.append("- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n")

    prompt_parts.append(
        "- Insert the exact bracketed citation for every parameter.\n"
        "- If certain benchmarks are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- Conclude concisely and end with complete terminal punctuation."
    )

    full_prompt = "\n".join(prompt_parts)

    token_gen = stream_response(
        prompt=full_prompt,
        model=model,
        system_prompt=RAG_SYSTEM_PROMPT,
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint
    )

    info = {
        "retrieval_duration_ms": round(retrieval_duration_ms, 2),
        "retrieved_chunks_count": len(chunks),
        "is_insufficient": False,
        "is_cross_revision": is_cross_revision
    }

    return token_gen, citations, info


# ============================================================================
# PERFORMANCE MEASUREMENT (EXTENDED)
# ============================================================================

def measure_model_performance(
    llm_model: str = DEFAULT_LLM_MODEL,
    embed_model: str = DEFAULT_EMBED_MODEL,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT
) -> Dict[str, Any]:
    """
    Executes an empirical performance benchmark across both the generation
    and embedding models on the host machine.
    """
    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": endpoint,
        "is_local_endpoint": endpoint.startswith("http://127.0.0.1") or endpoint.startswith("http://localhost"),
        "llm_model": llm_model,
        "embed_model": embed_model,
        "embedding_dim": None,
        "single_embed_latency_ms": None,
        "batch_embed_latency_ms": None,
        "batch_embed_per_item_ms": None,
        "cold_generation_latency_ms": None,
        "warm_generation_latency_ms": None,
        "generation_tokens_per_second": None,
        "system_ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "system_ram_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "system_ram_used_percent": psutil.virtual_memory().percent,
        "process_ram_rss_mb": round(psutil.Process().memory_info().rss / (1024**2), 2),
        "status": "success"
    }

    # 1. Embedding benchmark
    single_text = "HVF Armoured Hull Fabrication standard welding protocol and NDT criteria."
    t0 = time.time()
    single_vec = generate_embedding(single_text, model=embed_model, endpoint=endpoint)
    results["single_embed_latency_ms"] = round((time.time() - t0) * 1000.0, 2)
    results["embedding_dim"] = int(single_vec.shape[0])

    batch_texts = [
        "Plate edge beveling angle tolerance must not exceed +/- 0.5 degrees.",
        "Laser tracker 3D datum verification on hull station nodes.",
        "Induction pre-heating to 180 C for low-hydrogen electrodes.",
        "Phased Array Ultrasonic Testing PAUT seam acceptance."
    ]
    t0 = time.time()
    batch_vecs = generate_embeddings(batch_texts, model=embed_model, endpoint=endpoint)
    results["batch_embed_latency_ms"] = round((time.time() - t0) * 1000.0, 2)
    results["batch_embed_per_item_ms"] = round(results["batch_embed_latency_ms"] / len(batch_texts), 2)

    # 2. Text generation benchmark
    test_prompt = "State the importance of pre-heating in high-tensile steel welding in two concise sentences."
    gen_result = generate_response(
        test_prompt,
        model=llm_model,
        temperature=0.1,
        max_tokens=64,
        endpoint=endpoint
    )
    results["warm_generation_latency_ms"] = gen_result["total_duration_ms"]
    results["generation_tokens_per_second"] = gen_result["tokens_per_second"]

    results["process_ram_rss_mb"] = round(psutil.Process().memory_info().rss / (1024**2), 2)
    results["system_ram_available_gb"] = round(psutil.virtual_memory().available / (1024**3), 2)

    return results


if __name__ == "__main__":
    print("Executing rag_engine build verification...")
    res = rebuild_faiss_index()
    print("Rebuild status:", res)
    sample_retrieval = retrieve_relevant_chunks("What is the pre-heating temperature for hull welding?")
    print(f"Sample retrieval: {len(sample_retrieval)} chunks retrieved.")
    if sample_retrieval:
        print("Top citation:", sample_retrieval[0]["citation"])
        print("Top score:", sample_retrieval[0]["score"])
