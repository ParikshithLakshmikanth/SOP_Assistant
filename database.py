#!/usr/bin/env python3
"""
SOP Document Intelligence & Revision Impact Analysis Assistant
==============================================================
Module: database.py
Architecture Role: Module 5 of 5 (SQLite Conversation Persistence & History).

Responsibilities:
- Persistent SQLite storage for multi-session chatbot consultations.
- Strict foreign-key relationship enforcement (`PRAGMA foreign_keys = ON;`).
- Atomic transactions with parameterized queries to prevent SQL injection.
- Preserves full conversation context: roles, content, structured citations, and cancellation status.
- Strict isolation: Conversation dialogue is NEVER indexed into the FAISS vector database
  and is NEVER treated as authoritative engineering SOP evidence.
- Fully offline execution without external database servers or cloud dependencies.
"""

import os
import json
import uuid
import sqlite3
from contextlib import contextmanager
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("SOP_Assistant.Database")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_DB_PATH = os.path.join(DEFAULT_DATA_DIR, "sop_assistant.db")


# ============================================================================
# CONNECTION & INITIALIZATION
# ============================================================================

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Creates and configures an SQLite database connection.
    Enforces foreign-key integrity and returns sqlite3.Row for dictionary-like access.
    """
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db(db_path: str = DEFAULT_DB_PATH):
    """
    Context manager that yields an open SQLite connection and guarantees
    its closure upon exiting the block, preventing Windows file-lock leaks.
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_database(db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Initializes the SQLite schema with conversations and messages tables,
    indexes, and cascading foreign-key rules.
    
    Args:
        db_path: Path to the SQLite database file.
    """
    with get_db(db_path) as conn:
        cursor = conn.cursor()

        # 1. Conversations Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        # 2. Messages Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                citations TEXT NOT NULL DEFAULT '[]',
                is_cancelled INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
            );
        """)

        # 3. Impact Reviews Table (Phase 8 Human Review Workflow)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS impact_reviews (
                review_id TEXT PRIMARY KEY,
                impact_id TEXT NOT NULL UNIQUE,
                source_change_id TEXT NOT NULL,
                source_sop_id TEXT NOT NULL,
                affected_sop_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('PENDING', 'ACCEPTED', 'REJECTED', 'INVESTIGATE')),
                reviewer_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        # 4. Optimized Indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_conv_seq
            ON messages(conversation_id, sequence_number);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_impact_reviews_lookup
            ON impact_reviews(source_change_id, affected_sop_id);
        """)

        conn.commit()
        logger.info(f"Database schema initialized successfully at {db_path}")


# ============================================================================
# CONVERSATION MANAGEMENT
# ============================================================================

def create_conversation(
    title: str = "New Consultation",
    conv_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Creates a new persistent conversation record.
    
    Args:
        title: Descriptive consultation title.
        conv_id: Optional custom conversation ID; generates UUID4 if None.
        db_path: Path to database.
        
    Returns:
        Dict[str, Any]: Newly created conversation metadata.
    """
    init_database(db_path)

    cid = str(conv_id).strip() if conv_id else str(uuid.uuid4())[:8]
    clean_title = title.strip() if title and title.strip() else "New Consultation"
    now_iso = datetime.now().isoformat()

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO conversations (conversation_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?);
            """,
            (cid, clean_title, now_iso, now_iso)
        )
        conn.commit()

    logger.info(f"Created conversation '{clean_title}' [{cid}]")
    return {
        "conversation_id": cid,
        "title": clean_title,
        "created_at": now_iso,
        "updated_at": now_iso
    }


def get_conversation(
    conversation_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Retrieves metadata for a single conversation by ID.
    
    Args:
        conversation_id: Unique conversation identifier.
        db_path: Path to database.
        
    Returns:
        Optional[Dict[str, Any]]: Conversation metadata or None if not found.
    """
    if not conversation_id or not str(conversation_id).strip():
        return None

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT conversation_id, title, created_at, updated_at
            FROM conversations
            WHERE conversation_id = ?;
            """,
            (str(conversation_id).strip(),)
        )
        row = cursor.fetchone()

    if row:
        return dict(row)
    return None


def list_conversations(
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Lists recent conversations ordered by last update timestamp descending.
    Includes active message counts for UI display.
    
    Args:
        limit: Maximum number of conversations to retrieve.
        db_path: Path to database.
        
    Returns:
        List[Dict[str, Any]]: List of conversation records with message_count.
    """
    init_database(db_path)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
                   COUNT(m.message_id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON c.conversation_id = m.conversation_id
            GROUP BY c.conversation_id
            ORDER BY c.updated_at DESC
            LIMIT ?;
            """,
            (max(1, int(limit)),)
        )
        rows = cursor.fetchall()

    return [dict(r) for r in rows]


def update_conversation_title(
    conversation_id: str,
    new_title: str,
    db_path: str = DEFAULT_DB_PATH
) -> bool:
    """
    Updates the title and update-timestamp of an existing conversation.
    
    Args:
        conversation_id: Target conversation ID.
        new_title: Updated title string.
        db_path: Path to database.
        
    Returns:
        bool: True if updated, False if conversation not found or title invalid.
    """
    if not conversation_id or not new_title or not new_title.strip():
        return False

    now_iso = datetime.now().isoformat()
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE conversations
            SET title = ?, updated_at = ?
            WHERE conversation_id = ?;
            """,
            (new_title.strip(), now_iso, str(conversation_id).strip())
        )
        conn.commit()
        updated = cursor.rowcount > 0

    return updated


