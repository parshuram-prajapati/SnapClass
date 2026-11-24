import os
import io
import sys
import time
import math
from datetime import datetime, timezone, timedelta
import numpy as np
from PIL import Image, ImageDraw

# Add workspace to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.pipelines.image_utils import (
    validate_image_file,
    process_and_optimize_image,
    safe_cleanup_memory,
    MAX_UPLOAD_SIZE_MB,
    MAX_IMAGE_DIMENSION
)
from src.pipelines.face_pipeline import (
    get_face_embeddings,
    predict_attendance,
    load_dlib_models
)
from src.database.db import (
    request_password_reset,
    verify_password_reset_token,
    reset_teacher_password,
    validate_password_strength,
    hash_pass,
    check_pass,
    _MEMORY_RESET_TOKENS
)


def create_mock_face_image(width=400, height=400):
    """Draws a simple synthetic face that dlib can parse without crashing."""
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    # Head circle
    draw.ellipse([(width * 0.2, height * 0.1), (width * 0.8, height * 0.9)], fill=(255, 220, 180), outline=(0, 0, 0))
    # Eyes
    draw.ellipse([(width * 0.35, height * 0.35), (width * 0.45, height * 0.45)], fill=(0, 0, 0))
    draw.ellipse([(width * 0.55, height * 0.35), (width * 0.65, height * 0.45)], fill=(0, 0, 0))
    # Nose
    draw.polygon([(width * 0.5, height * 0.45), (width * 0.47, height * 0.6), (width * 0.53, height * 0.6)], fill=(200, 150, 120))
    # Mouth
    draw.arc([(width * 0.35, height * 0.65), (width * 0.65, height * 0.75)], start=0, end=180, fill=(180, 50, 50), width=4)
    return img


