import pytest
from unittest.mock import patch
from app import create_app, stylometric_signal

TEST_CONFIG = {
    "TESTING": True,
    "RATELIMIT_ENABLED": True,
    "RATELIMIT_STORAGE_URI": "memory://",
}


@pytest.fixture
def app():
    application = create_app(TEST_CONFIG)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_submit_returns_required_fields(client):
    with patch("app.llm_signal", return_value=0.5):
        resp = client.post("/submit", json={"text": "test text", "creator_id": "u1"})
    data = resp.get_json()
    for key in ("content_id", "attribution", "confidence", "llm_score", "stylometric_score", "label_text", "status"):
        assert key in data


def test_submit_ai_text_scores_high(client):
    with patch("app.llm_signal", return_value=0.9):
        resp = client.post("/submit", json={
            "text": "Artificial intelligence represents a transformative paradigm shift.",
            "creator_id": "u1",
        })
    data = resp.get_json()
    assert data["confidence"] > 0.65
    assert data["attribution"] == "likely_ai"


def test_submit_human_text_scores_low(client):
    with patch("app.llm_signal", return_value=0.1):
        resp = client.post("/submit", json={
            "text": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after.",
            "creator_id": "u1",
        })
    data = resp.get_json()
    assert data["confidence"] < 0.35
    assert data["attribution"] == "likely_human"


def test_all_three_label_variants_reachable(client):
    for llm_val, expected in [(0.85, "likely_ai"), (0.50, "uncertain"), (0.10, "likely_human")]:
        with patch("app.llm_signal", return_value=llm_val):
            resp = client.post("/submit", json={"text": "sample text here for testing purposes only", "creator_id": "u1"})
        assert resp.get_json()["attribution"] == expected, f"llm={llm_val} expected {expected}"


def test_appeal_updates_status(client):
    with patch("app.llm_signal", return_value=0.9):
        submit_resp = client.post("/submit", json={"text": "AI-like text here.", "creator_id": "u1"})
    content_id = submit_resp.get_json()["content_id"]

    appeal_resp = client.post("/appeal", json={
        "content_id": content_id,
        "creator_reasoning": "I wrote this myself.",
    })
    assert appeal_resp.get_json()["status"] == "under_review"

    log_resp = client.get("/log")
    entries = log_resp.get_json()["entries"]
    appeal_entries = [e for e in entries if e["content_id"] == content_id and e["status"] == "under_review"]
    assert len(appeal_entries) >= 1
    assert appeal_entries[0]["appeal_reasoning"] is not None


def test_appeal_unknown_content_id_returns_404(client):
    import uuid
    resp = client.post("/appeal", json={
        "content_id": str(uuid.uuid4()),
        "creator_reasoning": "test",
    })
    assert resp.status_code == 404


def test_log_returns_structured_entries(client):
    with patch("app.llm_signal", return_value=0.5):
        for _ in range(3):
            client.post("/submit", json={"text": "some text", "creator_id": "u1"})
    entries = client.get("/log").get_json()["entries"]
    assert len(entries) >= 3
    for e in entries:
        for key in ("content_id", "timestamp", "attribution", "confidence"):
            assert key in e


def test_rate_limit_triggers_429(client):
    statuses = []
    with patch("app.llm_signal", return_value=0.5):
        for _ in range(11):
            r = client.post("/submit", json={"text": "rate limit test", "creator_id": "u1"})
            statuses.append(r.status_code)
    assert 429 in statuses


def test_stylometric_signal_directly():
    ai_text = (
        "Artificial intelligence represents a transformative paradigm shift in modern society. "
        "It is important to note that while the benefits of AI are numerous, it is equally "
        "essential to consider the ethical implications. Furthermore, stakeholders across "
        "various sectors must collaborate to ensure responsible deployment."
    )
    human_text = (
        "ok so i finally tried that new ramen place downtown and honestly? underwhelming. "
        "the broth was fine but they put WAY too much sodium in it and i was thirsty for like "
        "three hours after. my friend got the spicy version and said it was better. "
        "probably wont go back unless someone drags me there"
    )
    assert stylometric_signal(ai_text) > stylometric_signal(human_text)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
