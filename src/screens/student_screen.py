import streamlit as st

from src.ui.base_layout import style_background_dashboard, style_base_layout

from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from PIL import Image
import numpy as np
from src.pipelines.face_pipeline import predict_attendance, get_face_embeddings, train_classifier
from src.pipelines.voice_pipeline import get_voice_embedding
from src.database.db import get_all_students, create_student, get_student_subjects, get_student_attendance, unenroll_student_to_subject
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
                    st.toast(f'Unenrolled from {sub['name']} successfully!')
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
            # Use strict 0.48 confidence threshold to prevent false matches on strangers
            detected, all_ids, num_faces = predict_attendance(img, confidence_threshold=0.48)

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
        new_name = st.text_input("Enter your full name", placeholder='E.g. Hamza Rizvi', key='reg_student_name')

        st.caption("Capture a clear frontal photo of your face for FaceID recognition:")
        reg_photo = st.camera_input("Take registration photo", key="reg_student_cam")

        st.subheader('Optional : Voice Enrollment')
        st.caption("Enroll your voice for voice-assisted attendance:")

        audio_data = None
        try:
            audio_data = st.audio_input('Record a short phrase (e.g. "I am present, my name is...")', key='reg_student_voice')
        except Exception:
            st.error('Microphone access failed!')

        st.divider()

        btn_c1, btn_c2 = st.columns(2)

        with btn_c1:
            if st.button('Create Account', type='primary', width='stretch', key='btn_submit_student_reg'):
                if not new_name.strip():
                    st.warning('Please enter your full name!')
                elif not reg_photo:
                    st.warning('Please take a photo of your face to complete registration!')
                else:
                    with st.spinner('Creating your facial profile...'):
                        img = np.array(Image.open(reg_photo))
                        encodings = get_face_embeddings(img)
                        if encodings:
                            face_emb = encodings[0].tolist()

                            voice_emb = None
                            if audio_data:
                                voice_emb = get_voice_embedding(audio_data.read())

                            response_data = create_student(new_name.strip(), face_embedding=face_emb, voice_embedding=voice_emb)

                            if response_data:
                                train_classifier()
                                st.session_state.is_logged_in = True
                                st.session_state.user_role = 'student'
                                st.session_state.student_data = response_data[0]
                                st.toast(f'Profile Created! Hi {new_name}!')
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error('Could not capture your facial features. Please ensure your face is well lit and centered.')

        with btn_c2:
            if st.button('Already Registered? Login Instead', width='stretch', key='btn_back_to_login_tab'):
                st.session_state.student_mode = 'login'
                st.rerun()