def delete_conversation(
    conversation_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> bool:
    """
    Deletes a conversation and cascades deletion to all its messages.
    
    Args:
        conversation_id: Target conversation ID to purge.
        db_path: Path to database.
        
    Returns:
        bool: True if deleted, False if conversation did not exist.
    """
    if not conversation_id or not str(conversation_id).strip():
        return False

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM conversations WHERE conversation_id = ?;",
            (str(conversation_id).strip(),)
        )
        conn.commit()
        deleted = cursor.rowcount > 0

    if deleted:
        logger.info(f"Deleted conversation [{conversation_id}] and cascaded messages.")
    return deleted


# ============================================================================
# MESSAGE MANAGEMENT
# ============================================================================

def save_message(
    conversation_id: str,
    role: str,
    content: str,
    citations: Optional[List[Dict[str, Any]]] = None,
    is_cancelled: bool = False,
    msg_id: Optional[str] = None,
    timestamp: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Persists a single chat message (user, assistant, or system) in sequence.
    Updates the parent conversation's updated_at timestamp.
    
    Args:
        conversation_id: Parent conversation ID.
        role: Message role ('user', 'assistant', 'system').
        content: Verbatim text content.
        citations: Optional list of retrieved passage citation dicts.
        is_cancelled: Flag indicating user pressed Stop during generation.
        msg_id: Optional custom message ID; generates UUID4 if None.
        timestamp: Optional formatted timestamp; defaults to current time.
        db_path: Path to database.
        
    Returns:
        Dict[str, Any]: Saved message record.
        
    Raises:
        ValueError: If role is invalid, conversation_id is missing, or conversation does not exist.
    """
    if not conversation_id or not str(conversation_id).strip():
        raise ValueError("conversation_id cannot be empty.")

    clean_cid = str(conversation_id).strip()
    clean_role = str(role).strip().lower()
    if clean_role not in ("user", "assistant", "system"):
        raise ValueError(f"Invalid message role '{role}'. Must be 'user', 'assistant', or 'system'.")

    # Verify conversation exists
    conv = get_conversation(clean_cid, db_path=db_path)
    if not conv:
        raise ValueError(f"Cannot save message: Conversation [{clean_cid}] does not exist.")

    m_id = str(msg_id).strip() if msg_id else str(uuid.uuid4())
    ts = str(timestamp).strip() if timestamp else datetime.now().strftime("%H:%M:%S")
    now_iso = datetime.now().isoformat()
    cits_json = json.dumps(citations or [])

    with get_db(db_path) as conn:
        cursor = conn.cursor()

        # Determine next sequence_number atomically
        cursor.execute(
            """
            SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_seq
            FROM messages
            WHERE conversation_id = ?;
            """,
            (clean_cid,)
        )
        next_seq = cursor.fetchone()["next_seq"]

        # Insert message
        cursor.execute(
            """
            INSERT INTO messages (
                message_id, conversation_id, role, content,
                citations, is_cancelled, timestamp, sequence_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                m_id, clean_cid, clean_role, content or "",
                cits_json, 1 if is_cancelled else 0, ts, next_seq
            )
        )

        # Update conversation timestamp
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?;",
            (now_iso, clean_cid)
        )
        conn.commit()

    return {
        "message_id": m_id,
        "conversation_id": clean_cid,
        "role": clean_role,
        "content": content or "",
        "citations": citations or [],
        "is_cancelled": bool(is_cancelled),
        "timestamp": ts,
        "sequence_number": next_seq
    }


