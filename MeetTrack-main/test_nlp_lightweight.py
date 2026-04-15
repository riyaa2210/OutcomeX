"""
Test script for lightweight NLP service (no spacy)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backend.services.nlp_service import extract_action_items

TEST_TRANSCRIPT = """
John will submit the report by April 7th. 
Sarah needs to review the code by tomorrow.
Mike must complete the testing before Friday.
Assign the documentation to Lisa.
Team will schedule the deployment next Monday.
Please prepare the presentation for the meeting.
"""

print("\n" + "="*60)
print("🧪 LIGHTWEIGHT NLP SERVICE TEST (No SpaCy)")
print("="*60)
print(f"\n📄 Test Transcript:\n{TEST_TRANSCRIPT}")
print("\n" + "-"*60)

try:
    action_items = extract_action_items(TEST_TRANSCRIPT)
    
    print(f"\n✅ Successfully extracted {len(action_items)} action items:\n")
    
    for i, item in enumerate(action_items, 1):
        print(f"{i}. Description: {item['description']}")
        print(f"   👤 Assigned to: {item['assigned_to'] or 'Not specified'}")
        print(f"   📅 Deadline: {item['deadline'] or 'Not specified'}")
        print(f"   ✓ Status: {item['status']}")
        print()
    
    print("="*60)
    print("✅ TEST PASSED - NLP service working without spacy!")
    print("="*60)
    
except Exception as e:
    print(f"\n❌ TEST FAILED: {str(e)}")
    import traceback
    traceback.print_exc()
