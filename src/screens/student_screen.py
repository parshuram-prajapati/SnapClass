import streamlit as st
from src.pipelines.face_detector import detect_faces
from src.pipelines.face_embedder import get_face_embedding

from src.database.db import save_face_embeddings

from src.ui.base_layout import style_background_dashboard, style_base_layout

from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from PIL import Image
import numpy as np
from src.pipelines.face_pipeline import (
    predict_attendance,
    get_face_embeddings,
    train_classifier
)
from src.pipelines.voice_pipeline import get_voice_embedding
from src.database.db import (
    get_all_students,
    create_student,
    get_student_subjects,
    get_student_attendance,
    unenroll_student_to_subject,
    normalize_student_usn
)
import time

from src.components.dialog_enroll import enroll_dialog
from src.components.subject_card import subject_card

def student_dashboard():
    student_data = st.session_state.student_data
    student_id = student_data['student_id']
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"""Welcome, {student_data['name']} """)
        if st.button("Logout", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['is_logged_in'] = False
            del st.session_state.student_data 
            st.rerun()


    st.space()

    c1, c2 =st.columns(2)
    with c1:
        st.header('Your Enrolled Subjects')
    with c2:
        if st.button('Enroll in Subject', type='primary', width='stretch'):
            enroll_dialog()


    st.divider()


    with st.spinner('Loading your enrolled subjects..'):
        subjects = get_student_subjects(student_id)
        logs = get_student_attendance(student_id)

    stats_map = {}

    for log in logs:
        sid = log['subject_id']

        if sid not in stats_map:
            stats_map[sid] = {"total":0, "attended": 0}

        stats_map[sid]['total'] +=1

        if log.get('is_present'):
            stats_map[sid]['attended'] += 1


    cols = st.columns(2)
    for i, sub_node in enumerate(subjects):
        sub = sub_node['subjects']
        sid = sub['subject_id']


        stats = stats_map.get(sid,{"total":0, "attended": 0} )
        def unenroll_button():
                if st.button("Unenroll from tihs course", type='tertiary', width='stretch', icon=':material/delete_forever:'):
                    unenroll_student_to_subject(student_id, sid)
                    st.toast(f"Unenrolled from {sub['name']} successfully!")
                    st.rerun()

        with cols[i % 2]:

            subject_card(
                name = sub['name'],
                code =sub['subject_code'],
                section = sub['section'],
                stats = [
                    ('📅', 'Total', stats['total']),
                    ('✅', 'Attended', stats['attended']),
                ],
                footer_callback=unenroll_button
            )
    footer_dashboard()


def student_screen():
    style_background_dashboard()
    style_base_layout()

    if "student_data" in st.session_state:
        student_dashboard()
        return
    
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    if 'student_mode' not in st.session_state:
        st.session_state.student_mode = 'login'

    t1, t2 = st.columns(2)
    with t1:
        type_login = "primary" if st.session_state.student_mode == 'login' else 'tertiary'
        if st.button('Login using FaceID', type=type_login, width='stretch', key='tab_student_login'):
            st.session_state.student_mode = 'login'
            st.rerun()
    with t2:
        type_reg = "primary" if st.session_state.student_mode == 'register' else 'tertiary'
        if st.button('Register New Student', type=type_reg, width='stretch', key='tab_student_register'):
            st.session_state.student_mode = 'register'
            st.rerun()

    st.space()

    if st.session_state.student_mode == 'login':
        student_screen_login()
    else:
        student_screen_register()
        
    footer_dashboard()


def student_screen_login():
    st.header('Login using FaceID', text_alignment='center')
    st.space()
    
    photo_source = st.camera_input("Position your face in the center", key="student_login_cam")

    if photo_source:
        img = np.array(Image.open(photo_source))

        with st.spinner('AI is verifying your identity...'):
            # Use strict 0.55 confidence threshold to prevent false matches on strangers
            detected, all_ids, num_faces = predict_attendance(img, confidence_threshold=0.55)

            if num_faces == 0:
                st.warning('No face detected. Please position your face clearly in the camera.')
            elif num_faces > 1:
                st.warning('Multiple faces found. Please make sure only one person is in the frame.')
            else:
                if detected:
                    student_id = list(detected.keys())[0]
                    all_students = get_all_students()
                    student = next((s for s in all_students if s['student_id'] == student_id), None)

                    if student:
                        st.session_state.is_logged_in = True
                        st.session_state.user_role = 'student'
                        st.session_state.student_data = student
                        st.toast(f'Welcome Back {student["name"]}')
                        time.sleep(1)
                        st.rerun()
                else:
                    st.info('Face not recognized in registered student database.')
                    st.write("If you are a new student, click below to register your profile:")
                    if st.button('Register New Profile', type='primary', width='stretch', key='btn_switch_to_reg'):
                        st.session_state.student_mode = 'register'
                        st.rerun()




def student_screen_register():
    st.header('Register New Student Profile', text_alignment='center')
    st.space()

    with st.container(border=True):

        new_name = st.text_input(
            "Enter your full name",
            placeholder="E.g. Hamza Rizvi",
            key="reg_student_name"
        )

        def uppercase_usn_input():
            st.session_state["reg_student_usn"] = (
                st.session_state.get("reg_student_usn", "").strip().upper()
            )

        new_usn = st.text_input(
            "Enter your USN (University Seat Number)",
            placeholder="E.g. 2BL24CI028",
            key="reg_student_usn",
            on_change=uppercase_usn_input
        )

        st.subheader("FaceID Enrollment")
        st.caption(
            "Capture exactly 4 clear photos of the same student. "
            "Use different angles and lighting conditions."
        )

        # Four camera capture fields
        photo_labels = [
            "Photo 1 - Front face",
            "Photo 2 - Slightly left",
            "Photo 3 - Slightly right",
            "Photo 4 - Different angle"
        ]

        captured_photos = []

        for row in range(2):
            cols = st.columns(2)

            for col_index in range(2):
                photo_index = row * 2 + col_index

                with cols[col_index]:
                    st.markdown(f"**{photo_labels[photo_index]}**")

                    photo = st.camera_input(
                        f"Capture photo {photo_index + 1}",
                        key=f"reg_camera_{photo_index + 1}"
                    )

                    captured_photos.append(photo)

                    if photo:
                        st.success("Photo captured")

        st.caption("All four photos must contain exactly one face.")

        st.divider()

        # Optional voice enrollment
        st.subheader("Optional: Voice Enrollment")
        st.caption("Enroll your voice for voice-assisted attendance.")

        audio_data = None

        try:
            audio_data = st.audio_input(
                'Record a short phrase (e.g. "I am present, my name is...")',
                key="reg_student_voice"
            )
        except Exception:
            st.error("Microphone access failed!")

        st.divider()

        btn_c1, btn_c2 = st.columns(2)

        with btn_c1:
            submit = st.button(
                "Create Account",
                type="primary",
                width="stretch",
                key="btn_submit_student_reg"
            )

        with btn_c2:
            back = st.button(
                "Already Registered? Login Instead",
                width="stretch",
                key="btn_back_to_login_tab"
            )

        if back:
            st.session_state.student_mode = "login"
            st.rerun()

        try:
            normalized_usn = normalize_student_usn(new_usn)
            usn_error = None
        except ValueError as exc:
            normalized_usn = ""
            usn_error = str(exc)

        if submit:

            if not new_name.strip():
                st.warning("Please enter your full name.")

            elif usn_error:
                st.error(usn_error)

            elif any(photo is None for photo in captured_photos):
                st.warning("Please capture all 4 face photos.")

            else:
                embeddings = []
                rejected_photos = []

                with st.spinner("Processing all 4 photos with YuNet and SFace..."):

                    for index, photo in enumerate(captured_photos, start=1):

                        try:
                            img = np.array(
                                Image.open(photo).convert("RGB")
                            )

                            # Detect faces
                            faces = detect_faces(img)

                            if len(faces) == 0:
                                rejected_photos.append(
                                    f"Photo {index}: No face detected."
                                )
                                continue

                            if len(faces) > 1:
                                rejected_photos.append(
                                    f"Photo {index}: Multiple faces detected."
                                )
                                continue

                            # Generate SFace embedding
                            embedding = get_face_embedding(
                                img,
                                faces[0]
                            )

                            embedding = np.asarray(
                                embedding,
                                dtype=np.float32
                            ).reshape(-1)

                            if embedding.shape != (128,):
                                rejected_photos.append(
                                    f"Photo {index}: Invalid embedding."
                                )
                                continue

                            norm = np.linalg.norm(embedding)

                            if not np.isfinite(norm) or norm == 0:
                                rejected_photos.append(
                                    f"Photo {index}: Invalid face embedding."
                                )
                                continue

                            embeddings.append(
                                (embedding / norm).tolist()
                            )

                        except Exception as exc:
                            rejected_photos.append(
                                f"Photo {index}: Processing failed ({exc})"
                            )

                # Require all four valid photos
                if len(embeddings) != 4:

                    st.error(
                        f"Only {len(embeddings)} of 4 photos were valid. "
                        "Please capture all four photos again."
                    )

                    for reason in rejected_photos:
                        st.warning(reason)

                else:

                    try:
                        # Optional voice embedding
                        voice_emb = None

                        if audio_data:
                            voice_emb = get_voice_embedding(
                                audio_data.getvalue()
                            )

                        # Create student account
                        response_data = create_student(
                            new_name.strip(),
                            usn=normalized_usn,
                            face_embedding=None,
                            voice_embedding=voice_emb
                        )

                        if not response_data:
                            st.error("Student account creation failed.")

                        else:
                            student = response_data[0]
                            student_id = student["student_id"]

                            # Save all four SFace embeddings
                            save_face_embeddings(
                                student_id,
                                embeddings
                            )

                            # Refresh recognition database
                            train_classifier()

                            st.success(
                                "Student registered successfully!\n\n"
                                f"Name: {new_name.strip()}\n\n"
                                f"USN: {normalized_usn}"
                            )

                            st.session_state.is_logged_in = True
                            st.session_state.user_role = "student"
                            st.session_state.student_data = student

                            st.toast(
                                f"Profile created! Welcome {new_name}!"
                            )

                            time.sleep(1)
                            st.rerun()

                    except Exception as exc:
                        st.error(
                            "Registration could not be completed. "
                            f"Error: {exc}"
                        )
