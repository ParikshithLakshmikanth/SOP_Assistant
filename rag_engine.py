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

# Permissible physical and operational relationship predicates
ALLOWED_RELATIONSHIP_PREDICATES = {
    "PART_OF",
    "CONNECTED_TO",
    "SUPPORTS",
    "DRIVES",
    "SEALS",
    "LUBRICATES",
    "MEASURES",
    "CONTROLS",
    "MOUNTS",
    "INTERFACES_WITH",
}


# ============================================================================
# OLLAMA CONNECTION & MODEL DISCOVERY
# ============================================================================

def get_ollama_client(
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    timeout: Optional[float] = None
) -> ollama.Client:
    """
    Instantiates an Ollama Client bound to the specified local endpoint
    with an optional HTTP request timeout (in seconds).
    """
    if timeout is not None:
        return ollama.Client(host=endpoint, timeout=float(timeout))
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
    normalize: bool = True,
    timeout: float = 15.0
) -> np.ndarray:
    """
    Generates a 768-dimensional dense embedding for a single text input.
    """
    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty or whitespace-only text.")

    if not check_ollama_connection(endpoint, timeout=min(5.0, float(timeout))):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint, timeout=timeout)

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
        if isinstance(e, TimeoutError) or "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower():
            logger.error(f"Embedding generation timed out after {timeout}s: {e}")
            raise TimeoutError(f"Embedding generation timed out after {timeout}s: {e}") from e
        logger.error(f"Failed to generate embedding for text (len={len(text)}): {e}")
        raise RuntimeError(f"Embedding generation failed: {e}") from e
    finally:
        inner = getattr(client, "_client", None)
        if inner is not None and hasattr(inner, "close"):
            try:
                inner.close()
            except Exception:
                pass


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
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    timeout: float = 180.0
) -> Dict[str, Any]:
    """
    Executes synchronous text generation using the local Gemma model via Ollama.
    """
    if not prompt or not prompt.strip():
        raise ValueError("Prompt cannot be empty or whitespace-only.")

    if not check_ollama_connection(endpoint, timeout=min(5.0, float(timeout))):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint, timeout=timeout)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    effective_max_tokens = max(1, int(max_tokens))
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
        if isinstance(e, TimeoutError) or "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower():
            logger.error(f"Text generation timed out after {timeout}s with model {model}: {e}")
            raise TimeoutError(f"Text generation timed out after {timeout}s with model '{model}': {e}") from e
        logger.error(f"Text generation failed with model {model}: {e}")
        raise RuntimeError(f"Text generation failed with model '{model}': {e}") from e
    finally:
        inner = getattr(client, "_client", None)
        if inner is not None and hasattr(inner, "close"):
            try:
                inner.close()
            except Exception:
                pass