def get_conversation_messages(
    conversation_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Retrieves all messages for a given conversation in strict chronological sequence.
    Deserializes citations JSON back to structured list.
    
    Args:
        conversation_id: Target conversation ID.
        db_path: Path to database.
        
    Returns:
        List[Dict[str, Any]]: Chronologically sorted list of message dictionaries.
    """
    if not conversation_id or not str(conversation_id).strip():
        return []

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT message_id, conversation_id, role, content,
                   citations, is_cancelled, timestamp, sequence_number
            FROM messages
            WHERE conversation_id = ?
            ORDER BY sequence_number ASC;
            """,
            (str(conversation_id).strip(),)
        )
        rows = cursor.fetchall()

    messages: List[Dict[str, Any]] = []
    for r in rows:
        cits_raw = r["citations"]
        try:
            cits = json.loads(cits_raw) if cits_raw else []
        except Exception:
            cits = []

        messages.append({
            "message_id": r["message_id"],
            "conversation_id": r["conversation_id"],
            "role": r["role"],
            "content": r["content"],
            "citations": cits,
            "is_cancelled": bool(r["is_cancelled"]),
            "timestamp": r["timestamp"],
            "sequence_number": r["sequence_number"]
        })

    return messages


def get_conversation_with_messages(
    conversation_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Retrieves conversation metadata along with its full ordered message history.
    
    Args:
        conversation_id: Unique conversation identifier.
        db_path: Path to database.
        
    Returns:
        Optional[Dict[str, Any]]: Conversation record with 'messages' list, or None.
    """
    conv = get_conversation(conversation_id, db_path=db_path)
    if not conv:
        return None

    conv["messages"] = get_conversation_messages(conversation_id, db_path=db_path)
    return conv


# ============================================================================
# PHASE 8: HUMAN REVIEW & IMPACT DECISION PERSISTENCE
# ============================================================================

VALID_REVIEW_DECISIONS = {"PENDING", "ACCEPTED", "REJECTED", "INVESTIGATE"}

def save_impact_review(
    impact_id: str,
    source_change_id: str,
    source_sop_id: str,
    affected_sop_id: str,
    decision: str,
    reviewer_notes: str = "",
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Saves or updates a human review decision and note for a cross-document impact candidate.
    
    Args:
        impact_id: Unique impact candidate identifier.
        source_change_id: Change ID triggering the impact.
        source_sop_id: Source logical SOP ID.
        affected_sop_id: Affected logical SOP ID.
        decision: One of 'PENDING', 'ACCEPTED', 'REJECTED', 'INVESTIGATE'.
        reviewer_notes: Detailed notes or engineering rationale from reviewer.
        db_path: Path to database.
        
    Returns:
        Dict[str, Any]: The persisted review record.
    """
    init_database(db_path)

    clean_decision = str(decision).strip().upper()
    if clean_decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"Invalid review decision '{decision}'. Must be one of {VALID_REVIEW_DECISIONS}")

    clean_impact_id = str(impact_id).strip()
    if not clean_impact_id:
        raise ValueError("impact_id cannot be empty.")

    now_iso = datetime.now().isoformat()
    rev_id = str(uuid.uuid4())[:8]

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        # Upsert logic based on impact_id unique constraint
        cursor.execute(
            """
            INSERT INTO impact_reviews (
                review_id, impact_id, source_change_id, source_sop_id, affected_sop_id,
                decision, reviewer_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(impact_id) DO UPDATE SET
                decision = excluded.decision,
                reviewer_notes = excluded.reviewer_notes,
                updated_at = excluded.updated_at;
            """,
            (
                rev_id, clean_impact_id, str(source_change_id).strip(),
                str(source_sop_id).strip(), str(affected_sop_id).strip(),
                clean_decision, str(reviewer_notes).strip(), now_iso, now_iso
            )
        )
        conn.commit()

    return get_impact_review(clean_impact_id, db_path=db_path) or {}