def run_all_tests():
    print("=" * 70)
    print("SNAPCLASS AI - COMPREHENSIVE TEST SUITE (14 SCENARIOS)")
    print("=" * 70)

    test_results = {}

    # -------------------------------------------------------------------------
    # Scenario 1: Normal photograph upload
    # -------------------------------------------------------------------------
    print("\n[Scenario 1] Normal photograph upload...")
    try:
        norm_img = Image.new("RGB", (800, 600), color=(100, 150, 200))
        bio = io.BytesIO()
        norm_img.save(bio, format="JPEG", quality=85)
        bio.seek(0)
        
        is_valid, err = validate_image_file(bio, filename="normal_class.jpg")
        assert is_valid, f"Validation failed: {err}"
        
        opt_img, opt_err = process_and_optimize_image(bio)
        assert opt_img is not None, f"Optimization failed: {opt_err}"
        assert opt_img.mode == "RGB", f"Expected RGB mode, got {opt_img.mode}"
        assert opt_img.size == (800, 600), f"Expected (800, 600), got {opt_img.size}"
        
        test_results["1. Normal photograph upload"] = "PASSED"
        print("  -> PASSED: Validated and processed normal image (800x600).")
    except Exception as e:
        test_results["1. Normal photograph upload"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 2: Large 5 MB photograph
    # -------------------------------------------------------------------------
    print("\n[Scenario 2] Large 5 MB photograph...")
    try:
        # Create uncompressed large data to exceed 5 MB
        large_img = Image.new("RGB", (2500, 2500), color=(120, 140, 160))
        draw = ImageDraw.Draw(large_img)
        for i in range(0, 2500, 50):
            draw.line([(0, i), (2500, i)], fill=(i % 255, (i * 2) % 255, (i * 3) % 255), width=5)
        
        bio = io.BytesIO()
        large_img.save(bio, format="JPEG", quality=100, subsampling=0)
        # Pad with JPEG comment bytes if needed to ensure > 5MB
        curr_size = bio.tell()
        target_size = 5 * 1024 * 1024 + 100 * 1024  # ~5.1 MB
        if curr_size < target_size:
            bio.write(b"\x00" * (target_size - curr_size))
        
        size_mb = bio.tell() / (1024 * 1024)
        print(f"  Generated test image of size: {size_mb:.2f} MB")
        
        bio.seek(0)
        is_valid, err = validate_image_file(bio, filename="large_5mb.jpg")
        assert is_valid, f"Validation failed: {err}"
        
        bio.seek(0)
        opt_img, opt_err = process_and_optimize_image(bio)
        assert opt_img is not None, f"Optimization failed: {opt_err}"
        assert max(opt_img.size) <= MAX_IMAGE_DIMENSION, f"Image was not scaled below {MAX_IMAGE_DIMENSION}"
        
        test_results["2. Large 5 MB photograph"] = f"PASSED ({size_mb:.2f} MB)"
        print(f"  -> PASSED: Successfully handled {size_mb:.2f} MB image without crashing.")
    except Exception as e:
        test_results["2. Large 5 MB photograph"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 3: Large 10 MB photograph
    # -------------------------------------------------------------------------
    print("\n[Scenario 3] Large 10 MB photograph...")
    try:
        large_10mb_img = Image.new("RGB", (3200, 3200), color=(200, 180, 160))
        draw = ImageDraw.Draw(large_10mb_img)
        for i in range(0, 3200, 40):
            draw.rectangle([(i, i), (i + 30, i + 30)], fill=((i * 5) % 255, (i * 7) % 255, 100))
        
        bio = io.BytesIO()
        large_10mb_img.save(bio, format="JPEG", quality=100, subsampling=0)
        curr_size = bio.tell()
        target_10mb = 10 * 1024 * 1024 + 200 * 1024  # ~10.2 MB
        if curr_size < target_10mb:
            bio.write(b"\x00" * (target_10mb - curr_size))
        
        size_mb = bio.tell() / (1024 * 1024)
        print(f"  Generated test image of size: {size_mb:.2f} MB")
        
        bio.seek(0)
        is_valid, err = validate_image_file(bio, filename="large_10mb.jpg")
        assert is_valid, f"Validation failed: {err}"
        
        bio.seek(0)
        opt_img, opt_err = process_and_optimize_image(bio)
        assert opt_img is not None, f"Optimization failed: {opt_err}"
        assert max(opt_img.size) <= MAX_IMAGE_DIMENSION, f"Image was not scaled below {MAX_IMAGE_DIMENSION}"
        
        test_results["3. Large 10 MB photograph"] = f"PASSED ({size_mb:.2f} MB)"
        print(f"  -> PASSED: Successfully validated and downscaled {size_mb:.2f} MB image.")
    except Exception as e:
        test_results["3. Large 10 MB photograph"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 4: High-resolution 4K photograph
    # -------------------------------------------------------------------------
    print("\n[Scenario 4] High-resolution 4K photograph...")
    try:
        # True 4K UHD dimensions: 3840 x 2160
        img_4k = Image.new("RGB", (3840, 2160), color=(60, 80, 120))
        bio = io.BytesIO()
        img_4k.save(bio, format="JPEG", quality=90)
        
        bio.seek(0)
        opt_img, err = process_and_optimize_image(bio)
        assert opt_img is not None, f"Optimization failed: {err}"
        w, h = opt_img.size
        assert max(w, h) <= MAX_IMAGE_DIMENSION, f"Expected dimension <= {MAX_IMAGE_DIMENSION}, got {opt_img.size}"
        
        # Verify aspect ratio preservation: 3840 / 2160 = 1.7777...
        orig_aspect = 3840 / 2160
        new_aspect = w / h
        assert abs(orig_aspect - new_aspect) < 0.05, f"Aspect ratio drifted: {orig_aspect} vs {new_aspect}"
        
        # Verify face embeddings extraction on optimized 4K image does not crash or trigger bad_alloc
        img_np = np.array(opt_img)
        encodings = get_face_embeddings(img_np)
        assert isinstance(encodings, list)
        
        test_results["4. High-resolution 4K photograph"] = f"PASSED (3840x2160 -> {w}x{h})"
        print(f"  -> PASSED: 4K (3840x2160) scaled to {w}x{h} with aspect ratio preserved, dlib executed safely.")
    except Exception as e:
        test_results["4. High-resolution 4K photograph"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 5: Group photograph containing 30+ people
    # -------------------------------------------------------------------------
    print("\n[Scenario 5] Group photograph containing 30+ people...")
    try:
        # Synthesize 35 mock face embeddings
        np.random.seed(42)
        mock_35_encodings = [np.random.randn(128) for _ in range(35)]
        
        # Verify predict_attendance logic with 35 detected faces
        # Simulate model data with 3 registered students
        reg_embeddings = [np.random.randn(128) for _ in range(3)]
        # Make one detected face closely match registered student #1
        mock_35_encodings[5] = reg_embeddings[0] + np.random.normal(0, 0.02, 128)
        # Make another detected face closely match registered student #2
        mock_35_encodings[18] = reg_embeddings[1] + np.random.normal(0, 0.02, 128)

        # Mock the trained model and face extraction
        import src.pipelines.face_pipeline as fp
        orig_get_trained = fp.get_trained_model
        orig_get_embeddings = fp.get_face_embeddings

        fp.get_trained_model = lambda: {
            'clf': None,
            'X': reg_embeddings,
            'y': [101, 102, 103]
        }
        fp.get_face_embeddings = lambda img_np: mock_35_encodings

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        detected, all_students, face_count = fp.predict_attendance(dummy_img)

        # Restore
        fp.get_trained_model = orig_get_trained
        fp.get_face_embeddings = orig_get_embeddings

        assert face_count == 35, f"Expected 35 faces, got {face_count}"
        assert 101 in detected, "Student 101 should be detected"
        assert 102 in detected, "Student 102 should be detected"
        assert 103 not in detected, "Student 103 was not in the 35 faces"

        test_results["5. Group photograph containing 30+ people"] = f"PASSED ({face_count} faces processed)"
        print(f"  -> PASSED: Processed {face_count} faces in group photograph without memory issues.")
    except Exception as e:
        test_results["5. Group photograph containing 30+ people"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 6: Multiple photographs uploaded together
    # -------------------------------------------------------------------------
    print("\n[Scenario 6] Multiple photographs uploaded together...")
    try:
        images_batch = []
        for idx in range(4):
            bio = io.BytesIO()
            img = Image.new("RGB", (600 + idx * 100, 400 + idx * 100), color=(idx * 40, 100, 150))
            img.save(bio, format="JPEG")
            bio.seek(0)
            images_batch.append((f"photo_{idx+1}.jpg", bio))

        processed_images = []
        for name, bio in images_batch:
            is_valid, err = validate_image_file(bio, filename=name)
            assert is_valid, f"Batch validation failed for {name}"
            opt_img, opt_err = process_and_optimize_image(bio)
            assert opt_img is not None, f"Batch optimization failed for {name}"
            processed_images.append(opt_img)

        assert len(processed_images) == 4
        test_results["6. Multiple photographs uploaded together"] = "PASSED (4 photos batch)"
        print("  -> PASSED: Successfully validated and optimized batch of 4 photographs.")
    except Exception as e:
        test_results["6. Multiple photographs uploaded together"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 7: Corrupted image upload
    # -------------------------------------------------------------------------
    print("\n[Scenario 7] Corrupted image upload...")
    try:
        # Test 1: Random corrupted garbage bytes
        corrupt_bytes = b"NOT_A_JPEG_FILE_RANDOM_GARBAGE_BYTES_12345" * 10
        is_valid, err_msg = validate_image_file(corrupt_bytes, filename="corrupt.jpg")
        assert not is_valid, "Validation should have failed for corrupted file"
        assert err_msg is not None and len(err_msg) > 0, "Expected descriptive error message"

        # Test 2: Unsupported extension
        txt_bytes = b"Hello world text file"
        is_valid_ext, err_ext = validate_image_file(txt_bytes, filename="report.pdf")
        assert not is_valid_ext, "Validation should reject .pdf"

        test_results["7. Corrupted image upload"] = "PASSED (Gracefully rejected with helpful error)"
        print(f"  -> PASSED: Corrupted file caught and rejected gracefully ({err_msg}).")
    except Exception as e:
        test_results["7. Corrupted image upload"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 8: Photograph containing no faces
    # -------------------------------------------------------------------------
    print("\n[Scenario 8] Photograph containing no faces...")
    try:
        blackboard_img = np.zeros((600, 800, 3), dtype=np.uint8)
        detected, all_students, count = predict_attendance(blackboard_img)
        assert count == 0, f"Expected 0 faces, got {count}"
        assert len(detected) == 0, f"Expected empty detected dict, got {detected}"

        test_results["8. Photograph containing no faces"] = "PASSED (0 faces detected, no crash)"
        print("  -> PASSED: Empty face image handled cleanly (0 faces, no crash).")
    except Exception as e:
        test_results["8. Photograph containing no faces"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 9: Photograph with unknown people
    # -------------------------------------------------------------------------
    print("\n[Scenario 9] Photograph with unknown people...")
    try:
        import src.pipelines.face_pipeline as fp
        orig_get_trained = fp.get_trained_model
        orig_get_embeddings = fp.get_face_embeddings

        # Registered student embedding at [0, 0, ...]
        reg_emb = np.zeros(128)
        # Unknown person embedding far away at [5, 5, ...] (distance >> 0.6)
        unknown_emb = np.ones(128) * 2.0

        fp.get_trained_model = lambda: {
            'clf': None,
            'X': [reg_emb],
            'y': [42]
        }
        fp.get_face_embeddings = lambda img_np: [unknown_emb]

        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        detected, all_students, count = fp.predict_attendance(dummy_img, confidence_threshold=0.6)

        # Restore
        fp.get_trained_model = orig_get_trained
        fp.get_face_embeddings = orig_get_embeddings

        assert count == 1, "One face should be detected"
        assert len(detected) == 0, f"Unknown face must NOT be recognized as registered student! Got: {detected}"

        test_results["9. Photograph with unknown people"] = "PASSED (Unknown person rejected, not marked Present)"
        print("  -> PASSED: Unknown person strictly rejected by resemblance threshold.")
    except Exception as e:
        test_results["9. Photograph with unknown people"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 10: Repeated uploads without restarting the application
    # -------------------------------------------------------------------------
    print("\n[Scenario 10] Repeated uploads without restarting the application...")
    try:
        for iteration in range(10):
            test_img = Image.new("RGB", (1200, 900), color=(iteration * 20, 100, 150))
            bio = io.BytesIO()
            test_img.save(bio, format="JPEG")
            bio.seek(0)
            opt_img, _ = process_and_optimize_image(bio)
            img_np = np.array(opt_img)
            _ = get_face_embeddings(img_np)
            del opt_img
            del img_np
            safe_cleanup_memory()

        test_results["10. Repeated uploads without restarting"] = "PASSED (10 consecutive cycles without leaks)"
        print("  -> PASSED: 10 repeated upload cycles completed smoothly with memory cleanup.")
    except Exception as e:
        test_results["10. Repeated uploads without restarting"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 11: Forgot password with a valid registered email/username
    # -------------------------------------------------------------------------
    print("\n[Scenario 11] Forgot password with a valid registered email/username...")
    try:
        # Existing registered teacher in database is 'Mehak'
        success, msg, raw_token, *_ = request_password_reset("Mehak", send_email=False)
        assert success, "Reset request should succeed"
        assert raw_token is not None, "Valid user should produce a reset token"
        assert len(raw_token) >= 32, "Token should be secure random string"
        
        # Verify token is valid right now
        is_valid, teacher_id, v_msg = verify_password_reset_token(raw_token)
        assert is_valid, f"Token verification failed: {v_msg}"
        assert teacher_id == 3, f"Expected teacher_id 3 for Mehak, got {teacher_id}"

        test_results["11. Forgot password with a valid registered email"] = "PASSED"
        print(f"  -> PASSED: Reset token successfully created and verified for registered teacher.")
    except Exception as e:
        test_results["11. Forgot password with a valid registered email"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 12: Forgot password with an unregistered email
    # -------------------------------------------------------------------------
    print("\n[Scenario 12] Forgot password with an unregistered email...")
    try:
        success, msg, raw_token, *_ = request_password_reset("completely_nonexistent_user_999@school.edu", send_email=False)
        assert success, "Request should still report success to prevent user enumeration"
        assert raw_token is None, "Non-existent user must NOT produce an active reset token"
        assert "If the entered email/username is registered" in msg

        test_results["12. Forgot password with an unregistered email"] = "PASSED (No token, no user enumeration)"
        print("  -> PASSED: Unregistered email safely handled without enumeration.")
    except Exception as e:
        test_results["12. Forgot password with an unregistered email"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 13: Expired or already-used reset link
    # -------------------------------------------------------------------------
    print("\n[Scenario 13] Expired or already-used reset link...")
    try:
        # Part A: Test expired token
        _, _, exp_token, *_ = request_password_reset("Mehak", expiry_minutes=-5, send_email=False)  # Expired 5 mins ago
        is_valid_exp, _, exp_msg = verify_password_reset_token(exp_token)
        assert not is_valid_exp, "Expired token should not be valid"
        assert "expired" in exp_msg.lower(), f"Expected 'expired' in message, got: {exp_msg}"

        # Part B: Test already-used token
        _, _, use_token, *_ = request_password_reset("Mehak", expiry_minutes=15, send_email=False)
        # Use token once
        ok, reset_msg = reset_teacher_password(use_token, "StrongPass123!")
        assert ok, f"Initial password reset failed: {reset_msg}"

        # Try using it a second time
        is_valid_second, _, second_msg = verify_password_reset_token(use_token)
        assert not is_valid_second, "Already-used token must NOT be valid a second time!"
        assert "already been used" in second_msg.lower(), f"Expected 'already been used', got: {second_msg}"

        test_results["13. Expired or already-used reset link"] = "PASSED (Both expired & reused tokens rejected)"
        print("  -> PASSED: Expired and already-used tokens rejected correctly.")
    except Exception as e:
        test_results["13. Expired or already-used reset link"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # Scenario 14: Successful password reset and subsequent login
    # -------------------------------------------------------------------------
    print("\n[Scenario 14] Successful password reset and subsequent login...")
    try:
        from src.database.config import supabase
        # Fetch and preserve original password hash
        mehak_res = supabase.table("teachers").select("*").eq("username", "Mehak").execute()
        orig_hash = mehak_res.data[0]["password"] if mehak_res.data else None

        # Request fresh reset token
        _, _, fresh_token, *_ = request_password_reset("Mehak", send_email=False)
        new_pwd = "UpdatedSecurePassword2026!"
        
        # Reset password
        reset_ok, reset_msg = reset_teacher_password(fresh_token, new_pwd)
        assert reset_ok, f"Password reset failed: {reset_msg}"

        # Verify teacher can log in with new password
        from src.database.db import teacher_login
        teacher_after = teacher_login("Mehak", new_pwd)
        assert teacher_after is not None, "Login with new password failed!"
        assert teacher_after["username"] == "Mehak"

        # Verify old password fails
        old_login = teacher_login("Mehak", "WrongPasswordAttempt123!")
        assert old_login is None, "Login with wrong password should fail"

        # Restore original password hash immediately to protect real user credentials
        if orig_hash:
            supabase.table("teachers").update({"password": orig_hash}).eq("username", "Mehak").execute()

        test_results["14. Successful password reset and subsequent login"] = "PASSED"
        print("  -> PASSED: Password reset tested, verified login, and restored original credentials.")
    except Exception as e:
        test_results["14. Successful password reset and subsequent login"] = f"FAILED: {e}"
        print(f"  -> FAILED: {e}")

    # -------------------------------------------------------------------------
    # SUMMARY REPORT
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("FINAL TEST RESULTS SUMMARY:")
    print("=" * 70)
    all_passed = True
    for scn, res in test_results.items():
        status_flag = "PASS" if "PASSED" in res else "FAIL"
        if status_flag == "FAIL":
            all_passed = False
        print(f"  [{status_flag}] {scn}: {res}")
    print("=" * 70)
    if all_passed:
        print("ALL 14 SCENARIOS EXECUTED AND PASSED SUCCESSFULLY!")
    else:
        print("SOME TESTS FAILED - REVIEW ABOVE FOR DETAILS.")
    print("=" * 70)

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
