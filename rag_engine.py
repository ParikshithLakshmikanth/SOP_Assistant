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
    Removes all chunks associated with a specific document ID from the FAISS
    index and metadata, updating the manifest and saving atomically.
    
    Args:
        document_id: Document ID to remove (e.g. 'HVF/AVNL/SOP-MBT/HW-101').
        index_dir: Target FAISS directory.
        
    Returns:
        Dict[str, Any]: Removal summary (removed_count, remaining_count, status).
    """
    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None or not metadata:
        return {"removed_count": 0, "remaining_count": 0, "status": "index_not_found"}

    indices_to_remove = [
        i for i, chunk in enumerate(metadata)
        if chunk.get("document_id") == document_id
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
            if d.get("document_id") != document_id
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
    Embeds and indexes a list of chunk dictionaries into the FAISS index.
    Supports incremental indexing and automatic duplicate replacement.
    
    Args:
        chunks: List of chunk dictionaries conforming to Phase 1 schema.
        index_dir: Path to directory storing index.
        batch_size: Batch size for Ollama embeddings.
        replace_existing: If True, purges prior chunks with the same document_id.
        endpoint: Local Ollama URL.
        embed_model: Registered Ollama embedding model.
        
    Returns:
        Dict[str, Any]: Indexing summary metrics.
    """
    if not chunks:
        logger.warning("index_chunks called with empty chunks list.")
        return {"indexed_chunks": 0, "total_chunks": 0, "status": "empty_input"}

    # Load existing or create new index
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

    # Group new chunks by document_id
    docs_incoming = set(c.get("document_id") for c in chunks if c.get("document_id"))

    # Handle duplicates if requested
    if replace_existing:
        for doc_id in docs_incoming:
            remove_document_from_index(doc_id, index_dir=index_dir)
        # Reload after removals
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

    # Generate embeddings for new chunks
    texts = [c["chunk_text"] for c in chunks]
    t0 = time.time()
    vectors = generate_embeddings(
        texts,
        model=embed_model,
        batch_size=batch_size,
        endpoint=endpoint,
        normalize=True
    )
    embed_duration = time.time() - t0

    # Add to FAISS index
    index.add(vectors)

    # Append to metadata
    metadata.extend(chunks)

    # Update manifest
    manifest["chunk_count"] = index.ntotal
    manifest["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # Update document inventory in manifest
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

    # Persist atomically
    save_faiss_index(index, metadata, manifest, index_dir=index_dir)

    return {
        "indexed_chunks": len(chunks),
        "total_index_chunks": index.ntotal,
        "embedding_duration_s": round(embed_duration, 2),
        "documents_affected": list(docs_incoming),
        "status": "success"
    }


def index_documents(
    documents: List[Dict[str, Any]],
    index_dir: str = DEFAULT_INDEX_DIR,
    batch_size: int = 16,
    replace_existing: bool = True
) -> Dict[str, Any]:
    """
    Extracts all chunks from a list of processed document objects and indexes them.
    
    Args:
        documents: List of document dicts returned by document_processor.process_pdf().
        index_dir: Storage path for FAISS index.
        batch_size: Embedding batch size.
        replace_existing: Whether to overwrite existing document records.
        
    Returns:
        Dict[str, Any]: Combined indexing summary.
    """
    all_chunks: List[Dict[str, Any]] = []
    for doc in documents:
        doc_chunks = doc.get("chunks", [])
        all_chunks.extend(doc_chunks)

    return index_chunks(
        all_chunks,
        index_dir=index_dir,
        batch_size=batch_size,
        replace_existing=replace_existing
    )


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
# PASSAGE RETRIEVAL & FILTERING
# ============================================================================

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
    score_threshold: Optional[float] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    embed_model: str = DEFAULT_EMBED_MODEL
) -> List[Dict[str, Any]]:
    """
    Performs vector similarity search in the FAISS index to retrieve the most
    relevant document passages for a query.
    
    Guarantees:
    - Normalizes query vector for exact cosine similarity calculation.
    - Preserves all source document, revision, section, and page information.
    - Accurately applies document_id, logical_sop_id, and revision filters.
    - Returns non-calibrated inner product similarity scores directly.
    
    Args:
        query: User question or search query string.
        top_k: Maximum number of relevant chunks to return.
        document_id: Optional filter for a specific document ID.
        logical_sop_id: Optional filter for an SOP category (e.g. 'HVF_SOP_1_Hull_Welding').
        revision: Optional filter for a revision string.
        score_threshold: Minimum cosine similarity score.
        index_dir: FAISS directory.
        endpoint: Ollama endpoint.
        embed_model: Ollama embedding model.
        
    Returns:
        List[Dict[str, Any]]: Ranked list of matching chunks with similarity scores.
    """
    if not query or not query.strip():
        return []

    index, metadata, manifest = load_faiss_index(index_dir)
    if index is None or index.ntotal == 0 or not metadata:
        logger.warning(f"No FAISS index available in {index_dir} for query: {query[:30]}")
        return []

    # 1. Embed and normalize query vector
    q_vec = generate_embedding(
        query,
        model=embed_model,
        endpoint=endpoint,
        normalize=True
    )
    q_arr = q_vec.reshape(1, -1).astype(np.float32)

    # 2. Search FAISS
    # If filters are requested, fetch a wider pool to guarantee top_k filtered results
    has_filters = bool(document_id or logical_sop_id or revision)
    k_search = min(index.ntotal, top_k * 5 if has_filters else top_k)

    scores, indices = index.search(q_arr, k_search)

    results: List[Dict[str, Any]] = []
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

        # Apply Revision filter
        if revision and revision.lower() not in raw_chunk.get("revision", "").lower():
            continue

        result_item = dict(raw_chunk)
        result_item["score"] = float(score)
        result_item["citation"] = format_citation(raw_chunk)

        results.append(result_item)
        if len(results) >= top_k:
            break

    return results


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
    - Evaluates and flags insufficient evidence conditions.
    - Returns structured citation metadata alongside answer text.
    - Separates conversational dialogue context from authoritative document evidence.
    
    Returns:
        Dict[str, Any]:
            - answer (str)
            - citations (List[Dict[str, Any]])
            - is_insufficient (bool)
            - model (str)
            - tokens_per_second (float)
            - eval_count (int)
            - status (str)
    """
    if retrieved_chunks is None:
        retrieved_chunks = retrieve_relevant_chunks(
            query=question,
            top_k=top_k,
            endpoint=endpoint
        )

    if not retrieved_chunks:
        return {
            "answer": "The provided SOP documentation does not contain sufficient evidence to answer this question.",
            "citations": [],
            "is_insufficient": True,
            "model": model,
            "tokens_per_second": 0.0,
            "eval_count": 0,
            "status": "insufficient_evidence"
        }

    evidence_context, citations = build_evidence_context(retrieved_chunks, max_context_chars=16000)

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
        "- Present all relevant parameters, tolerances, and acceptance criteria in structured bullet points or a table.\n"
        "- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n"
        "- Insert the exact bracketed citation for every parameter.\n"
        "- If certain benchmarks are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- End with a complete, concluded response."
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
        model=model
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
    1. Retrieves relevant evidence passages from FAISS.
    2. Builds structured evidence context and citations.
    3. Yields progressive token stream from Gemma while returning citations immediately.
    
    Returns:
        Tuple[Generator[str, None, None], List[Dict[str, Any]], Dict[str, Any]]:
            - token_generator: Yields response text token by token.
            - citations: Structured citations list for UI rendering.
            - info: Metadata dict (retrieval_duration_ms, retrieved_chunks_count).
    """
    retrieval_t0 = time.time()
    chunks = retrieve_relevant_chunks(
        query=question,
        top_k=top_k,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        score_threshold=score_threshold,
        index_dir=index_dir,
        endpoint=endpoint
    )
    retrieval_duration_ms = (time.time() - retrieval_t0) * 1000.0

    if not chunks:
        def empty_gen():
            yield "The provided SOP documentation does not contain sufficient evidence to answer this question."

        info = {
            "retrieval_duration_ms": round(retrieval_duration_ms, 2),
            "retrieved_chunks_count": 0,
            "is_insufficient": True
        }
        return empty_gen(), [], info

    evidence_context, citations = build_evidence_context(chunks, max_context_chars=16000)

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
        "- Present all relevant parameters, tolerances, and acceptance criteria in structured bullet points or a table.\n"
        "- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n"
        "- Insert the exact bracketed citation for every parameter.\n"
        "- If certain benchmarks are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- End with a complete, concluded response."
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
        "is_insufficient": False
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
