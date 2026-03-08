anot"""
Validation script for error handling improvements.

This script tests the metadata endpoints to ensure proper error handling
for duplicate key violations and other database integrity errors.

Run this after starting the server to validate the fixes.
"""

import requests
import json

BASE_URL = "http://localhost:8000/api/v1"


def test_create_grade_duplicate():
    """Test that creating a duplicate grade returns 409 Conflict."""
    print("\n=== Testing Grade Creation (Duplicate) ===")
    
    # First creation should succeed
    grade_data = {
        "id": "TEST_GRADE_1",
        "name": "Test Grade 1",
        "level": "1",
        "display_order": 100
    }
    
    print(f"Creating grade: {grade_data['id']}")
    response1 = requests.post(f"{BASE_URL}/meta/grades", json=grade_data)
    print(f"First attempt: {response1.status_code}")
    
    if response1.status_code == 201:
        print("✓ First creation succeeded")
    elif response1.status_code == 409:
        print("⚠ Grade already exists from previous test")
    else:
        print(f"✗ Unexpected status: {response1.status_code}")
        print(f"Response: {response1.text}")
    
    # Second creation should return 409
    print(f"\nAttempting duplicate creation...")
    response2 = requests.post(f"{BASE_URL}/meta/grades", json=grade_data)
    print(f"Second attempt: {response2.status_code}")
    
    if response2.status_code == 409:
        print("✓ Duplicate correctly rejected with 409 Conflict")
        response_data = response2.json()
        print(f"Error message: {response_data.get('detail')}")
        print(f"Error type: {response_data.get('error_type')}")
        return True
    else:
        print(f"✗ Expected 409, got {response2.status_code}")
        print(f"Response: {response2.text}")
        return False


def test_create_subject_duplicate():
    """Test that creating a duplicate subject returns 409 Conflict."""
    print("\n=== Testing Subject Creation (Duplicate) ===")
    
    subject_data = {
        "id": "test_subject_1",
        "name": "Test Subject 1",
        "display_order": 100,
        "icon": "test-icon"
    }
    
    print(f"Creating subject: {subject_data['id']}")
    response1 = requests.post(f"{BASE_URL}/meta/subjects", json=subject_data)
    print(f"First attempt: {response1.status_code}")
    
    if response1.status_code == 201:
        print("✓ First creation succeeded")
    elif response1.status_code == 409:
        print("⚠ Subject already exists from previous test")
    
    # Second creation should return 409
    print(f"\nAttempting duplicate creation...")
    response2 = requests.post(f"{BASE_URL}/meta/subjects", json=subject_data)
    print(f"Second attempt: {response2.status_code}")
    
    if response2.status_code == 409:
        print("✓ Duplicate correctly rejected with 409 Conflict")
        response_data = response2.json()
        print(f"Error message: {response_data.get('detail')}")
        print(f"Error type: {response_data.get('error_type')}")
        return True
    else:
        print(f"✗ Expected 409, got {response2.status_code}")
        print(f"Response: {response2.text}")
        return False


def test_create_topic_duplicate():
    """Test that creating a duplicate topic returns 409 Conflict."""
    print("\n=== Testing Topic Creation (Duplicate) ===")
    
    # Note: Topics use UUID, so we can't easily test duplicates
    # This test verifies the endpoint works correctly
    topic_data = {
        "title": "Test Topic",
        "grade": "S1",
        "subject": "mathematics",
        "page_start": 1,
        "page_end": 10,
        "path": ["Chapter 1"]
    }
    
    print(f"Creating topic: {topic_data['title']}")
    response = requests.post(f"{BASE_URL}/meta/topics", json=topic_data)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 201:
        print("✓ Topic creation succeeded")
        return True
    else:
        print(f"✗ Unexpected status: {response.status_code}")
        print(f"Response: {response.text}")
        return False


def test_error_response_structure():
    """Test that error responses have proper structure."""
    print("\n=== Testing Error Response Structure ===")
    
    # Create a duplicate to get an error response
    grade_data = {
        "id": "TEST_GRADE_2",
        "name": "Test Grade 2",
        "level": "2",
        "display_order": 101
    }
    
    # Create once
    requests.post(f"{BASE_URL}/meta/grades", json=grade_data)
    
    # Create duplicate
    response = requests.post(f"{BASE_URL}/meta/grades", json=grade_data)
    
    if response.status_code == 409:
        data = response.json()
        
        # Check required fields
        has_detail = "detail" in data
        has_error_type = "error_type" in data
        
        print(f"Has 'detail' field: {has_detail}")
        print(f"Has 'error_type' field: {has_error_type}")
        print(f"Detail: {data.get('detail')}")
        print(f"Error type: {data.get('error_type')}")
        
        if has_detail and has_error_type:
            print("✓ Error response structure is correct")
            return True
        else:
            print("✗ Error response missing required fields")
            return False
    else:
        print(f"✗ Could not test error structure (status: {response.status_code})")
        return False


def main():
    """Run all validation tests."""
    print("=" * 60)
    print("ERROR HANDLING VALIDATION TESTS")
    print("=" * 60)
    print("\nMake sure the server is running at http://localhost:8000")
    print("Press Enter to continue...")
    input()
    
    results = []
    
    try:
        results.append(("Grade Duplicate", test_create_grade_duplicate()))
        results.append(("Subject Duplicate", test_create_subject_duplicate()))
        results.append(("Topic Creation", test_create_topic_duplicate()))
        results.append(("Error Structure", test_error_response_structure()))
    except requests.exceptions.ConnectionError:
        print("\n✗ Could not connect to server. Is it running?")
        return
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Error handling is working correctly.")
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Please review the output above.")


if __name__ == "__main__":
    main()
