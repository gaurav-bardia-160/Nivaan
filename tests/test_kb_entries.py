from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_kb_entry_retrieval_aadhaar_enrolment():
    response = client.post("/api/ask", json={"input_type": "question", "question": "How do I enrol for a new Aadhaar card?", "language": "en"})
    assert response.status_code == 200
    assert "Aadhaar Enrolment Basics" in response.json()["title"]

def test_kb_entry_retrieval_link_pan_aadhaar():
    response = client.post("/api/ask", json={"input_type": "question", "question": "I need to link my PAN card with my Aadhaar.", "language": "en"})
    assert response.status_code == 200
    assert "Link PAN with Aadhaar" in response.json()["title"]

def test_kb_entry_retrieval_pf_withdrawal():
    response = client.post("/api/ask", json={"input_type": "question", "question": "How can I withdraw my PF money online?", "language": "en"})
    assert response.status_code == 200
    assert "EPF Withdrawal Process" in response.json()["title"]

def test_kb_entry_retrieval_police_fir():
    response = client.post("/api/ask", json={"input_type": "question", "question": "Steps to file an FIR at the police station.", "language": "en"})
    assert response.status_code == 200
    assert "Filing a First Information Report (FIR)" in response.json()["title"]

def test_kb_entry_retrieval_open_savings_account():
    response = client.post("/api/ask", json={"input_type": "question", "question": "How do I open a savings bank account?", "language": "en"})
    assert response.status_code == 200
    assert "Opening a Savings Bank Account" in response.json()["title"]

def test_kb_entry_retrieval_pm_kisan():
    response = client.post("/api/ask", json={"input_type": "question", "question": "How to register for PM Kisan Samman Nidhi Yojana?", "language": "en"})
    assert response.status_code == 200
    assert "PM Kisan Samman Nidhi Yojana" in response.json()["title"]

def test_kb_entry_retrieval_consumer_court():
    response = client.post("/api/ask", json={"input_type": "question", "question": "I want to file a complaint in consumer court against a seller.", "language": "en"})
    assert response.status_code == 200
    assert "Filing a Consumer Court Complaint" in response.json()["title"]


def test_kb_entry_retrieval_passport():
    response = client.post("/api/ask", json={"input_type": "question", "question": "how to make paspot", "language": "en"})
    assert response.status_code == 200
    data = response.json()
    assert "Passport" in data["title"]
    assert data["confidence"] in ["medium", "high"]
