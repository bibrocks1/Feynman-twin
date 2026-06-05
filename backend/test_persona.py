from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_test():
    print("Testing Feynman Persona with Context...")
    
    # 1. Ask a basic question to see the tone
    res1 = client.post("/api/chat", json={
        "message": "Why do magnets attract each other?",
        "user_id": "test_persona_user"
    })
    
    data = res1.json()
    print("\n--- RESPONSE 1 ---")
    print(data.get("response", "Error"))
    
    # 2. Ask something anachronistic
    session_id = data.get("session_id")
    res2 = client.post("/api/chat", json={
        "message": "What do you think about people using smartphones to watch TikTok videos all day?",
        "session_id": session_id,
        "user_id": "test_persona_user"
    })
    
    print("\n--- RESPONSE 2 (Anachronism Test) ---")
    print(res2.json().get("response", "Error"))

if __name__ == "__main__":
    run_test()