def get_impact_review(
    impact_id: str,
    db_path: str = DEFAULT_DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the review record for a given impact ID if it exists.
    """
    init_database(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT review_id, impact_id, source_change_id, source_sop_id,
                   affected_sop_id, decision, reviewer_notes, created_at, updated_at
            FROM impact_reviews
            WHERE impact_id = ?;
            """,
            (str(impact_id).strip(),)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


def list_impact_reviews(
    source_sop_id: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Lists saved impact reviews, optionally filtered by source logical SOP ID.
    """
    init_database(db_path)
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        if source_sop_id:
            cursor.execute(
                """
                SELECT review_id, impact_id, source_change_id, source_sop_id,
                       affected_sop_id, decision, reviewer_notes, created_at, updated_at
                FROM impact_reviews
                WHERE source_sop_id = ?
                ORDER BY updated_at DESC;
                """,
                (str(source_sop_id).strip(),)
            )
        else:
            cursor.execute(
                """
                SELECT review_id, impact_id, source_change_id, source_sop_id,
                       affected_sop_id, decision, reviewer_notes, created_at, updated_at
                FROM impact_reviews
                ORDER BY updated_at DESC;
                """
            )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_database_health(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Performs diagnostic health check on the SQLite database.
    Verifies disk existence, connection capability, integrity check PRAGMA,
    table structures, and returns total conversation, message, and review counts.
    
    Args:
        db_path: Path to the SQLite database file.
        
    Returns:
        Dict[str, Any]: Diagnostic report with connectivity, counts, and issues list.
    """
    if not os.path.exists(db_path):
        return {
            "is_healthy": False,
            "connected": False,
            "file_exists": False,
            "path": db_path,
            "total_conversations": 0,
            "total_messages": 0,
            "total_reviews": 0,
            "file_size_bytes": 0,
            "issues": [f"Database file does not exist at '{db_path}'."]
        }

    issues = []
    total_convs = 0
    total_msgs = 0
    total_reviews = 0

    try:
        file_size = os.path.getsize(db_path)
        with get_db(db_path) as conn:
            cursor = conn.cursor()
            
            # 1. SQLite PRAGMA integrity check
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            if not row or str(row[0]).lower() != "ok":
                issues.append(f"SQLite PRAGMA integrity check failed: {row[0] if row else 'Empty response'}")

            # 2. Check conversations table
            try:
                cursor.execute("SELECT count(*) FROM conversations;")
                total_convs = cursor.fetchone()[0]
            except Exception as e_c:
                issues.append(f"Conversations table query failed: {e_c}")

            # 3. Check messages table
            try:
                cursor.execute("SELECT count(*) FROM messages;")
                total_msgs = cursor.fetchone()[0]
            except Exception as e_m:
                issues.append(f"Messages table query failed: {e_m}")

            # 4. Check impact_reviews table
            try:
                cursor.execute("SELECT count(*) FROM impact_reviews;")
                total_reviews = cursor.fetchone()[0]
            except Exception as e_r:
                issues.append(f"Impact reviews table query failed: {e_r}")

        return {
            "is_healthy": len(issues) == 0,
            "connected": True,
            "file_exists": True,
            "path": db_path,
            "total_conversations": total_convs,
            "total_messages": total_msgs,
            "total_reviews": total_reviews,
            "file_size_bytes": file_size,
            "issues": issues
        }
    except Exception as e:
        return {
            "is_healthy": False,
            "connected": False,
            "file_exists": True,
            "path": db_path,
            "total_conversations": 0,
            "total_messages": 0,
            "total_reviews": 0,
            "file_size_bytes": 0,
            "issues": [f"Database connection error: {str(e)}"]
        }


# ============================================================================
# SELF-TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    print("Testing database.py functionality...")
    test_db = os.path.join(DEFAULT_DATA_DIR, "test_self_check.db")
    if os.path.exists(test_db):
        os.remove(test_db)

    init_database(test_db)
    conv = create_conversation("Self-Check Consultation", db_path=test_db)
    cid = conv["conversation_id"]
    print(f"Created conversation: {cid}")

    m1 = save_message(cid, "user", "What is weld preheating?", db_path=test_db)
    m2 = save_message(
        cid,
        "assistant",
        "Preheating is required at 180 C.",
        citations=[{"citation": "[HVF_SOP_1.pdf, Rev 4, Sec 2, Page 3]", "score": 0.88}],
        db_path=test_db
    )
    print(f"Saved {m1['role']} message (seq {m1['sequence_number']})")
    print(f"Saved {m2['role']} message (seq {m2['sequence_number']})")

    msgs = get_conversation_messages(cid, db_path=test_db)
    print(f"Retrieved {len(msgs)} messages. Citations in assistant message: {len(msgs[1]['citations'])}")

    convs = list_conversations(db_path=test_db)
    print(f"Total conversations in list: {len(convs)}, message count: {convs[0]['message_count']}")

    delete_conversation(cid, db_path=test_db)
    msgs_after = get_conversation_messages(cid, db_path=test_db)
    print(f"Messages after cascade delete: {len(msgs_after)} (Expected: 0)")

    if os.path.exists(test_db):
        os.remove(test_db)
    print("Self-check completed successfully.")