def stream_response(
    prompt: str,
    model: str = DEFAULT_LLM_MODEL,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1536,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    timeout: float = 180.0
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

    if not check_ollama_connection(endpoint, timeout=min(5.0, float(timeout))):
        raise ConnectionError(f"Ollama server unreachable at {endpoint}.")

    client = get_ollama_client(endpoint, timeout=timeout)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    effective_max_tokens = max(1, int(max_tokens))
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
        inner = getattr(client, "_client", None)
        if inner is not None and hasattr(inner, "close"):
            try:
                inner.close()
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
    revision_mode: Optional[str] = None,
    document_filter: Optional[str] = None,
    is_uncertain: Optional[bool] = None,
    top_k: int = 50,
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
        # Document filter
        if document_filter and document_filter != "All Documents" and document_filter != "All SOP Documents":
            df_norm = document_filter.strip().lower()
            c_fn = str(c.get("filename") or c.get("source_filename") or "").strip().lower()
            c_docid = str(c.get("document_id") or "").strip().lower()
            c_lsop = str(c.get("logical_sop_id") or "").strip().lower()
            if df_norm not in (c_fn, c_docid, c_lsop) and df_norm not in c_fn:
                continue

        # Revision filter
        if revision_mode:
            rev_m = revision_mode.strip().lower()
            if rev_m in ("v1", "v1 (baseline / archival)", "baseline", "v1_only"):
                if not is_v1_component(c):
                    continue
            elif rev_m in ("v2", "v2 (active / revised)", "revised", "v2_only"):
                if not is_v2_component(c):
                    continue

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


def filter_components(
    components: Optional[List[Dict[str, Any]]] = None,
    doc_filter: Optional[str] = None,
    revision_filter: Optional[str] = None,
    subsystem_filter: Optional[str] = None,
    entity_type_filter: Optional[str] = None,
    uncertainty_filter: Optional[str] = None,
    search_keyword: Optional[str] = None,
    index_dir: str = DEFAULT_INDEX_DIR
) -> List[Dict[str, Any]]:
    """
    Deterministic filtering for Component Explorer across document, revision,
    subsystem, entity classification, uncertainty status, and search keywords.
    """
    if components is None:
        components = load_components_metadata(index_dir)

    if not components:
        return []

    filtered = list(components)

    # 1. Document Filter
    if doc_filter and doc_filter not in ("All Documents", "All SOP Documents", "All"):
        df_clean = doc_filter.strip().lower()
        filtered = [
            c for c in filtered
            if df_clean in str(c.get("logical_sop_id", "")).lower()
            or df_clean in str(c.get("filename", "")).lower()
            or df_clean in str(c.get("source_filename", "")).lower()
            or df_clean in str(c.get("document_id", "")).lower()
        ]

    # 2. Revision Filter
    if revision_filter and revision_filter not in ("All Revisions", "All"):
        rf_clean = revision_filter.strip().lower()
        if "v1" in rf_clean or "baseline" in rf_clean:
            filtered = [c for c in filtered if is_v1_component(c)]
        elif "v2" in rf_clean or "revised" in rf_clean or "active" in rf_clean:
            filtered = [c for c in filtered if is_v2_component(c)]

    # 3. Subsystem Filter
    if subsystem_filter and subsystem_filter not in ("All Subsystems", "All"):
        sf_clean = subsystem_filter.strip().lower()
        filtered = [
            c for c in filtered
            if sf_clean == str(c.get("subsystem", "")).strip().lower()
            or sf_clean == str(c.get("parent_subsystem", "")).strip().lower()
        ]

    # 4. Entity Type Filter (Default: Physical Components, Assemblies & Subsystems)
    if entity_type_filter and entity_type_filter not in ("All Entity Types", "All Extracted Entities (Unfiltered)", "All"):
        if entity_type_filter in (
            "Physical Components & Assemblies (Default)",
            "Physical Components, Assemblies & Subsystems (Default)",
            "Physical Components & Assemblies",
            "PHYSICAL_COMPONENTS_ONLY"
        ):
            filtered = [c for c in filtered if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM")]
        else:
            filtered = [c for c in filtered if c.get("entity_type") == entity_type_filter]
    elif entity_type_filter is None:
        # Default when unspecified
        filtered = [c for c in filtered if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM")]

    # 5. Uncertainty / Confidence Filter
    if uncertainty_filter and uncertainty_filter not in ("All Records", "All Confidence Levels", "All"):
        if "High-Confidence" in uncertainty_filter:
            filtered = [c for c in filtered if not c.get("is_uncertain", False)]
        elif "Uncertain" in uncertainty_filter:
            filtered = [c for c in filtered if c.get("is_uncertain", False)]
        elif "Directly Stated" in uncertainty_filter:
            filtered = [c for c in filtered if c.get("evidence_status") == "DIRECTLY_STATED"]

    # 6. Search Keyword
    if search_keyword and search_keyword.strip():
        tokens = [t.lower() for t in search_keyword.strip().split() if len(t) >= 2]
        if tokens:
            scored = []
            for c in filtered:
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
                matches = sum(1 for tok in tokens if tok in searchable)
                if matches > 0:
                    scored.append((matches, c))
            scored.sort(key=lambda x: x[0], reverse=True)
            filtered = [item[1] for item in scored]
        else:
            filtered = []

    return filtered


def format_component_detail(comp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constructs a beginner-friendly structured detail dictionary for a component record,
    handling missing fields with explicit notes and preserving verifiable source provenance.
    """
    name = comp.get("component_name") or "Unnamed Component"
    entity_type = comp.get("entity_type") or "OTHER_REFERENCE"

    simple_desc = comp.get("simple_description")
    if not simple_desc or not str(simple_desc).strip():
        simple_desc = "No simplified explanation documented in SOP source."
        has_simple_desc = False
    else:
        has_simple_desc = True

    primary_func = comp.get("primary_function")
    if not primary_func or not str(primary_func).strip():
        primary_func = "No primary vehicle function explicitly documented in SOP source."
        has_primary_func = False
    else:
        has_primary_func = True

    assoc_subsystem = comp.get("parent_subsystem") or comp.get("subsystem")
    if not assoc_subsystem or not str(assoc_subsystem).strip():
        assoc_subsystem = "No parent assembly or subsystem explicitly assigned in SOP source."
        has_assoc_subsystem = False
    else:
        has_assoc_subsystem = True

    # Validate relationships (strictly only validated relationships with explicit source_reference)
    raw_rels = comp.get("relationships") or []
    validated_rels = []
    for r in raw_rels:
        tgt = r.get("target_component")
        rel_type = r.get("relationship_type", "CONNECTED_TO")
        src_ref = r.get("source_reference")
        if tgt and src_ref:
            validated_rels.append({
                "source_component": name,
                "relationship_type": rel_type,
                "target_component": tgt,
                "source_reference": src_ref
            })

    evidence_status = comp.get("evidence_status") or ("UNCERTAIN" if comp.get("is_uncertain") else "DIRECTLY_STATED")
    filename = comp.get("source_filename") or comp.get("filename") or "Unknown Document"
    revision = comp.get("revision") or ("Rev 2.0" if is_v2_component(comp) else "Rev 1.0")
    section = comp.get("section_reference") or "General Directives"
    page_number = comp.get("page_number") or 1

    supporting_passage = comp.get("supporting_source_passage") or comp.get("raw_context") or ""

    return {
        "component_id": comp.get("component_id", "CMP"),
        "component_name": name,
        "entity_type": entity_type,
        "simple_description": simple_desc,
        "has_simple_description": has_simple_desc,
        "primary_function": primary_func,
        "has_primary_function": has_primary_func,
        "associated_subsystem": assoc_subsystem,
        "has_associated_subsystem": has_assoc_subsystem,
        "relationships": validated_rels,
        "has_relationships": len(validated_rels) > 0,
        "evidence_status": evidence_status,
        "filename": filename,
        "revision": revision,
        "section": section,
        "page_number": page_number,
        "supporting_passage": supporting_passage,
        "material": comp.get("material_or_construction") or "Not specified in SOP",
        "location": comp.get("location_or_use") or "Not specified in SOP",
        "alternative_names": comp.get("alternative_names") or [],
        "technical_specifications": comp.get("technical_specifications") or "",
        "tooling_or_metrology": comp.get("tooling_or_metrology") or "",
        "acceptance_criteria": comp.get("acceptance_criteria") or "",
        "callout_warning": comp.get("callout_warning") or "",
        "is_uncertain": comp.get("is_uncertain", False),
        "uncertainty_reason": comp.get("uncertainty_reason", "")
    }


def compare_component_revisions(
    components: Optional[List[Dict[str, Any]]] = None,
    sop_filter: Optional[str] = None,
    entity_types: Optional[List[str]] = None,
    index_dir: str = DEFAULT_INDEX_DIR
) -> Dict[str, Any]:
    """
    Compares component records between Baseline (V1) and Revised (V2) SOPs.
    
    Categorizes components into:
      - 'added': Present in V2 but not in V1
      - 'removed': Present in V1 but not in V2
      - 'modified': Present in both revisions with documented differences in description,
                    function, technical specifications, or acceptance criteria
      - 'unchanged': Present in both revisions with identical specifications
      
    Args:
        components: Optional list of component records; if None, loads from components_metadata.json.
        sop_filter: Optional filter by logical_sop_id or source_filename.
        entity_types: Optional list of entity types to restrict comparison to (e.g. PHYSICAL_COMPONENT, ASSEMBLY).
        index_dir: Path to directory containing components_metadata.json.
        
    Returns:
        Dict containing:
            - 'summary': Counts for added, removed, modified, unchanged, total_compared
            - 'added': List of component records added in V2
            - 'removed': List of component records removed from V1
            - 'modified': List of dicts with {'component_name', 'v1', 'v2', 'diffs': [(field, val1, val2)]}
            - 'unchanged': List of dicts with {'component_name', 'v1', 'v2'}
    """
    if components is None:
        components = load_components_metadata(index_dir)
        
    filtered = components or []
    
    # Optional entity type filter
    if entity_types:
        filtered = [c for c in filtered if c.get("entity_type") in entity_types]
        
    # Optional SOP filter
    if sop_filter and sop_filter not in ("All Documents", "All SOP Documents", "All"):
        sf_clean = sop_filter.strip().lower()
        filtered = [
            c for c in filtered
            if sf_clean in str(c.get("logical_sop_id", "")).lower()
            or sf_clean in str(c.get("filename", "")).lower()
            or sf_clean in str(c.get("source_filename", "")).lower()
            or sf_clean in str(c.get("document_id", "")).lower()
        ]
        
    v1_comps = [c for c in filtered if is_v1_component(c)]
    v2_comps = [c for c in filtered if is_v2_component(c)]
    
    v1_by_name: Dict[str, Dict[str, Any]] = {}
    for c in v1_comps:
        name = str(c.get("component_name") or "").strip()
        if name and name not in v1_by_name:
            v1_by_name[name] = c
            
    v2_by_name: Dict[str, Dict[str, Any]] = {}
    for c in v2_comps:
        name = str(c.get("component_name") or "").strip()
        if name and name not in v2_by_name:
            v2_by_name[name] = c
            
    added: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    
    comparison_fields = [
        ("simple_description", "Simplified Explanation"),
        ("primary_function", "Primary Vehicle Function"),
        ("technical_specifications", "Technical Specifications & Tolerances"),
        ("acceptance_criteria", "Acceptance Criteria"),
        ("material_or_construction", "Material / Construction"),
        ("tooling_or_metrology", "Tooling & Metrology")
    ]
    
    for name, c2 in v2_by_name.items():
        if name not in v1_by_name:
            added.append(c2)
        else:
            c1 = v1_by_name[name]
            diffs = []
            for field_key, field_label in comparison_fields:
                v1_val = str(c1.get(field_key) or "").strip()
                v2_val = str(c2.get(field_key) or "").strip()
                if v1_val != v2_val:
                    diffs.append({
                        "field": field_key,
                        "label": field_label,
                        "v1_value": v1_val or "(Not specified)",
                        "v2_value": v2_val or "(Not specified)"
                    })
            if diffs:
                modified.append({
                    "component_name": name,
                    "entity_type": c2.get("entity_type", "PHYSICAL_COMPONENT"),
                    "v1": c1,
                    "v2": c2,
                    "diffs": diffs
                })
            else:
                unchanged.append({
                    "component_name": name,
                    "entity_type": c2.get("entity_type", "PHYSICAL_COMPONENT"),
                    "v1": c1,
                    "v2": c2
                })
                
    for name, c1 in v1_by_name.items():
        if name not in v2_by_name:
            removed.append(c1)
            
    # Sort results alphabetically by component name
    added.sort(key=lambda x: str(x.get("component_name", "")).lower())
    removed.sort(key=lambda x: str(x.get("component_name", "")).lower())
    modified.sort(key=lambda x: str(x.get("component_name", "")).lower())
    unchanged.sort(key=lambda x: str(x.get("component_name", "")).lower())
    
    total_distinct = len(added) + len(removed) + len(modified) + len(unchanged)
    
    return {
        "summary": {
            "total_compared": total_distinct,
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "unchanged_count": len(unchanged)
        },
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged
    }


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
    v2_boost: float = 0.03,
    embed_timeout: float = 15.0
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
        normalize=True,
        timeout=embed_timeout
    )
    q_arr = q_vec.reshape(1, -1).astype(np.float32)

    # 2. Search FAISS
    # Search all chunks in index so domain and revision re-ranking evaluates all candidates
    k_search = index.ntotal

    scores, indices = index.search(q_arr, k_search)

    # Detect domain context from query for focused lexical / subsystem alignment
    ql_raw = query.lower()
    ql_tokens = set(re.findall(r'\b[a-z0-9_]+\b', ql_raw))

    is_engine_domain = bool(
        re.search(r'\b(engine\s+alignment|powerpack|v12|engine\s+bay|trunnion|shaft\s+alignment|hydromount)\b', ql_raw)
        or ('engine' in ql_tokens and any(t in ql_tokens for t in ['alignment', 'align', 'hoisting', 'trunnion', 'mounting', 'bay', 'crankshaft', 'offset', 'steps', 'procedure']))
    )
    is_hull_domain = bool(
        re.search(r'\b(hull\s+welding|armoured\s+hull|hull\s+tub|glacis|sponson|gmaw|welding\s+cell|turnover\s+jig)\b', ql_raw)
        or ('hull' in ql_tokens and any(t in ql_tokens for t in ['weld', 'welding', 'assemblies', 'assembly', 'plate', 'plates', 'tub', 'sponson', 'glacis']))
    )
    is_turret_domain = bool(
        re.search(r'\b(turret|turret\s+mount|ceramic-hybrid|cross-roller|slip-ring|forj|rotary\s+joint|pinion|traverse)\b', ql_raw)
    )
    is_suspension_domain = bool(
        re.search(r'\b(suspension|torsion\s+bar|road-wheel|rotary\s+damper|track\s+system|magnetorheological|sprocket\s+alignment)\b', ql_raw)
        or ('suspension' in ql_tokens or 'torsion' in ql_tokens)
    )
    is_gun_domain = bool(
        re.search(r'\b(gun|bore\s+sighting|muzzle|recoil|thermal\s+sleeve|dynamic\s+muzzle|artillery|barrel)\b', ql_raw)
        or ('gun' in ql_tokens and any(t in ql_tokens for t in ['calibration', 'calibrate', 'bore', 'recoil', 'muzzle']))
    )

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

        # Targeted domain relevance adjustment
        fn = str(raw_chunk.get("filename", "")).lower()
        sec_title = str(raw_chunk.get("section_title", "")).lower()
        log_id = str(raw_chunk.get("logical_sop_id", "")).lower()

        domain_boost = 0.0
        if is_engine_domain:
            if "engine_alignment" in fn or "ea_309" in log_id:
                domain_boost += 0.18
                if "alignment" in sec_title or "shaft" in sec_title:
                    domain_boost += 0.06
                elif "hoisting" in sec_title or "trunnion" in sec_title:
                    domain_boost += 0.05
                elif "metrology" in sec_title or "hydromount" in sec_title:
                    domain_boost += 0.04
                if re.match(r'^section\s+[1-3]\.0', sec_title):
                    domain_boost += 0.04
            else:
                domain_boost -= 0.10

        elif is_hull_domain:
            if "hull_welding" in fn or "hw_101" in log_id:
                domain_boost += 0.18
                if "assembly" in ql_raw or "assemblies" in ql_raw:
                    if "assembly" in sec_title or "jig" in sec_title or "plate" in sec_title:
                        domain_boost += 0.04
                elif "benchmark" in ql_raw or "weld" in ql_raw or "parameter" in ql_raw:
                    if "welding" in sec_title or "multi-pass" in sec_title or "gmaw" in sec_title:
                        domain_boost += 0.06
                    elif "benchmarks" in sec_title or "metrology" in sec_title:
                        domain_boost += 0.04
            else:
                domain_boost -= 0.10

        elif is_turret_domain:
            if "turret_integration" in fn or "ti_204" in log_id:
                domain_boost += 0.18
            else:
                domain_boost -= 0.10

        elif is_suspension_domain:
            if "torsion_suspension" in fn or "ts_412" in log_id:
                domain_boost += 0.18
            else:
                domain_boost -= 0.10

        elif is_gun_domain:
            if "gun_calibration" in fn or "gc_515" in log_id:
                domain_boost += 0.18
            else:
                domain_boost -= 0.10

        eff_score = raw_score + domain_boost

        # Controlled V2 preference in "All revisions" mode among comparably relevant results
        if effective_mode == "all" and chunk_is_v2:
            eff_score += v2_boost

        result_item["effective_score"] = eff_score

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

    effective_max_chars = int(max_context_chars) if max_context_chars else 16000

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


# ============================================================================
# COMPONENT-AWARE RAG RETRIEVAL & CONTEXT SYNTHESIS (MINI PHASE 3)
# ============================================================================

def is_v2_component(comp: Dict[str, Any]) -> bool:
    """
    Deterministically determines whether a component record belongs to a revised (V2) or
    currently active operational SOP.
    
    Any document that is not an archival baseline (V1) document is an active,
    authoritative technical specification and is eligible for latest (V2) retrieval.
    """
    if comp.get("is_v2") is True:
        return True
    if comp.get("is_v1") is True:
        return False

    fname = str(comp.get("source_filename") or comp.get("filename", "")).lower().strip()
    rev = str(comp.get("revision", "")).lower().strip()

    if "uploaded" in rev or "uploaded" in fname:
        return True
    if fname.endswith("_v2.pdf") or fname.endswith("-v2.pdf") or "v2" in rev or "[version 2.0]" in rev:
        return True
    if fname in BASELINE_V1_FILENAMES or fname.endswith("_v1.pdf") or fname.endswith("-v1.pdf"):
        return False
    if "baseline" in rev or "archival" in rev:
        return False
    return True


def is_v1_component(comp: Dict[str, Any]) -> bool:
    """
    Deterministically determines whether a component record belongs to an archival baseline (V1) SOP.
    """
    if comp.get("is_v1") is True:
        return True
    if comp.get("is_v2") is True:
        return False

    fname = str(comp.get("source_filename") or comp.get("filename", "")).lower().strip()
    rev = str(comp.get("revision", "")).lower().strip()

    if "uploaded" in rev or "uploaded" in fname:
        return False
    if fname.endswith("_v2.pdf") or fname.endswith("-v2.pdf") or "v2" in rev or "[version 2.0]" in rev:
        return False
    if fname in BASELINE_V1_FILENAMES or fname.endswith("_v1.pdf") or fname.endswith("-v1.pdf"):
        return True
    if "baseline" in rev or "archival" in rev:
        return True
    clean_rev = rev.split("|")[0].strip()
    if clean_rev in ("v1.0", "v1", "rev 1", "rev 1.0", "version 1", "version 1.0"):
        return True
    return False


def format_component_citation(comp: Dict[str, Any]) -> str:
    """
    Constructs a uniform, traceable source citation string for a component record.
    Format: [Filename, Revision, Section, Page X]
    """
    fname = comp.get("source_filename") or comp.get("filename", "SOP.pdf")
    rev = comp.get("revision", "").split("|")[0].strip()
    sec = comp.get("section_reference", "General")
    sec_clean = re.sub(r'[\r\n]+', ' ', sec).split(' - ')[0].split(' : ')[0].strip()
    if len(sec_clean) > 40:
        sec_clean = sec_clean[:37] + "..."
    page = comp.get("page_number", 1)
    return f"[{fname}, {rev}, {sec_clean}, Page {page}]"


DEFAULT_GLOSSARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "component_glossary.json")


def load_component_glossary(glossary_path: Optional[str] = None) -> Dict[str, Any]:
    """Loads the structured component glossary from JSON storage."""
    path = glossary_path or DEFAULT_GLOSSARY_PATH
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load component glossary from {path}: {e}")
        return {}


def lookup_component_glossary(
    query_or_name: str,
    glossary_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Looks up a component or subsystem definition in the glossary by canonical name,
    alias, or query phrase.
    """
    glossary = load_component_glossary(glossary_path)
    if not glossary or not query_or_name:
        return None

    ql = query_or_name.lower().strip()
    ql_clean = re.sub(r'[^a-z0-9\s]', ' ', ql)
    tokens = [
        w for w in ql_clean.split()
        if w not in {
            'what', 'is', 'a', 'an', 'the', 'does', 'do', 'define', 'explain',
            'in', 'simple', 'words', 'terms', 'tell', 'me', 'about', 'mean',
            'meaning', 'of', 'please', 'describe'
        }
    ]
    candidate = ' '.join(tokens).strip()
    if not candidate:
        candidate = ql_clean.strip()

    # 1. Exact match on glossary key
    if candidate in glossary:
        return glossary[candidate]

    # 2. Exact match on canonical name or alias
    for key, data in glossary.items():
        canonical = data.get("canonical_name", "").lower()
        aliases = [a.lower() for a in data.get("aliases", [])]
        if candidate == canonical or candidate in aliases:
            return data

    # 3. Substring match
    for key, data in glossary.items():
        if key in candidate or any(a in candidate for a in [al.lower() for al in data.get("aliases", [])]):
            return data

    # 4. Partial token overlap
    for key, data in glossary.items():
        if candidate in key:
            return data

    return None


def format_basic_definition_response(
    entry: Dict[str, Any],
    query: str = ""
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Formats a beginner-friendly 6-part component definition response strictly grounded
    in validated SOP evidence and engineering glossary metadata.
    
    Structure:
    1. **What it is**
    2. **What it does**
    3. **Where it fits**
    4. **Related parts**
    5. **SOP reference**
    6. **Evidence note**
    """
    name = entry.get("canonical_name", "Component")
    what_it_is = entry.get("what_it_is", "")
    what_it_does = entry.get("what_it_does", "")
    where_it_fits = entry.get("where_it_fits", "Primary Vehicle Assembly")

    related = entry.get("related_parts", [])
    rel_str = ", ".join(related) if related else "None explicitly documented in this section."

    explicit_rels = entry.get("explicit_relationships", [])
    if explicit_rels:
        rel_lines = [f"- {r}" for r in explicit_rels]
        related_section = f"{rel_str}\n\n*Verified Connections:*\n" + "\n".join(rel_lines)
    else:
        related_section = rel_str

    doc = entry.get("sop_filename", "HVF SOP")
    rev = entry.get("revision", "Baseline / Revised")
    sec = entry.get("section", "Section 1.0")
    pg = entry.get("page_number", 1)
    sop_ref_text = f"{doc} ({rev}), {sec}, Page {pg}"

    status = entry.get("evidence_status", "DIRECTLY_STATED")
    context_note = entry.get("general_context_note", "")
    if status == "DIRECTLY_STATED":
        evidence_note = f"**DIRECTLY_STATED**: Documented directly in {doc} ({rev}). {context_note}"
    elif status == "INFERRED":
        evidence_note = f"**INFERRED**: Interpretation derived from documented functions and interface requirements in {doc}. {context_note}"
    else:
        evidence_note = (
            "**GENERAL_CONTEXT**: The available SOP passages identify this component but do not provide an exhaustive definition. "
            f"This explanation reflects standard armoured vehicle engineering context alongside documented SOP parameters. {context_note}"
        )

    text_parts = [
        f"### {name}\n",
        f"**What it is**\n{what_it_is}\n",
        f"**What it does**\n{what_it_does}\n",
        f"**Where it fits**\n{where_it_fits}\n",
        f"**Related parts**\n{related_section}\n",
        f"**SOP reference**\n{sop_ref_text}\n",
        f"**Evidence note**\n{evidence_note}"
    ]
    response_text = "\n".join(text_parts)

    rel_excerpt = f"Where it fits: {where_it_fits}. Related parts: {rel_str}."
    if explicit_rels:
        rel_excerpt += " Verified Connections: " + " ".join(explicit_rels)

    citations = [{
        "document_id": doc,
        "filename": doc,
        "logical_sop_id": doc.replace(".pdf", ""),
        "revision": rev,
        "section": sec,
        "section_title": sec,
        "page_number": pg,
        "chunk_id": f"GLOSSARY-{name.upper().replace(' ', '_')[:24]}",
        "evidence_status": status,
        "citation": sop_ref_text,
        "score": 1.0,
        "text_excerpt": f"{name}: {what_it_is} {what_it_does} {rel_excerpt} {sop_ref_text}"
    }]

    return response_text, citations


def detect_component_intent(
    query: str,
    index_dir: str = DEFAULT_INDEX_DIR
) -> Dict[str, Any]:
    """
    Detects user query intent across 8 categories:
    1. GENERAL_CONVERSATION: Conversational greetings, pleasantries, acknowledgments
    2. REVISION_CHANGES: V1 vs V2 component and procedural changes
    3. COMPONENT_RELATIONSHIPS: Component connections, interfaces, differences
    4. COMPONENT_OVERVIEW / ASSEMBLY_SUBSYSTEM: Component list, parts breakdown, assembly details
    5. COMPONENT_FUNCTION: Operational purpose, function, role
    6. BASIC_DEFINITION: Beginner-friendly definitions of components / subsystems
    7. TECHNICAL_SPECIFICATION: Specific mechanical tolerances, thicknesses, dimensions
    8. GENERAL_PROCEDURAL: Procedural execution, welding, maintenance, standard RAG
    """
    if not query or not query.strip():
        return {
            "is_component_intent": False,
            "category": "GENERAL_PROCEDURAL",
            "category_code": "F",
            "matched_entities": [],
            "confidence": 0.0,
            "reason": "Empty query"
        }

    ql = query.lower().strip()
    ql_clean = re.sub(r'[^a-z0-9\s]', '', ql)

    # 1. Category G: GENERAL_CONVERSATION (Greetings, pleasantries)
    greetings = {
        'hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon',
        'good evening', 'thanks', 'thank you', 'bye', 'help', 'who are you',
        'what can you do', 'ok', 'okay'
    }
    if ql_clean in greetings or re.match(r'^(hi|hello|hey|greetings|good\s+(?:morning|afternoon|evening)|help)[\s!.]*$', ql):
        return {
            "is_component_intent": False,
            "category": "GENERAL_CONVERSATION",
            "category_code": "G",
            "matched_entities": [],
            "confidence": 0.99,
            "reason": "Query is a conversational greeting or pleasantry; skips document retrieval."
        }

    # Extract matched component entities from metadata if available
    matched_entities: List[str] = []
    try:
        all_comps = load_components_metadata(index_dir)
        q_norm = re.sub(r'[^a-z0-9\s]', ' ', ql)
        seen = set()
        for c in all_comps:
            name = c.get("component_name", "")
            if not name or len(name) < 3:
                continue
            name_norm = re.sub(r'[^a-z0-9\s]', ' ', name.lower()).strip()
            if not name_norm:
                continue
            if f" {name_norm} " in f" {q_norm} " or q_norm.startswith(name_norm + " ") or q_norm.endswith(" " + name_norm):
                if name_norm not in seen:
                    seen.add(name_norm)
                    matched_entities.append(name)
    except Exception:
        pass

    # 2. Category E: V1 vs V2 Component / Procedure Changes (REVISION_CHANGES)
    rev_change_pattern = (
        re.search(r'\b(what\s+changed|changes?|differences?|compare)\b.*\b(v1|v2|baseline|revised|revision)\b', ql)
        or 'v1 and v2' in ql or 'between v1 and v2' in ql or 'v1 versus v2' in ql
    )
    comp_indicator_pattern = re.search(r'\b(components?|parts?|assembl(?:y|ies)|subsystems?|materials?|hardware|welding|procedure)\b', ql)
    if rev_change_pattern and (comp_indicator_pattern or 'v2' in ql or 'v1' in ql):
        return {
            "is_component_intent": True,
            "category": "REVISION_CHANGES",
            "category_code": "E",
            "matched_entities": matched_entities,
            "confidence": 0.95,
            "reason": "Query asks about differences/changes in components or procedures between revisions."
        }

    # 3. Category D: Component Relationships / Differences between components
    rel_pattern = re.search(
        r'\b(how\s+are\s+(?:these\s+|the\s+)?components\s+related|relationship\s+between|relationships?\s+of|'
        r'connect(?:ed|s)?\s+(?:to|with)|interface(?:s)?\s+with|interact(?:s)?\s+with|'
        r'mounted?\s+(?:to|on)|how\s+do\s+.*\s+(?:connect|interface|relate)|'
        r'how\s+is\s+.*\s+(?:connect|connected|interfaced|related)|'
        r'difference\s+between\s+(?:a\s+|the\s+)?.*\s+and\s+(?:a\s+|the\s+)?)\b',
        ql
    )
    if rel_pattern and (len(matched_entities) >= 1 or any(w in ql for w in ['component', 'components', 'part', 'parts', 'assembly', 'related', 'connection', 'connected', 'connect', 'interface', 'difference', 'between'])):
        return {
            "is_component_intent": True,
            "category": "COMPONENT_RELATIONSHIPS",
            "category_code": "D",
            "matched_entities": matched_entities,
            "confidence": 0.92,
            "reason": "Query asks about relationships, mechanical connections, interfaces, or comparative differences between components."
        }

    # 4. Category A / C: Component Overview / Breakdown / Assemblies
    parts_contain_pattern = re.search(
        r'\b(what\s+are\s+the\s+(?:main\s+|basic\s+)?parts\s+of|'
        r'what\s+does\s+.*\s+contain|'
        r'what\s+are\s+the\s+(?:main\s+|basic\s+)?components\s+of|'
        r'breakdown\s+of\s+(?:the\s+)?(?:components|parts|assemblies))\b',
        ql
    )
    if parts_contain_pattern:
        if any(w in ql for w in ['powerpack', 'v12 powerpack']):
            return {
                "is_component_intent": True,
                "category": "ASSEMBLY_SUBSYSTEM",
                "category_code": "C",
                "matched_entities": matched_entities,
                "confidence": 0.92,
                "reason": "Query asks for breakdown of powerpack subsystem components."
            }
        return {
            "is_component_intent": True,
            "category": "COMPONENT_OVERVIEW",
            "category_code": "A",
            "matched_entities": matched_entities,
            "confidence": 0.90,
            "reason": "Query asks for an overview, list, or breakdown of equipment components/parts."
        }

    overview_pattern = re.search(
        r'\b(what\s+are\s+the\s+(?:main\s+|basic\s+)?(?:components|parts|assemblies|subsystems)|'
        r'what\s+does\s+.*\s+say\s+about\s+(?:its\s+|the\s+)?(?:main\s+|basic\s+)?(?:components|parts|assemblies|subsystems)|'
        r'main\s+assemblies\s+of|basic\s+assemblies\s+of|'
        r'basic\s+parts\s+of|list\s+(?:all\s+|the\s+)?(?:components|assemblies|subsystems)|list\s+of\s+(?:components|assemblies|subsystems)|'
        r'(?:components|assemblies|subsystems)\s+of\s+the|parts\s+of\s+the|breakdown\s+of\s+(?:the\s+)?(?:components|assemblies)|'
        r'all\s+(?:components|assemblies)\s+of|what\s+(?:components|assemblies)\s+(?:make\s+up|belong))\b',
        ql
    )
    if overview_pattern and not any(w in ql for w in ['powerpack', 'v12 powerpack']):
        if any(w in ql for w in ['assemblies', 'assembly', 'subsystem', 'subsystems']):
            return {
                "is_component_intent": True,
                "category": "ASSEMBLY_SUBSYSTEM",
                "category_code": "C",
                "matched_entities": matched_entities,
                "confidence": 0.92,
                "reason": "Query asks for an overview or breakdown of assemblies or subsystems."
            }
        return {
            "is_component_intent": True,
            "category": "COMPONENT_OVERVIEW",
            "category_code": "A",
            "matched_entities": matched_entities,
            "confidence": 0.90,
            "reason": "Query asks for an overview, list, or breakdown of equipment components."
        }

    # Category C: Assembly or Subsystem Explanation
    assembly_pattern = re.search(
        r'\b(explain|describe|detail|overview\s+of|main\s+(?:components|assemblies)\s+of\s+(?:the\s+)?|what\s+(?:does\s+.*\s+say\s+about|are)\s+(?:the\s+)?main\s+assemblies)\b.*\b(assembly|assemblies|subsystem|subsystems|powerpack|mount\s+system|suspension\s+system|turret\s+basket|hull\s+tub|hull\s+welding)\b',
        ql
    ) or any(w in ql for w in ['v12 powerpack', 'turret basket assembly', 'needle-bearing housing assembly'])
    if assembly_pattern:
        return {
            "is_component_intent": True,
            "category": "ASSEMBLY_SUBSYSTEM",
            "category_code": "C",
            "matched_entities": matched_entities,
            "confidence": 0.90,
            "reason": "Query asks to explain or detail a complex assembly or subsystem."
        }

    # 5. Category B: Individual Component Explanation / Function
    func_pattern = re.search(
        r'\b(function\s+of|purpose\s+of|role\s+of|what\s+does\s+(?:the\s+|a\s+)?.*do|what\s+is\s+(?:the\s+|a\s+)?(?:function|purpose|role))\b',
        ql
    )
    if func_pattern or (len(matched_entities) >= 1 and any(w in ql for w in ['function', 'purpose', 'role', 'what does', 'used for'])):
        return {
            "is_component_intent": True,
            "category": "COMPONENT_FUNCTION",
            "category_code": "B",
            "matched_entities": matched_entities,
            "confidence": 0.88,
            "reason": "Query asks about the specific operational function or role of an individual component."
        }

    # 6. Category BASIC_DEFINITION: Beginner-friendly Definition of Component / Subsystem
    def_pattern = re.search(
        r'^(?:what\s+is\s+(?:an?\s+|the\s+)?|what\s+exactly\s+is\s+(?:an?\s+|the\s+)?|'
        r'define\s+(?:an?\s+|the\s+)?|tell\s+me\s+about\s+(?:an?\s+|the\s+)?|'
        r'explain\s+(?:an?\s+|the\s+)?|'
        r'what\s+does\s+(?:an?\s+|the\s+)?.*\s+mean\??|'
        r'what\s+is\s+meant\s+by\s+(?:an?\s+|the\s+)?)([^?]+)\??$',
        ql
    )
    if def_pattern:
        subject = def_pattern.group(1).strip()
        spec_words = ['preheating', 'temperature', 'torque', 'tolerance', 'thickness', 'pressure', 'clearance', 'voltage', 'rpm']
        proc_words = ['procedure', 'sequence', 'process', 'step', 'how']
        if not any(w in subject for w in spec_words + proc_words):
            return {
                "is_component_intent": True,
                "category": "BASIC_DEFINITION",
                "category_code": "DEF",
                "matched_entities": matched_entities,
                "confidence": 0.95,
                "reason": f"Query asks for a basic definition or beginner explanation of '{subject}'."
            }

    # 7. Category TECHNICAL_SPECIFICATION: Specific mechanical tolerances, dimensions, thicknesses
    if ('thickness' in ql or 'tolerance' in ql) and not any(w in ql for w in ['preheating temperature', 'torque sequence']):
        return {
            "is_component_intent": False,
            "category": "TECHNICAL_SPECIFICATION",
            "category_code": "SPEC",
            "matched_entities": matched_entities,
            "confidence": 0.88,
            "reason": "Query asks for technical specification parameters, dimensions, or tolerances."
        }

    # 8. Category F: General SOP Procedural Questions (Default)
    return {
        "is_component_intent": False,
        "category": "GENERAL_PROCEDURAL",
        "category_code": "F",
        "matched_entities": matched_entities,
        "confidence": 0.85,
        "reason": "Query concerns procedures, technical tolerances, parameters, or general SOP execution."
    }


def resolve_conversational_query(
    question: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    components: Optional[List[Dict[str, Any]]] = None,
    index_dir: str = DEFAULT_INDEX_DIR
) -> Tuple[str, Optional[str]]:
    """
    Resolves pronoun and generic follow-up references ('this component', 'it', 'this assembly',
    'which assembly does it belong to', etc.) by identifying the antecedent component from
    recent conversation turns.
    
    Returns:
        Tuple[str, Optional[str]]: (effective_query, antecedent_component_name)
    """
    if not conversation_history:
        return question, None

    ql = question.lower().strip()
    follow_up_cues = [
        "this component", "the component", "this part", "this assembly", "the assembly",
        "which assembly does it belong to", "belong to", "connect to it",
        "what other components connect", "what happens if this component",
        "what changed in this component", "which sop section describes its",
        "what does it do", "what does this do", "does it do", "how is it",
        "describe its", "explain it", "how does it", "what is it"
    ]

    words = ql.split()
    needs_antecedent = any(cue in ql for cue in follow_up_cues) or (
        len(words) <= 10 and any(p in words for p in ["it", "its", "this", "these", "that"])
    )

    if not needs_antecedent:
        return question, None

    found_comp = None

    # 1. Pattern extraction from conversation turns (e.g. "Explain the <Component> (<ENTITY_TYPE>)")
    for turn in reversed(conversation_history):
        content = str(turn.get("content", ""))
        m = re.search(r'(?:Explain the|Component:|about the)\s+([A-Za-z0-9\s\-]+?)(?:\s+\([A-Z_]+\)|$|\s+based)', content, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            if len(cand) >= 3 and cand.lower() not in ("it", "this", "these", "the component"):
                found_comp = cand
                break

    # 2. Metadata matching against known component records if not resolved by pattern
    if not found_comp:
        comps = components if components is not None else load_components_metadata(index_dir)
        if comps:
            comp_names = sorted(list({str(c.get("component_name", "")).strip() for c in comps if c.get("component_name")}), key=len, reverse=True)
            for turn in reversed(conversation_history):
                content = str(turn.get("content", ""))
                for name in comp_names:
                    if len(name) >= 3 and name.lower() in content.lower():
                        found_comp = name
                        break
                if found_comp:
                    break

    if found_comp and found_comp.lower() not in ql:
        effective_query = f"{question} (regarding component: {found_comp})"
        return effective_query, found_comp

    return question, found_comp


def retrieve_component_aware_evidence(
    query: str,
    top_k_chunks: int = 5,
    top_k_components: int = 8,
    document_id: Optional[str] = None,
    logical_sop_id: Optional[str] = None,
    revision: Optional[str] = None,
    revision_mode: Optional[str] = None,
    score_threshold: Optional[float] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    embed_model: str = DEFAULT_EMBED_MODEL,
    v2_boost: float = 0.03,
    embed_timeout: float = 15.0
) -> Dict[str, Any]:
    """
    Hybrid component-aware retrieval engine:
    1. Detects query intent across Categories A-F.
    2. Performs FAISS vector similarity search over chunk passages.
    3. For component queries (Categories A-E), retrieves, filters, and ranks structured
       component metadata records and explicitly validated relationships.
    4. Applies strict revision policy (V2-first, V1-only, or All) across both vector
       chunks and structured component metadata.
    5. Excludes OTHER_REFERENCE, TOOL_OR_INSTRUMENT, and DOCUMENT_OR_CERTIFICATE from physical components.
    """
    intent = detect_component_intent(query, index_dir=index_dir)

    # Normalize effective revision mode (V2-first default)
    effective_mode: str = "v2"
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
    elif revision:
        r_str = revision.strip().lower()
        if r_str in ["v2", "v2_only", "revision_v2", "latest"] or r_str.startswith("v2 —") or r_str.startswith("v2 -"):
            effective_mode = "v2"
        elif r_str in ["v1", "v1_only", "baseline_v1", "baseline"] or r_str.startswith("v1 —") or r_str.startswith("v1 -"):
            effective_mode = "v1"
        elif r_str in ["all", "all_revisions", "all revisions"] or r_str.startswith("all revisions"):
            effective_mode = "all"

    # Fast bypass for pure conversational greetings
    if intent.get("category") == "GENERAL_CONVERSATION":
        return {
            "chunks": [],
            "components": [],
            "supporting_entities": [],
            "relationships": [],
            "intent": intent,
            "is_component_query": False,
            "revision_policy": effective_mode,
            "total_components_scanned": 0,
            "filtered_components_count": 0
        }

    # Retrieve semantic chunks from FAISS with consistent revision mode
    chunks = retrieve_relevant_chunks(
        query=query,
        top_k=top_k_chunks,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        revision_mode=effective_mode,
        score_threshold=score_threshold,
        index_dir=index_dir,
        endpoint=endpoint,
        embed_model=embed_model,
        v2_boost=v2_boost,
        embed_timeout=embed_timeout
    )

    if not intent["is_component_intent"]:
        return {
            "intent": intent,
            "is_component_query": False,
            "chunks": chunks,
            "components": [],
            "supporting_entities": [],
            "relationships": [],
            "revision_mode": effective_mode,
            "citations": [c.get("citation") for c in chunks if c.get("citation")]
        }

    all_comps = load_components_metadata(index_dir)
    if not all_comps:
        return {
            "intent": intent,
            "is_component_query": True,
            "chunks": chunks,
            "components": [],
            "supporting_entities": [],
            "relationships": [],
            "revision_mode": effective_mode,
            "citations": [c.get("citation") for c in chunks if c.get("citation")]
        }

    # Filter components
    physical_candidates = []
    supporting_candidates = []

    STOP_WORDS = {
        'what', 'are', 'the', 'is', 'a', 'an', 'of', 'in', 'and', 'for', 'to', 'how',
        'do', 'does', 'did', 'these', 'this', 'that', 'with', 'between', 'explain',
        'describe', 'function', 'purpose', 'role', 'components', 'parts', 'main',
        'basic', 'tell', 'me', 'about', 'list', 'show', 'all'
    }

    ql = query.lower().strip()
    clean_q = re.sub(r'[^a-zA-Z0-9\s-]', ' ', ql)
    q_tokens = [t for t in re.split(r'[\s-]+', clean_q) if len(t) >= 3 and t not in STOP_WORDS]
    matched_names_lower = [m.lower() for m in intent.get("matched_entities", [])]

    for c in all_comps:
        # Revision filter
        c_is_v2 = is_v2_component(c)
        c_is_v1 = is_v1_component(c)
        if effective_mode == "v2" and not c_is_v2:
            continue
        elif effective_mode == "v1" and c_is_v2:
            continue

        # Document ID filter
        if document_id and c.get("document_id") != document_id:
            continue

        # Logical SOP ID filter
        if logical_sop_id and c.get("logical_sop_id") != logical_sop_id:
            continue

        # Specific Revision String filter
        if revision and revision.lower() not in ("v1", "v2", "all"):
            if revision.lower() not in str(c.get("revision", "")).lower():
                continue

        etype = c.get("entity_type", "")
        # NEVER treat OTHER_REFERENCE as physical component or supporting entity
        if etype == "OTHER_REFERENCE":
            continue

        # Score matching
        name = str(c.get("component_name", "")).lower()
        desc = str(c.get("simple_description", "")).lower()
        func = str(c.get("primary_function", "")).lower()
        sub = str(c.get("parent_subsystem") or c.get("subsystem") or "").lower()
        mat = str(c.get("material_or_construction", "")).lower()
        spec = str(c.get("technical_specifications", "")).lower()
        search_blob = f"{name} {desc} {func} {sub} {mat} {spec}"

        score = 0.0
        # For revision comparison queries, establish baseline relevance so both revisions are retrieved
        if intent.get("category") == "REVISION_CHANGES":
            score += 1.0

        # Check matched entity from query
        for m_name in matched_names_lower:
            if m_name in name:
                score += 25.0
            elif m_name in search_blob:
                score += 8.0

        # Exact component name & subsystem tokens in query
        for tok in q_tokens:
            if tok in sub:
                score += 15.0
            if tok in name:
                score += 10.0
            elif tok in search_blob:
                score += 2.0

        # Domain alignment boost for components
        c_fn = str(c.get("source_filename") or c.get("filename", "")).lower()
        if "hull" in q_tokens or "welding" in q_tokens:
            if "hull_welding" in c_fn or "armoured hull" in sub:
                score += 12.0
            else:
                score -= 10.0
        elif "engine" in q_tokens or "powerpack" in q_tokens:
            if "engine_alignment" in c_fn or "powerpack" in sub:
                score += 12.0
            else:
                score -= 10.0
        elif "turret" in q_tokens:
            if "turret_integration" in c_fn or "turret" in sub:
                score += 12.0
            else:
                score -= 10.0
        elif "suspension" in q_tokens or "torsion" in q_tokens:
            if "torsion_suspension" in c_fn or "suspension" in sub:
                score += 12.0
            else:
                score -= 10.0
        elif "gun" in q_tokens or "muzzle" in q_tokens:
            if "gun_calibration" in c_fn or "gun" in sub:
                score += 12.0
            else:
                score -= 10.0

        # Entity type boost when assemblies or structural components are queried
        if "assemblies" in ql or "assembly" in ql:
            if etype == "ASSEMBLY":
                score += 15.0
            elif etype == "PHYSICAL_COMPONENT":
                score += 8.0

        # V2 boost in "all" mode
        if effective_mode == "all" and c_is_v2:
            score += 0.05

        if score <= 0.0:
            continue

        item = dict(c)
        item["retrieval_score"] = score
        item["is_v2"] = c_is_v2
        item["citation"] = format_component_citation(c)

        if etype in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"):
            physical_candidates.append(item)
        elif etype in ("MATERIAL", "TECHNICAL_PARAMETER", "PROCESS_OR_OPERATION"):
            supporting_candidates.append(item)

    # Sort candidates
    physical_candidates.sort(key=lambda x: x["retrieval_score"], reverse=True)
    supporting_candidates.sort(key=lambda x: x["retrieval_score"], reverse=True)

    # In All revisions mode (especially for revision comparison), ensure both V1 and V2 are represented
    if effective_mode == "all" and len(physical_candidates) > 1:
        v2_candidates = [c for c in physical_candidates if c["is_v2"]]
        v1_candidates = [c for c in physical_candidates if not c["is_v2"]]
        if v2_candidates and v1_candidates:
            half_k = max(1, top_k_components // 2)
            v2_selected = v2_candidates[:half_k + (top_k_components % 2)]
            v1_selected = v1_candidates[:half_k]
            combined = []
            for v2_c, v1_c in zip(v2_selected, v1_selected):
                combined.append(v2_c)
                combined.append(v1_c)
            if len(v2_selected) > len(v1_selected):
                combined.extend(v2_selected[len(v1_selected):])
            elif len(v1_selected) > len(v2_selected):
                combined.extend(v1_selected[len(v2_selected):])
            selected_physical = combined[:top_k_components]
        else:
            selected_physical = physical_candidates[:top_k_components]
    else:
        selected_physical = physical_candidates[:top_k_components]

    selected_supporting = supporting_candidates[:4]

    # Collect validated relationships
    validated_relationships: List[Dict[str, Any]] = []
    seen_rel = set()
    for comp in selected_physical:
        src_name = comp.get("component_name", "")
        for rel in comp.get("relationships", []):
            pred = rel.get("relationship_type", "")
            tgt = rel.get("target_component", "")
            src_ref = rel.get("source_reference", "")
            if pred in ALLOWED_RELATIONSHIP_PREDICATES and tgt and src_ref:
                rel_key = (src_name, pred, tgt)
                if rel_key not in seen_rel:
                    seen_rel.add(rel_key)
                    validated_relationships.append({
                        "source_component": src_name,
                        "relationship_type": pred,
                        "target_component": tgt,
                        "source_reference": src_ref,
                        "source_filename": comp.get("source_filename") or comp.get("filename"),
                        "revision": comp.get("revision")
                    })

    # Merged citations
    merged_citations: List[Dict[str, Any]] = []
    seen_citations = set()

    for comp in selected_physical:
        c_dict = {
            "filename": comp.get("source_filename") or comp.get("filename"),
            "document_id": comp.get("document_id"),
            "revision": comp.get("revision"),
            "section_title": comp.get("section_reference", "General"),
            "page_number": comp.get("page_number", 1),
            "component_name": comp.get("component_name"),
            "entity_type": comp.get("entity_type"),
            "evidence_status": comp.get("evidence_status", "DIRECTLY_STATED"),
            "citation": comp["citation"]
        }
        key = (c_dict["filename"], c_dict["revision"], c_dict["page_number"])
        if key not in seen_citations:
            seen_citations.add(key)
            merged_citations.append(c_dict)

    for ch in chunks:
        ch_dict = {
            "filename": ch.get("filename"),
            "document_id": ch.get("document_id"),
            "revision": ch.get("revision"),
            "section_title": ch.get("section_title"),
            "page_number": ch.get("page_number"),
            "page_numbers": ch.get("page_numbers"),
            "citation": ch.get("citation"),
            "score": ch.get("score")
        }
        key = (ch_dict["filename"], ch_dict["revision"], ch_dict["page_number"])
        if key not in seen_citations:
            seen_citations.add(key)
            merged_citations.append(ch_dict)

    return {
        "intent": intent,
        "is_component_query": bool(selected_physical or selected_supporting or chunks),
        "chunks": chunks,
        "components": selected_physical,
        "supporting_entities": selected_supporting,
        "relationships": validated_relationships,
        "revision_mode": effective_mode,
        "citations": merged_citations
    }


def build_component_evidence_context(
    retrieved_components: List[Dict[str, Any]],
    retrieved_chunks: List[Dict[str, Any]],
    validated_relationships: Optional[List[Dict[str, Any]]] = None,
    supporting_entities: Optional[List[Dict[str, Any]]] = None,
    max_context_chars: int = 16000
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Constructs a structured component knowledge block and merges it with semantic
    SOP chunk passages for injection into LLM prompts.
    """
    blocks = []
    citations = []

    # 1. Authoritative Structured Components
    if retrieved_components:
        blocks.append("### AUTHORITATIVE STRUCTURED COMPONENT KNOWLEDGE:")
        for i, c in enumerate(retrieved_components):
            c_num = i + 1
            citation_str = c.get("citation", format_component_citation(c))
            name = c.get("component_name", "Unknown Component")
            etype = c.get("entity_type", "PHYSICAL_COMPONENT")
            fname = c.get("source_filename") or c.get("filename", "SOP.pdf")
            rev = c.get("revision", "N/A")
            sec = c.get("section_reference", "General")
            page = c.get("page_number", 1)
            ev_status = c.get("evidence_status", "DIRECTLY_STATED")
            desc = c.get("simple_description") or "Not explicitly described in SOP."
            func = c.get("primary_function") or "Not specified in SOP — do NOT invent a function."
            mat = c.get("material_or_construction") or "Not specified in SOP."
            sub = c.get("parent_subsystem") or c.get("subsystem") or "Not specified in SOP."
            loc = c.get("location_or_use") or "Not specified in SOP."
            specs = c.get("technical_specifications") or "None listed."

            comp_lines = [
                f"--- COMPONENT [{c_num}]: {name} ---",
                f"ENTITY TYPE: {etype}",
                f"DOCUMENT: {fname} | REVISION: {rev} | SECTION: {sec} | PAGE: {page}",
                f"CITATION: {citation_str}",
                f"EVIDENCE STATUS: {ev_status} (Strict: Assert as facts only if DIRECTLY_STATED; note GENERAL_CONTEXT/INFERRED accordingly)",
                f"DESCRIPTION: {desc}",
                f"PRIMARY FUNCTION: {func}",
                f"MATERIAL / CONSTRUCTION: {mat}",
                f"SUBSYSTEM / LOCATION: {sub} ({loc})",
                f"TECHNICAL SPECIFICATIONS: {specs}"
            ]

            # Relationships for this component
            rels = c.get("relationships", [])
            if rels:
                comp_lines.append("VALIDATED RELATIONSHIPS:")
                for r in rels:
                    comp_lines.append(
                        f"  * {r.get('relationship_type')} -> {r.get('target_component')} "
                        f"[Citation: {r.get('source_reference')}]"
                    )
            else:
                comp_lines.append("VALIDATED RELATIONSHIPS: None documented in SOP.")

            blocks.append("\n".join(comp_lines))
            blocks.append("")

            citations.append({
                "passage_number": c_num,
                "component_name": name,
                "entity_type": etype,
                "filename": fname,
                "document_id": c.get("document_id"),
                "revision": rev,
                "section_title": sec,
                "page_number": page,
                "evidence_status": ev_status,
                "citation": citation_str
            })

    # 2. Supporting Technical Parameters / Materials
    if supporting_entities:
        blocks.append("### SUPPORTING TECHNICAL PARAMETERS & MATERIALS:")
        for se in supporting_entities:
            blocks.append(
                f"- [{se.get('entity_type')}]: {se.get('component_name')} | "
                f"Details: {se.get('technical_specifications') or se.get('material_or_construction')} | "
                f"Citation: {se.get('citation')}"
            )
        blocks.append("")

    # 3. Validated Relationships Cross-Reference
    if validated_relationships:
        blocks.append("### ALL VALIDATED MECHANICAL & OPERATIONAL RELATIONSHIPS:")
        for vr in validated_relationships:
            blocks.append(
                f"- {vr['source_component']} --[{vr['relationship_type']}]--> {vr['target_component']} "
                f"(Source: {vr['source_reference']})"
            )
        blocks.append("")

    # 4. Semantic FAISS chunk evidence
    if retrieved_chunks:
        chunk_context, chunk_citations = build_evidence_context(retrieved_chunks, max_context_chars=max_context_chars)
        blocks.append("### AUTHORITATIVE SOP EVIDENCE TEXT:")
        blocks.append(chunk_context)
        citations.extend(chunk_citations)

    return "\n".join(blocks), citations


# ============================================================================
# COMPONENT-AWARE RAG PROMPTS
# ============================================================================

COMPONENT_RAG_SYSTEM_PROMPT = """You are the official SOP Document Intelligence Assistant for Heavy Vehicles Factory (HVF), Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence.

Your objective is to provide beginner-friendly, rigorous, and completely grounded technical explanations of armoured vehicle components, assemblies, subsystems, functions, and relationships using ONLY the authoritative SOP evidence provided below.

Strict Grounding and Integrity Guidelines:
1. Strict Grounding: Rely EXCLUSIVELY on the factual statements in the provided EVIDENCE PASSAGES and STRUCTURED COMPONENT RECORDS. Never invent, extrapolate, or hallucinate component functions, materials, mechanical relationships, measurements, or locations.
2. Component Name Alone Does NOT Prove Function: If a component is named in the SOP but its operational function is not explicitly described, state clearly: "The SOP does not specify the operational function of [Component Name]." Do not speculate or invent a purpose.
3. Validated Relationships Only: Only describe connections, interfaces, or relationships that are explicitly documented in the VALIDATED RELATIONSHIPS section of the evidence. Co-occurrence of two parts in the same section or paragraph does NOT constitute a relationship. If no relationship is documented between components, explicitly state that the SOP does not specify how they connect.
4. Preserve Evidence Status:
   - For DIRECTLY_STATED items, present details as verified facts from the SOP body text.
   - For GENERAL_CONTEXT or INFERRED items, explicitly note that this information is inferred from section titles or visual diagrams, rather than directly stated text.
5. In-Text Citations: At the end of every substantive statement, include the exact bracketed citation: [Filename, Revision, Section, Page X].
6. Revision Distinctions: When evidence contains multiple revisions (e.g. baseline Rev 4.2 vs revised Rev 5.0), clearly distinguish between baseline and revised versions.
7. Beginner-Friendly Structure: Explain technical concepts simply and clearly for new technicians, while strictly retaining official technical names and codes."""

COMPONENT_RAG_INSTRUCTIONS = """Answer the user's component question using a clear, structured, beginner-friendly explanation strictly grounded in the authoritative component records and SOP passages above.

REQUIRED ANSWER STRUCTURE:
1. Overview: Provide a short, plain-language summary of the component, assembly, or subsystem.
2. Main Components / Assemblies: List the main physical components or assemblies documented in the SOP evidence. State their exact technical names and entity types. (Do not confuse tools, inspection procedures, or parameters with physical components).
   - For structural assemblies and hull questions: Explicitly distinguish between structural assemblies (e.g. Hull Tub Assembly, Sponson Box) and structural plates/components (e.g. Lower Hull Plate, Glacis Plate, Weld Joint Root Backing Strip). If the SOP lists plates without defining them as assemblies, call them structural components or plates, NOT assemblies. Never confuse manufacturing tools, equipment, or inspection stations (e.g., GMAW welding stations, PAUT scanners, induction heaters, turnover jigs) with structural vehicle components or assemblies.
3. Component Functions: For each component, explain what it does ONLY where the SOP evidence directly describes its function. If the SOP names a component but does not specify its function, explicitly state: "The SOP does not specify the operational function of [Component Name]." Never invent functions.
4. Validated Relationships: Describe mechanical and operational relationships ONLY when explicitly supported by the validated relationships in the evidence. Quote or cite the relationship. If no relationship between components is documented, state that no relationship is specified in the SOP. Never assume a connection from mere co-occurrence.
5. Relevant Procedures & Operational Context: Mention any relevant procedures, inspections, or operational handling context documented in the SOP.
   - For procedural steps (e.g. engine alignment): Present steps in chronological sequence directly supported by the SOP evidence (e.g., Section 1.0 engine bay metrology & hydromount damping, Section 2.0 powerpack hoisting & trunnion seating, Section 3.0 dual-laser shaft alignment & thermal compensation). State exact engineering values and tolerances (e.g. +0.10 mm cold offset vertical rise, running offset <= 0.035 mm, hydromount stiffness within +- 2.0%, DGQA Cpk >= 1.67, 5.5-tonne powerpack) without introducing unrelated procedures (such as sprocket or jig alignment) from other SOPs.
6. What the SOP Does Not Specify: Explicitly highlight any missing specifications, unstated functions, or undocumented construction details where important.

GROUNDING & CITATION RULES:
- Use beginner-friendly language while strictly preserving the authentic technical names used in the SOP.
- Never invent: component functions, materials, mechanical connections, dimensions/tolerances, or locations. A component name alone does NOT prove its function.
- Strictly preserve evidence status:
  * DIRECTLY_STATED: Assert as verified facts from the SOP.
  * GENERAL_CONTEXT or INFERRED: Note that this detail is derived from general context or visual diagrams, not directly stated body text.
- Include in-text citations: [Filename, Revision, Section, Page X] for every assertion.
- If asked about V1 vs V2, clearly distinguish between baseline and revised components and specifications."""


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
    max_tokens: int = 1536,
    index_dir: str = DEFAULT_INDEX_DIR,
    timeout: float = 180.0,
    embed_timeout: float = 15.0,
    max_context_chars: int = 16000
) -> Dict[str, Any]:
    """
    Synthesizes an evidence-grounded answer to a user question using retrieved chunks
    and structured component metadata with component-aware intelligence.
    
    Guarantees:
    - Strictly grounds generation in retrieved evidence and structured component records.
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
            - component_intent (Dict[str, Any])
            - is_component_query (bool)
            - model (str)
            - tokens_per_second (float)
            - eval_count (int)
            - status (str)
    """
    effective_question, antecedent_comp = resolve_conversational_query(question, conversation_history, index_dir=index_dir)
    initial_intent = detect_component_intent(effective_question, index_dir=index_dir)

    # 1. Fast conversational greeting response
    if initial_intent.get("category") == "GENERAL_CONVERSATION":
        greeting_text = (
            "Hello! I am the Intelligent SOP Document Assistant for Heavy Vehicles Factory (HVF) / "
            "Armoured Vehicles Nigam Limited (AVNL). I can help explain components, assemblies, "
            "engineering definitions, SOP procedures, technical tolerances, and revision impact analysis "
            "across V1 and V2 baseline documents. How can I assist you today?"
        )
        return {
            "answer": greeting_text,
            "citations": [],
            "is_insufficient": False,
            "is_cross_revision": False,
            "component_intent": initial_intent,
            "is_component_query": False,
            "model": model,
            "tokens_per_second": 0.0,
            "eval_count": len(greeting_text.split()),
            "status": "success"
        }

    # 2. Direct component glossary lookup for basic definitions
    if initial_intent.get("category") == "BASIC_DEFINITION" and retrieved_chunks is None:
        glossary_entry = lookup_component_glossary(effective_question)
        if glossary_entry:
            def_text, def_citations = format_basic_definition_response(glossary_entry, effective_question)
            return {
                "answer": def_text,
                "citations": def_citations,
                "is_insufficient": False,
                "is_cross_revision": False,
                "component_intent": initial_intent,
                "is_component_query": True,
                "model": model,
                "tokens_per_second": 0.0,
                "eval_count": len(def_text.split()),
                "status": "success"
            }

    if retrieved_chunks is None:
        evidence_data = retrieve_component_aware_evidence(
            query=effective_question,
            top_k_chunks=top_k,
            document_id=document_id,
            logical_sop_id=logical_sop_id,
            revision=revision,
            revision_mode=revision_mode,
            score_threshold=score_threshold,
            index_dir=index_dir,
            endpoint=endpoint,
            embed_timeout=embed_timeout
        )
        chunks = evidence_data.get("chunks", [])
        components = evidence_data.get("components", [])
        supporting_entities = evidence_data.get("supporting_entities", [])
        relationships = evidence_data.get("relationships", [])
        is_comp_query = evidence_data.get("is_component_query", False)
        intent = evidence_data.get("intent", {})
    else:
        chunks = retrieved_chunks
        intent = detect_component_intent(effective_question, index_dir=index_dir)
        if intent.get("is_component_intent", False):
            evidence_data = retrieve_component_aware_evidence(
                query=effective_question,
                top_k_chunks=top_k,
                document_id=document_id,
                logical_sop_id=logical_sop_id,
                revision=revision,
                revision_mode=revision_mode,
                score_threshold=score_threshold,
                index_dir=index_dir,
                endpoint=endpoint,
                embed_timeout=embed_timeout
            )
            components = evidence_data.get("components", [])
            supporting_entities = evidence_data.get("supporting_entities", [])
            relationships = evidence_data.get("relationships", [])
            is_comp_query = bool(components or relationships)
        else:
            components = []
            supporting_entities = []
            relationships = []
            is_comp_query = False

    if not chunks and not components:
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
            "component_intent": intent,
            "is_component_query": is_comp_query,
            "model": model,
            "tokens_per_second": 0.0,
            "eval_count": 0,
            "status": "insufficient_evidence"
        }

    if is_comp_query:
        evidence_context, citations = build_component_evidence_context(
            retrieved_components=components,
            retrieved_chunks=chunks,
            validated_relationships=relationships,
            supporting_entities=supporting_entities,
            max_context_chars=max_context_chars
        )
        selected_system_prompt = COMPONENT_RAG_SYSTEM_PROMPT
        selected_instructions = COMPONENT_RAG_INSTRUCTIONS
    else:
        evidence_context, citations = build_evidence_context(chunks, max_context_chars=max_context_chars)
        selected_system_prompt = RAG_SYSTEM_PROMPT
        selected_instructions = (
            "Answer the user's specific question using relevant evidence from the passages above.\n"
            "- Focus directly on evidence relevant to the question.\n"
            "- Present all relevant parameters, tolerances, and acceptance criteria concisely in structured bullet points or a table.\n"
            "- Avoid redundant or overly repetitive explanations.\n"
        )

    has_v1 = any(is_v1_chunk(c) for c in chunks) or any(is_v1_component(c) for c in components)
    has_v2 = any(is_v2_chunk(c) for c in chunks) or any(is_v2_component(c) for c in components)
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
    prompt_parts.append(selected_instructions)

    if is_cross_revision:
        prompt_parts.append(
            "\n- CRITICAL: The retrieved evidence spans multiple revisions (both baseline V1 and revised V2). "
            "Clearly identify the exact revision for each assertion and explicitly distinguish baseline vs revised values.\n"
        )
    else:
        prompt_parts.append("\n- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n")

    prompt_parts.append(
        "- Insert the exact bracketed citation for every parameter or assertion.\n"
        "- If certain benchmarks or component functions are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- Conclude concisely and end with complete terminal punctuation."
    )

    full_prompt = "\n".join(prompt_parts)

    # Generate response via local model
    gen_result = generate_response(
        prompt=full_prompt,
        model=model,
        system_prompt=selected_system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint,
        timeout=timeout
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
        "evidence_context": evidence_context,
        "is_insufficient": is_insufficient,
        "is_cross_revision": is_cross_revision,
        "component_intent": intent,
        "is_component_query": is_comp_query,
        "retrieved_components_count": len(components),
        "retrieved_chunks_count": len(chunks),
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
    revision_mode: Optional[str] = None,
    score_threshold: Optional[float] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    index_dir: str = DEFAULT_INDEX_DIR,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_LLM_MODEL
) -> Dict[str, Any]:
    """
    End-to-end RAG pipeline wrapper (synchronous):
    1. Retrieves relevant evidence passages from FAISS and structured component metadata.
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
    effective_question, antecedent_comp = resolve_conversational_query(question, conversation_history, index_dir=index_dir)
    initial_intent = detect_component_intent(effective_question, index_dir=index_dir)

    # 1. Fast handling of greetings or basic definitions via generate_rag_answer
    if initial_intent.get("category") in ("GENERAL_CONVERSATION", "BASIC_DEFINITION"):
        rag_output = generate_rag_answer(
            question=effective_question,
            top_k=top_k,
            document_id=document_id,
            logical_sop_id=logical_sop_id,
            revision=revision,
            revision_mode=revision_mode,
            conversation_history=conversation_history,
            endpoint=endpoint,
            model=model,
            index_dir=index_dir
        )
        rag_output["retrieval_duration_ms"] = round((time.time() - retrieval_t0) * 1000.0, 2)
        rag_output["antecedent_component"] = antecedent_comp
        return rag_output

    evidence_data = retrieve_component_aware_evidence(
        query=effective_question,
        top_k_chunks=top_k,
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
        retrieved_chunks=evidence_data.get("chunks", []),
        top_k=top_k,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        revision_mode=revision_mode,
        conversation_history=conversation_history,
        endpoint=endpoint,
        model=model,
        index_dir=index_dir
    )

    rag_output["retrieval_duration_ms"] = round(retrieval_duration_ms, 2)
    rag_output["retrieved_chunks_count"] = len(evidence_data.get("chunks", []))
    rag_output["retrieved_components_count"] = len(evidence_data.get("components", []))
    rag_output["component_intent"] = evidence_data.get("intent", {})
    rag_output["antecedent_component"] = antecedent_comp
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
    max_tokens: int = 1536,
    timeout: float = 180.0,
    embed_timeout: float = 15.0,
    max_context_chars: int = 16000
) -> Tuple[Generator[str, None, None], List[Dict[str, Any]], Dict[str, Any]]:
    """
    End-to-end progressive RAG streaming pipeline:
    1. Retrieves relevant evidence passages from FAISS and structured component metadata with V2-first intelligence.
    2. Builds structured evidence context and citations.
    3. Yields progressive token stream from LLM while returning citations immediately.
    
    Returns:
        Tuple[Generator[str, None, None], List[Dict[str, Any]], Dict[str, Any]]:
            - token_generator: Yields response text token by token.
            - citations: Structured citations list for UI rendering.
            - info: Metadata dict (retrieval_duration_ms, retrieved_chunks_count, retrieved_components_count, component_intent, is_cross_revision).
    """
    retrieval_t0 = time.time()
    effective_question, antecedent_comp = resolve_conversational_query(question, conversation_history, index_dir=index_dir)
    initial_intent = detect_component_intent(effective_question, index_dir=index_dir)

    # 1. Immediate handling of conversational greetings (no FAISS retrieval or model latency)
    if initial_intent.get("category") == "GENERAL_CONVERSATION":
        greeting_msg = (
            "Hello! I am the Intelligent SOP Document Assistant for Heavy Vehicles Factory (HVF) / "
            "Armoured Vehicles Nigam Limited (AVNL). I can help explain components, assemblies, "
            "engineering definitions, SOP procedures, technical tolerances, and revision impact analysis "
            "across V1 and V2 baseline documents. How can I assist you today?"
        )
        def greeting_gen():
            words = greeting_msg.split(" ")
            for idx, w in enumerate(words):
                yield w + (" " if idx < len(words) - 1 else "")
        info = {
            "retrieval_duration_ms": 0.0,
            "retrieved_chunks_count": 0,
            "retrieved_components_count": 0,
            "component_intent": initial_intent,
            "is_component_query": False,
            "is_insufficient": False,
            "is_cross_revision": False,
            "is_greeting": True
        }
        return greeting_gen(), [], info

    # 2. Direct component glossary lookup for basic definitions
    if initial_intent.get("category") == "BASIC_DEFINITION":
        glossary_entry = lookup_component_glossary(effective_question)
        if glossary_entry:
            def_text, def_citations = format_basic_definition_response(glossary_entry, effective_question)
            def glossary_gen():
                tokens = re.split(r'(\s+)', def_text)
                for t in tokens:
                    yield t
            info = {
                "retrieval_duration_ms": round((time.time() - retrieval_t0) * 1000.0, 2),
                "retrieved_chunks_count": len(def_citations),
                "retrieved_components_count": 1,
                "component_intent": initial_intent,
                "is_component_query": True,
                "is_insufficient": False,
                "is_cross_revision": False,
                "glossary_match": glossary_entry.get("canonical_name")
            }
            return glossary_gen(), def_citations, info

    evidence_data = retrieve_component_aware_evidence(
        query=effective_question,
        top_k_chunks=top_k,
        document_id=document_id,
        logical_sop_id=logical_sop_id,
        revision=revision,
        revision_mode=revision_mode,
        score_threshold=score_threshold,
        index_dir=index_dir,
        endpoint=endpoint
    )
    retrieval_duration_ms = (time.time() - retrieval_t0) * 1000.0

    chunks = evidence_data.get("chunks", [])
    components = evidence_data.get("components", [])
    supporting_entities = evidence_data.get("supporting_entities", [])
    relationships = evidence_data.get("relationships", [])
    is_comp_query = evidence_data.get("is_component_query", False)
    intent = evidence_data.get("intent", {})

    if not chunks and not components:
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
            "retrieved_components_count": 0,
            "component_intent": intent,
            "is_component_query": is_comp_query,
            "is_insufficient": True,
            "is_cross_revision": False
        }
        return empty_gen(), [], info

    if is_comp_query:
        evidence_context, citations = build_component_evidence_context(
            retrieved_components=components,
            retrieved_chunks=chunks,
            validated_relationships=relationships,
            supporting_entities=supporting_entities,
            max_context_chars=max_context_chars
        )
        selected_system_prompt = COMPONENT_RAG_SYSTEM_PROMPT
        selected_instructions = COMPONENT_RAG_INSTRUCTIONS
    else:
        evidence_context, citations = build_evidence_context(chunks, max_context_chars=max_context_chars)
        selected_system_prompt = RAG_SYSTEM_PROMPT
        selected_instructions = (
            "Answer the user's specific question using relevant evidence from the passages above.\n"
            "- Focus directly on evidence relevant to the question.\n"
            "- Present all relevant parameters, tolerances, and acceptance criteria concisely in structured bullet points or a table.\n"
            "- Avoid redundant or overly repetitive explanations.\n"
        )

    has_v1 = any(is_v1_chunk(c) for c in chunks) or any(is_v1_component(c) for c in components)
    has_v2 = any(is_v2_chunk(c) for c in chunks) or any(is_v2_component(c) for c in components)
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
    prompt_parts.append(selected_instructions)

    if is_cross_revision:
        prompt_parts.append(
            "\n- CRITICAL: The retrieved evidence spans multiple revisions (both baseline V1 and revised V2). "
            "Clearly identify the exact revision for each assertion and explicitly distinguish baseline vs revised values.\n"
        )
    else:
        prompt_parts.append("- Distinguish between baseline (Rev 4.2) and revised (Rev 5.0) requirements if present.\n")

    prompt_parts.append(
        "- Insert the exact bracketed citation for every parameter.\n"
        "- If certain benchmarks or component functions are not covered in the retrieved SOP evidence, explicitly note what is missing.\n"
        "- Conclude concisely and end with complete terminal punctuation."
    )

    full_prompt = "\n".join(prompt_parts)

    token_gen = stream_response(
        prompt=full_prompt,
        model=model,
        system_prompt=selected_system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        endpoint=endpoint,
        timeout=timeout
    )

    info = {
        "retrieval_duration_ms": round(retrieval_duration_ms, 2),
        "retrieved_chunks_count": len(chunks),
        "retrieved_components_count": len(components),
        "component_intent": intent,
        "is_component_query": is_comp_query,
        "is_insufficient": False,
        "is_cross_revision": is_cross_revision,
        "antecedent_component": antecedent_comp,
        "evidence_context": evidence_context
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


def get_comprehensive_system_health(index_dir: str = DEFAULT_INDEX_DIR) -> Dict[str, Any]:
    """
    Performs an all-in-one system reliability diagnostic audit across all 5 operational tiers:
    1. Local Ollama AI Daemon Connectivity and Model Readiness
    2. Dense Vector Embeddings (768-dim) and Generation LLM status
    3. FAISS Vector Database and chunk synchronization
    4. Structured Component Metadata records and classifications
    5. Persistent SQLite database health and table integrity
    
    Returns:
        Dict[str, Any]: Comprehensive telemetry dictionary with overall operational state.
    """
    # 1. Ollama & Models Connectivity
    ollama_online = check_ollama_connection()
    models_info = verify_required_models() if ollama_online else {
        "ollama_available": False,
        "llm_present": False,
        "embed_present": False,
        "all_ready": False,
        "installed_models": []
    }

    # 2. FAISS Vector Index Health
    faiss_health = verify_faiss_index_health(index_dir)

    # 3. Component Metadata Health
    comp_meta_path = os.path.join(index_dir, "components_metadata.json")
    comp_file_exists = os.path.isfile(comp_meta_path)
    components = load_components_metadata(index_dir)
    comp_records_count = len(components)
    
    entity_type_counts: Dict[str, int] = {}
    uncertain_count = 0
    for c in components:
        etype = c.get("entity_type", "OTHER_REFERENCE")
        entity_type_counts[etype] = entity_type_counts.get(etype, 0) + 1
        if c.get("is_uncertain", False):
            uncertain_count += 1

    comp_is_healthy = comp_file_exists and (comp_records_count > 0)

    # 4. SQLite Database Health
    db_health = {"is_healthy": False, "connected": False, "total_conversations": 0, "total_messages": 0, "issues": []}
    try:
        import database as db_mod
        db_health = db_mod.get_database_health()
    except Exception as e:
        db_health["issues"] = [f"Database health check error: {e}"]

    # 5. Document breakdown
    total_docs = faiss_health.get("total_documents", 0)
    baseline_docs_count = len(faiss_health.get("baseline_documents", []))
    uploaded_docs_count = len(faiss_health.get("uploaded_documents", []))

    # 6. Overall State Determination
    if (ollama_online and models_info.get("all_ready", False) and 
        faiss_health.get("is_healthy", False) and db_health.get("is_healthy", False)):
        overall_status = "HEALTHY"
        status_message = "All system services, vector indices, and database stores are fully operational."
    elif not faiss_health.get("is_healthy", False) or not db_health.get("is_healthy", False):
        overall_status = "CRITICAL"
        status_message = "Critical data store failure (FAISS index or SQLite database issue detected)."
    else:
        overall_status = "DEGRADED"
        status_message = "System operational with limited AI inference capabilities (Ollama daemon or model missing)."

    return {
        "timestamp": time.time(),
        "overall_status": overall_status,
        "status_message": status_message,
        "ollama": {
            "online": ollama_online,
            "endpoint": DEFAULT_OLLAMA_ENDPOINT,
            "llm_model": DEFAULT_LLM_MODEL,
            "llm_ready": models_info.get("llm_present", False),
            "embed_model": DEFAULT_EMBED_MODEL,
            "embed_ready": models_info.get("embed_present", False),
            "all_models_ready": models_info.get("all_ready", False),
            "installed_models": models_info.get("installed_models", [])
        },
        "faiss": faiss_health,
        "components": {
            "is_healthy": comp_is_healthy,
            "file_exists": comp_file_exists,
            "file_path": comp_meta_path,
            "total_records": comp_records_count,
            "entity_type_counts": entity_type_counts,
            "physical_components_count": entity_type_counts.get("PHYSICAL_COMPONENT", 0),
            "assemblies_count": entity_type_counts.get("ASSEMBLY", 0),
            "subsystems_count": entity_type_counts.get("SUBSYSTEM", 0),
            "uncertain_records_count": uncertain_count
        },
        "database": db_health,
        "documents": {
            "total_documents": total_docs,
            "baseline_documents_count": baseline_docs_count,
            "uploaded_documents_count": uploaded_docs_count,
            "baseline_documents": faiss_health.get("baseline_documents", []),
            "uploaded_documents": faiss_health.get("uploaded_documents", [])
        }
    }


if __name__ == "__main__":
    print("Executing rag_engine build verification...")
    res = rebuild_faiss_index()
    print("Rebuild status:", res)
    sample_retrieval = retrieve_relevant_chunks("What is the pre-heating temperature for hull welding?")
    print(f"Sample retrieval: {len(sample_retrieval)} chunks retrieved.")
    if sample_retrieval:
        print("Top citation:", sample_retrieval[0]["citation"])
        print("Top score:", sample_retrieval[0]["score"])
