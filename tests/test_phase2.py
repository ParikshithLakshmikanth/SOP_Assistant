#!/usr/bin/env python3
"""
Phase 2 Verification Test Suite: Local Ollama AI Integration
============================================================
Tests rag_engine.py against all requirements:
1. Real Ollama Connection check on local endpoint.
2. Verification of registered models (gemma-2b:latest and nomic-embed-text:latest).
3. Text generation using Gemma with temperature and token limits.
4. Token-by-token streaming response verification.
5. Single-text embedding generation with dimension validation (768).
6. Batch embedding generation with dimension validation (N, 768).
7. Vector normalization check (L2 norm == 1.000000).
8. Input validation and error handling (empty strings, whitespace-only, empty lists).
9. Graceful error handling for non-existent models and unreachable endpoints.
10. Offline loopback verification (exclusive local endpoint usage).
"""

import sys
import os
import math
import time
import numpy as np
import rag_engine as re

def run_tests():
    print("=" * 75)
    print("STARTING PHASE 2 VERIFICATION TEST SUITE (LOCAL OLLAMA INTEGRATION)")
    print("=" * 75)

    results = {
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "details": []
    }

    def record_test(name: str, passed: bool, message: str = ""):
        results["total_tests"] += 1
        if passed:
            results["passed_tests"] += 1
            print(f"[PASS] {name}: {message}")
            results["details"].append({"test": name, "status": "PASS", "message": message})
        else:
            results["failed_tests"] += 1
            print(f"[FAIL] {name}: {message}")
            results["details"].append({"test": name, "status": "FAIL", "message": message})

    # ------------------------------------------------------------------------
    # TEST 1: Ollama Connection Check (Real Integration)
    # ------------------------------------------------------------------------
    is_connected = re.check_ollama_connection()
    record_test(
        "1. Ollama Daemon Reachability",
        is_connected,
        f"Ollama server is active and responding on {re.DEFAULT_OLLAMA_ENDPOINT}"
        if is_connected else "Failed to reach Ollama endpoint."
    )

    # ------------------------------------------------------------------------
    # TEST 2: Model Registration Verification (Real Integration)
    # ------------------------------------------------------------------------
    model_status = re.verify_required_models()
    both_present = model_status["all_ready"]
    models_found = model_status.get("available_models", [])
    record_test(
        "2. Required Models Registration",
        both_present,
        f"Verified models present: {models_found}"
        if both_present else f"Missing models: {model_status.get('error')}"
    )

    # ------------------------------------------------------------------------
    # TEST 3: Text Generation using Gemma (Real Integration)
    # ------------------------------------------------------------------------
    gen_success = False
    gen_text = ""
    gen_tps = 0.0
    res = {}
    try:
        t0 = time.time()
        res = re.generate_response(
            prompt="Define an Armoured Hull in one sentence.",
            model=re.DEFAULT_LLM_MODEL,
            temperature=0.1,
            max_tokens=256
        )
        gen_text = res.get("response", "")
        gen_tps = res.get("tokens_per_second", 0.0)
        gen_success = len(gen_text) > 10 and res.get("status") == "success"
    except Exception as e:
        print(f"Generation error: {e}")

    record_test(
        "3. Gemma Text Generation",
        gen_success,
        f"Output: '{gen_text[:60]}...' | Tokens/sec: {gen_tps} | Time: {res.get('total_duration_ms')}ms"
        if gen_success else "Text generation failed."
    )

    # ------------------------------------------------------------------------
    # TEST 4: Gemma Token-by-Token Streaming (Real Integration)
    # ------------------------------------------------------------------------
    streaming_success = False
    chunks_received = []
    try:
        stream = re.stream_response(
            prompt="Count 1 to 5.",
            model=re.DEFAULT_LLM_MODEL,
            temperature=0.0,
            max_tokens=32
        )
        for token in stream:
            chunks_received.append(token)
        streaming_success = len(chunks_received) >= 5
    except Exception as e:
        print(f"Streaming error: {e}")

    record_test(
        "4. Gemma Progressive Streaming",
        streaming_success,
        f"Successfully received {len(chunks_received)} progressive chunks: '{''.join(chunks_received).strip()[:40]}...'"
        if streaming_success else f"Streaming received only {len(chunks_received)} tokens."
    )

    # ------------------------------------------------------------------------
    # TEST 5: Nomic Single-Text Embedding (Real Integration)
    # ------------------------------------------------------------------------
    embed_success = False
    single_dim = 0
    is_finite = False
    try:
        t0 = time.time()
        vec = re.generate_embedding("Rolled Homogeneous Armour plate welding specification.")
        single_dim = vec.shape[0] if vec.ndim == 1 else 0
        is_finite = bool(np.all(np.isfinite(vec)))
        embed_success = (single_dim == 768 and is_finite)
    except Exception as e:
        print(f"Single embed error: {e}")

    record_test(
        "5. Nomic Single-Text Embedding",
        embed_success,
        f"Vector shape: ({single_dim},) | Finite values: {is_finite} | Dim == 768: {single_dim == 768}"
    )

    # ------------------------------------------------------------------------
    # TEST 6: Nomic Batch Embedding (Real Integration)
    # ------------------------------------------------------------------------
    batch_success = False
    batch_shape = (0, 0)
    batch_samples = [
        "Hydraulic torque multiplier calibration standard.",
        "Laser co-planarity alignment of turret base ring.",
        "Engine trunnion shim pack tolerance inspection.",
        "Torsion bar shot-peening and ultrasonic flaw detection.",
        "Main gun barrel bore video-scope rifling inspection."
    ]
    try:
        t0 = time.time()
        batch_vecs = re.generate_embeddings(batch_samples, batch_size=4)
        batch_shape = batch_vecs.shape
        batch_finite = bool(np.all(np.isfinite(batch_vecs)))
        batch_success = (batch_shape == (len(batch_samples), 768) and batch_finite)
    except Exception as e:
        print(f"Batch embed error: {e}")

    record_test(
        "6. Nomic Batch Embedding",
        batch_success,
        f"Batch shape: {batch_shape} | All finite: {batch_finite} | Items processed: {len(batch_samples)}"
    )

    # ------------------------------------------------------------------------
    # TEST 7: Vector Normalization & Cosine Similarity Adherence
    # ------------------------------------------------------------------------
    norm_success = False
    try:
        # Check that L2 norm of generated normalized vectors is strictly 1.0 (within float32 precision)
        norms = np.linalg.norm(batch_vecs, axis=1)
        is_unit_norm = np.allclose(norms, 1.0, atol=1e-5)
        # Check inner product of identical vector equals 1.0
        dot_self = float(np.dot(batch_vecs[0], batch_vecs[0]))
        norm_success = is_unit_norm and math.isclose(dot_self, 1.0, rel_tol=1e-5)
    except Exception as e:
        print(f"Normalization error: {e}")

    record_test(
        "7. Vector Normalization Check",
        norm_success,
        f"All vectors L2-normalized: norms={np.round(norms[:3], 4)} | Self-dot-product: {dot_self:.6f}"
    )

    # ------------------------------------------------------------------------
    # TEST 8: Dimension Validation & Failure Detection
    # ------------------------------------------------------------------------
    validation_success = False
    try:
        # Valid 768
        v_good = np.ones((768,), dtype=np.float32)
        re.validate_embedding_dimensions(v_good, 768)

        # Invalid 512
        v_bad = np.ones((512,), dtype=np.float32)
        try:
            re.validate_embedding_dimensions(v_bad, 768)
            bad_rejected = False
        except ValueError:
            bad_rejected = True

        # Non-finite NaN
        v_nan = np.ones((768,), dtype=np.float32)
        v_nan[10] = np.nan
        try:
            re.validate_embedding_dimensions(v_nan, 768)
            nan_rejected = False
        except ValueError:
            nan_rejected = True

        validation_success = bad_rejected and nan_rejected
    except Exception as e:
        print(f"Dimension validation error: {e}")

    record_test(
        "8. Dimension & Numerical Integrity Validation",
        validation_success,
        "Correctly passed 768-dim vector; rejected 512-dim vector and rejected NaN vector."
    )

    # ------------------------------------------------------------------------
    # TEST 9: Empty & Invalid Input Handling
    # ------------------------------------------------------------------------
    input_handling_success = False
    try:
        # Empty string embedding
        empty_str_rejected = False
        try:
            re.generate_embedding("")
        except ValueError:
            empty_str_rejected = True

        # Whitespace-only string
        ws_rejected = False
        try:
            re.generate_embedding("   \n\t  ")
        except ValueError:
            ws_rejected = True

        # Empty prompt generation
        empty_prompt_rejected = False
        try:
            re.generate_response("   ")
        except ValueError:
            empty_prompt_rejected = True

        # Empty list embeddings should return empty array
        empty_list_handled = (re.generate_embeddings([]).shape == (0, 768))

        input_handling_success = (empty_str_rejected and ws_rejected and empty_prompt_rejected and empty_list_handled)
    except Exception as e:
        print(f"Input handling error: {e}")

    record_test(
        "9. Invalid Input Handling",
        input_handling_success,
        "Rejected empty string, whitespace string, empty prompt, and handled empty batch gracefully."
    )

    # ------------------------------------------------------------------------
    # TEST 10: Model-Unavailable & Bad Endpoint Error Handling
    # ------------------------------------------------------------------------
    error_handling_success = False
    try:
        # Non-existent model name should raise RuntimeError or ConnectionError with clear message
        fake_model_rejected = False
        try:
            re.generate_response("Test prompt", model="non_existent_fake_model_9999")
        except RuntimeError as e:
            fake_model_rejected = True
            err_msg = str(e)

        # Unreachable endpoint should return False for check and raise ConnectionError for generation
        unreachable_endpoint = "http://127.0.0.1:59999"
        conn_check_false = not re.check_ollama_connection(endpoint=unreachable_endpoint, timeout=1.0)
        unreachable_rejected = False
        try:
            re.generate_response("Test prompt", endpoint=unreachable_endpoint)
        except ConnectionError:
            unreachable_rejected = True

        error_handling_success = (fake_model_rejected and conn_check_false and unreachable_rejected)
    except Exception as e:
        print(f"Error handling test error: {e}")

    record_test(
        "10. Model-Unavailable & Bad Endpoint Handling",
        error_handling_success,
        f"Correctly caught fake model error ('{err_msg[:40]}...') and caught unreachable endpoint."
    )

    # ------------------------------------------------------------------------
    # TEST 11: Offline Loopback Verification
    # ------------------------------------------------------------------------
    offline_verified = (
        re.DEFAULT_OLLAMA_ENDPOINT.startswith("http://127.0.0.1")
        and not any(k in os.environ for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "COHERE_API_KEY"])
        and is_connected
    )
    record_test(
        "11. Offline Local Execution Verification",
        offline_verified,
        f"Endpoint is strictly local loopback ({re.DEFAULT_OLLAMA_ENDPOINT}). Zero external cloud LLM dependencies."
    )

    # ------------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------------
    print("=" * 75)
    print(f"PHASE 2 TEST SUMMARY: {results['passed_tests']}/{results['total_tests']} PASSED "
          f"({results['failed_tests']} FAILED)")
    print("=" * 75)

    return results

if __name__ == "__main__":
    res = run_tests()
    if res["failed_tests"] > 0:
        sys.exit(1)
    sys.exit(0)
