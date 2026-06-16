from pathlib import Path

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def assert_status(response, expected=200):
    if response.status_code != expected:
        raise AssertionError(f"Expected {expected}, got {response.status_code}: {response.text}")


def preview(text, limit=180):
    if not text:
        return ""
    return text[:limit].replace("\n", " ")


def main():
    test_file = Path("test_files/acme_sales_kb.txt")

    health = client.get("/api/health")
    assert_status(health)

    removed_legacy_upload = client.post("/api/upload")
    assert_status(removed_legacy_upload, 404)

    invalid_chat = client.post(
        "/api/chat",
        json={"message": "What is generative AI?", "module_id": "string"},
    )
    assert_status(invalid_chat, 404)

    listed_modules = client.get("/api/kb/modules")
    assert_status(listed_modules)
    modules_json = listed_modules.json()
    assert len(modules_json["modules"]) >= 4, "Core modules should be seeded"
    
    module_id = modules_json["modules"][0]["id"]

    with test_file.open("rb") as file:
        uploaded = client.post(
            f"/api/kb/modules/{module_id}/documents",
            files={"file": ("acme_sales_kb.txt", file, "text/plain")},
        )
    assert_status(uploaded)
    upload_json = uploaded.json()
    document = upload_json["document"]

    listed = client.get("/api/kb/modules")
    assert_status(listed)

    chat = client.post(
        "/api/chat",
        json={
            "message": "How should I respond when a buyer says they do not trust AI answers?",
            "module_id": module_id,
            "sales_rep_id": "rep-test-1",
            "crm_context": {"company": "TestCo", "stage": "Discovery"},
        },
    )
    assert_status(chat)

    questions = client.get(f"/api/test/start?module_id={module_id}")
    assert_status(questions)

    text_eval = client.post(
        "/api/test/evaluate",
        json={
            "question": "Why should we trust the AI answers?",
            "answer": "It only answers from approved company knowledge base documents and admits when there is not enough information.",
            "module_id": module_id,
        },
    )
    assert_status(text_eval)

    mock_start = client.post(
        "/api/mock-call/start",
        json={"sales_rep_id": "rep-test-1", "module_id": module_id},
    )
    assert_status(mock_start)

    mock_eval = client.post(
        "/api/mock-call/evaluate",
        json={
            "session_id": mock_start.json()["session_id"],
            "transcript": (
                "Client: I do not trust AI answers. "
                "Rep: Our assistant only uses approved knowledge base documents and tells the rep when it lacks information. "
                "Client: What about implementation time? "
                "Rep: We start with a focused pilot using existing CRM data."
            ),
            "module_id": module_id,
            "text_question": "What is the business value?",
            "text_answer": "It reduces ramp time, improves productivity, and makes messaging consistent.",
        },
    )
    assert_status(mock_eval)

    history = client.get(f"/api/mock-call/history?module_id={module_id}")
    assert_status(history)

    deleted_doc = client.delete(
        f"/api/kb/modules/{module_id}/documents/{document['id']}"
    )
    assert_status(deleted_doc)

    result = {
        "health": health.json()["status"],
        "legacy_upload_removed": removed_legacy_upload.status_code == 404,
        "invalid_module_rejected": invalid_chat.status_code == 404,
        "module_created": module_id,
        "upload_status": document["status"],
        "upload_chunks": document.get("chunk_count"),
        "module_count_seen": len(listed.json()["modules"]),
        "chat_preview": preview(chat.json()["response"]),
        "generated_question_count": len(questions.json()["questions"]),
        "text_score": text_eval.json()["score"],
        "mock_token_generated": bool(mock_start.json()["participant_token"]),
        "mock_kb_context_present": bool(mock_start.json().get("kb_context")),
        "mock_final_score": mock_eval.json()["final_score"],
        "mock_breakdown_present": all(
            key in mock_eval.json()
            for key in ["product_accuracy", "discovery", "objection_handling", "empathy", "closing_clarity"]
        ),
        "history_records": len(history.json()["records"]),
        "document_delete_vectors": deleted_doc.json()["deleted_vectors"]
    }
    print(result)


if __name__ == "__main__":
    main()
