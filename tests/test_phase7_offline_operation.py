import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import socket
import unittest
import rag_engine as re
import database as db

class OfflineNetworkBlocker:
    """
    Simulates total disconnection of external internet access.
    Permits ONLY loopback traffic (127.0.0.1 / localhost) for local Ollama daemon.
    Any attempt to connect to external IPs or public DNS raises OSError('Network is unreachable').
    """
    def __init__(self):
        self._orig_connect = socket.socket.connect

    def __enter__(self):
        def guarded_connect(sock_self, address):
            host = address[0] if isinstance(address, tuple) else address
            # Allow loopback ONLY
            if str(host) in ("127.0.0.1", "localhost", "::1"):
                return self._orig_connect(sock_self, address)
            raise OSError(f"OFFLINE AIRGAP ENFORCED: Outbound connection blocked to {host}:{address[1] if isinstance(address, tuple) and len(address)>1 else ''}")

        socket.socket.connect = guarded_connect
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        socket.socket.connect = self._orig_connect

def test_offline_operation():
    print("==================================================================")
    print("STEP 8: STRICT OFFLINE AIR-GAP VERIFICATION TEST")
    print("==================================================================")

    with OfflineNetworkBlocker():
        # 1. Verify outbound internet attempt fails under blocker
        print("Testing internet block enforcement...")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("8.8.8.8", 53))
            assert False, "Outbound internet call should have been blocked!"
        except OSError as e:
            print(f"Verified network air-gap: {e}")

        # 2. Local Ollama generation & embedding under complete air-gap
        print("\nVerifying local Ollama connectivity under air-gap...")
        conn_ok = re.check_ollama_connection()
        print(f"Ollama local loopback connected: {conn_ok}")
        assert conn_ok, "Local Ollama daemon must be accessible via 127.0.0.1"

        print("Testing local embedding generation under air-gap...")
        vec = re.generate_embedding("Offline air-gap verification text")
        print(f"Generated local embedding shape: {vec.shape}, dim: {vec.shape[0]}")
        assert vec.shape[0] == 768, "Local embedding must be 768-dim"

        # 3. FAISS Retrieval under air-gap
        print("\nTesting FAISS vector retrieval under air-gap...")
        chunks = re.retrieve_relevant_chunks("turret mount ceramic hybrid bearing", top_k=3)
        print(f"Retrieved {len(chunks)} chunks under air-gap.")
        assert len(chunks) > 0, "FAISS vector search must work offline"
        print(f"Top chunk: {chunks[0]['filename']} (score={chunks[0]['score']:.4f})")

        # 4. Component Explorer filtering under air-gap
        print("\nTesting Component Explorer filtering under air-gap...")
        comps = re.load_components_metadata()
        filtered = re.filter_components(comps, entity_type_filter="PHYSICAL_COMPONENT", revision_filter="V2 (Active / Revised)")
        print(f"Filtered {len(filtered)} physical components under air-gap.")
        assert len(filtered) > 0, "Component filtering must work offline"

        # 5. Database health under air-gap
        print("\nTesting SQLite database health under air-gap...")
        db_health = db.get_database_health()
        print(f"Database healthy: {db_health['is_healthy']}")
        assert db_health["is_healthy"], "Database must work offline"

        # 6. Comprehensive system health check under air-gap
        print("\nTesting system health telemetry under air-gap...")
        sys_health = re.get_comprehensive_system_health()
        print(f"System Health Status under air-gap: {sys_health['overall_status']}")
        assert sys_health["overall_status"] == "HEALTHY", "System must report HEALTHY under air-gap"

    print("\nSUCCESS: 100% Offline Air-Gap Operation Confirmed (Zero external calls required)!")

if __name__ == "__main__":
    test_offline_operation()

