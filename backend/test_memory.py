import os
from dotenv import load_dotenv
load_dotenv()

from database.db import SessionLocal
from database.models import Message, LongTermMemory
from memory.short_term import get_or_create_session, add_message, get_recent_messages
from memory.long_term import extract_long_term_memory, get_long_term_memory

def run_test():
    db = SessionLocal()
    session_id = get_or_create_session(db)
    user_id = "test_user_1"
    
    # Simulate a conversation
    messages = [
        ("user", "Hi Dr. Feynman! I'm a first-year undergraduate physics student."),
        ("assistant", "Hello! Welcome to the exciting world of physics."),
        ("user", "I'm having a lot of trouble understanding quantum mechanics. It seems so counter-intuitive."),
        ("assistant", "Well, if you think you understand quantum mechanics, you don't understand quantum mechanics!"),
        ("user", "Haha, true. But I specifically struggle with the probability amplitude concept."),
        ("assistant", "It's tricky. Imagine light as particles taking every possible path..."),
        ("user", "Does that mean particles can travel back in time?"),
        ("assistant", "Mathematically, a positron is an electron traveling backward in time!"),
        ("user", "Wow, that blows my mind. I'll read QED tonight."),
        ("assistant", "Excellent choice. Have fun reading it!"),
    ]
    
    print(f"Adding 10 messages to session {session_id}...")
    for role, content in messages:
        add_message(db, session_id, role, content)
        
    print("Triggering long term memory extraction...")
    # Manually trigger to test the logic
    extract_long_term_memory(db, session_id, user_id)
    
    print("\n--- DB VERIFICATION ---")
    ltm = get_long_term_memory(db, user_id)
    print(f"Extracted Profile:\n{ltm}")
    
    print("\nTest Complete!")

if __name__ == "__main__":
    run_test()
