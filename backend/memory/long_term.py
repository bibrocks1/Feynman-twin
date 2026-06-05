import os
from sqlalchemy.orm import Session as DBSession
from database.models import Message, LongTermMemory
from google import genai
import datetime

# We will use the google-genai client natively since it's cleaner for simple extraction
def extract_long_term_memory(db: DBSession, session_id: str, user_id: str = "guest"):
    """
    Checks if it's time to extract facts. If so, reads the conversation and extracts user traits.
    """
    # Count messages
    msg_count = db.query(Message).filter(Message.session_id == session_id).count()
    
    # Trigger extraction every 5 pairs (10 messages total) or every 5 user messages.
    # We'll trigger it when msg_count > 0 and msg_count % 10 == 0
    if msg_count > 0 and msg_count % 10 == 0:
        _perform_extraction(db, session_id, user_id)

def _perform_extraction(db: DBSession, session_id: str, user_id: str):
    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.timestamp.asc()).all()
    if not messages:
        return
        
    convo_text = "\n".join([f"{m.role.upper()}: {m.content}" for m in messages])
    
    prompt = f"""
    You are an AI tasked with analyzing a conversation between a User and Richard Feynman.
    Your goal is to extract key, persistent facts, traits, preferences, and background knowledge about the USER.
    Do NOT extract anything about Richard Feynman.
    Output a concise summary of the user's profile. If nothing notable exists, just output "No specific profile data yet."
    
    Conversation:
    {convo_text}
    
    User Profile Summary:
    """
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: No Gemini API Key found for long-term memory extraction.")
        return

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        extracted_text = response.text.strip()
        
        # Update or create DB record
        ltm = db.query(LongTermMemory).filter(LongTermMemory.user_id == user_id).first()
        if not ltm:
            ltm = LongTermMemory(user_id=user_id, extracted_profile=extracted_text)
            db.add(ltm)
        else:
            ltm.extracted_profile = extracted_text
            ltm.updated_at = datetime.datetime.utcnow()
            
        db.commit()
        print(f"Extracted long-term memory for user {user_id}: {extracted_text}")
    except Exception as e:
        print(f"ERROR [Background Task]: Failed to extract long term memory for {user_id}. Reason: {e}")
        # The background task will fail gracefully without crashing the main application.


def get_long_term_memory(db: DBSession, user_id: str = "guest") -> str:
    ltm = db.query(LongTermMemory).filter(LongTermMemory.user_id == user_id).first()
    return ltm.extracted_profile if ltm else "No specific profile data yet."
