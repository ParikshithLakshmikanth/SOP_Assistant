import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rag_engine
import database
import time
import json

test_questions = [
    ("Q1", "What are the main components of the turret mount system?", "all"),
    ("Q2", "What is the function of a ceramic-hybrid bearing?", "all"),
    ("Q3", "Explain the main components of the V12 powerpack.", "all"),
    ("Q4", "What are the basic parts of the suspension and track system?", "all"),
    ("Q5", "How are torsion suspension components related?", "all"),
    ("Q6", "What changed between V1 and V2 of turret integration?", "all"),
    ("Q7", "What are the main structural assemblies in hull welding?", "all"),
    ("Q8", "What are the engine alignment procedure steps?", "all"),
    ("Q_UNANSWERABLE", "What is the recommended air conditioning coolant type for the crew cabin?", "all"),
    ("Q_UNSUPPORTED_SPEC", "What is the top speed of the MBT on Mars surface?", "all"),
    ("Q_PROCEDURAL", "What torque setting is specified for the turret ring bolts?", "all"),
]

results = []

for q_id, q_text, rev_mode in test_questions:
    print(f"\n=======================================================")
    print(f"RUNNING {q_id}: {q_text} ({rev_mode})")
    print(f"=======================================================")
    t0 = time.time()
    res = rag_engine.answer_question(q_text, revision_mode=rev_mode)
    dt = time.time() - t0
    ans = res.get("answer", "")
    sources = res.get("sources", [])
    comp_matches = res.get("component_matches", [])
    print(f"Time: {dt:.2f}s | Sources: {len(sources)} | Matched comps: {len(comp_matches)}")
    print(f"Answer:\n{ans}\n")
    cites = []
    for s in sources:
        cites.append({
            "filename": s.get("filename"),
            "revision": s.get("revision"),
            "section": s.get("section") or s.get("section_title"),
            "page": s.get("page") or s.get("page_number")
        })
    print(f"Citations: {cites[:4]}")
    results.append({
        "q_id": q_id,
        "question": q_text,
        "revision_mode": rev_mode,
        "latency_sec": round(dt, 2),
        "answer": ans,
        "sources": cites,
        "component_matches_count": len(comp_matches)
    })

# Conversational follow-up test
print("\n=======================================================")
print("RUNNING FOLLOW-UP CONVERSATIONAL TEST")
print("=======================================================")
history = [
    {"role": "user", "content": "What is the function of a ceramic-hybrid bearing?"},
    {"role": "assistant", "content": "The ceramic-hybrid bearing is used in the turret traverse mechanism to reduce friction and rotational resistance during turret slewing."}
]
follow_up_q = "What lubrication or maintenance does it require?"
resolved_q = rag_engine.resolve_conversational_query(follow_up_q, history)
print(f"Original follow-up: {follow_up_q}")
print(f"Resolved query: {resolved_q}")
res_followup = rag_engine.answer_question(resolved_q, revision_mode="all")
print(f"Follow-up answer:\n{res_followup.get('answer')}")

results.append({
    "q_id": "Q_FOLLOWUP",
    "question": follow_up_q,
    "resolved_query": resolved_q,
    "answer": res_followup.get("answer"),
    "sources": [
        {"filename": s.get("filename"), "revision": s.get("revision"), "page": s.get("page") or s.get("page_number")}
        for s in res_followup.get("sources", [])
    ]
})

with open("tests/phase7_rag_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("\nSaved all RAG results to tests/phase7_rag_results.json")
