import streamlit as st
import time
from datetime import datetime
import pandas as pd
import numpy as np

from src.ui.base_layout import style_background_dashboard, style_base_layout
from src.components.header import header_dashboard
from src.components.footer import footer_dashboard
from src.components.subject_card import subject_card
from src.database.db import (
    check_teacher_exists,
    create_teacher,
    teacher_login,
    get_teacher_subjects,
    get_attendance_for_teacher,
    request_password_reset,
    verify_password_reset_token,
    reset_teacher_password,
    validate_password_strength
)
from src.database.config import supabase
from src.components.dialog_create_subject import create_subject_dialog
from src.components.dialog_share_subject import share_subject_dialog
from src.components.dialog_add_photo import add_photos_dialog
from src.components.dialog_attendance_results import attendance_result_dialog
from src.components.dialog_voice_attendance import voice_attendance_dialog
from src.pipelines.face_pipeline import predict_attendance
from src.pipelines.image_utils import safe_cleanup_memory


def teacher_screen():
    style_background_dashboard()
    style_base_layout()

    # Check query params for reset_token
    token_param = st.query_params.get('reset_token')
    if token_param and not st.session_state.get('teacher_data'):
        st.session_state['teacher_login_type'] = 'reset_password'
        st.session_state['active_reset_token'] = token_param

    login_type = st.session_state.get('teacher_login_type', 'login')

    if "teacher_data" in st.session_state:
        teacher_dashboard()
    elif login_type == "forgot_password":
        teacher_screen_forgot_password()
    elif login_type == "reset_password":
        teacher_screen_reset_password()
    elif login_type == "register":
        teacher_screen_register()
    else:
        teacher_screen_login()


def teacher_dashboard():
    teacher_data = st.session_state.teacher_data
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        st.subheader(f"""Welcome, {teacher_data['name']} """)
        if st.button("Logout", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['is_logged_in'] = False
            del st.session_state.teacher_data 
            st.rerun()

    st.space()

    if "current_teacher_tab" not in st.session_state:
        st.session_state.current_teacher_tab = 'take_attendance'
    tab1, tab2, tab3 = st.columns(3)

    with tab1:
        type1 = "primary" if st.session_state.current_teacher_tab == 'take_attendance' else "tertiary"
        if st.button('Take Attendance', type=type1, width='stretch', icon=':material/ar_on_you:'):
            st.session_state.current_teacher_tab = 'take_attendance'
            st.rerun()

    with tab2:
        type2 = "primary" if st.session_state.current_teacher_tab == 'manage_subjects' else "tertiary"
        if st.button('Manage Subjects', type=type2, width='stretch', icon=':material/book_ribbon:'):
            st.session_state.current_teacher_tab = 'manage_subjects'
            st.rerun()

    with tab3:
        type3 = "primary" if st.session_state.current_teacher_tab == 'attendance_records' else "tertiary"
        if st.button('Attendance Records', type=type3, width='stretch', icon=':material/cards_stack:'):
            st.session_state.current_teacher_tab = 'attendance_records'
            st.rerun()

    st.divider()

    if st.session_state.current_teacher_tab == "take_attendance":
        teacher_tab_take_attendance()
    if st.session_state.current_teacher_tab == "manage_subjects":
        teacher_tab_manage_subjects()
    if st.session_state.current_teacher_tab == "attendance_records":
        teacher_tab_attendance_records()

    footer_dashboard()


def teacher_tab_take_attendance():
    teacher_id = st.session_state.teacher_data['teacher_id']
    st.header('Take AI Attendance')

    if 'attendance_images' not in st.session_state:
        st.session_state.attendance_images = []

    subjects = get_teacher_subjects(teacher_id)

    if not subjects:
        st.warning('You havent created any subjects yet! Please create one to begin!')
        return
    
    subject_options = {f"{s['name']} - {s['subject_code']}": s['subject_id'] for s in subjects}

    col1, col2 = st.columns([3, 1], vertical_alignment='bottom')

    with col1:
        selected_subject_label = st.selectbox('Select Subject', options=list(subject_options.keys()))

    with col2:
        if st.button('Add Photos', type='primary', icon=':material/photo_prints:', width='stretch'):
            add_photos_dialog()

    selected_subject_id = subject_options[selected_subject_label]

    st.divider()

    if st.session_state.attendance_images:
        st.header(f'Added Photos ({len(st.session_state.attendance_images)})')
        gallery_cols = st.columns(4)

        for idx, img in enumerate(st.session_state.attendance_images):
            with gallery_cols[idx % 4]:
                st.image(img, width='stretch', caption=f'Photo {idx+1}')

    has_photos = bool(st.session_state.attendance_images)
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button('Clear all photos', width='stretch', type='tertiary', icon=':material/delete:', disabled=not has_photos):
            st.session_state.attendance_images = []
            st.session_state.processed_photo_signatures = set()
            safe_cleanup_memory()
            st.rerun()

    with c2:
        if st.button('Run Face Analysis', width='stretch', type='secondary', icon=':material/analytics:', disabled=not has_photos):
            total_photos = len(st.session_state.attendance_images)
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            all_detected_ids = {}
            photo_face_counts = []
            failed_photos = []

            for idx, img in enumerate(st.session_state.attendance_images):
                progress_val = float(idx) / float(total_photos)
                progress_bar.progress(progress_val)
                status_text.info(f"Scanning Photograph {idx + 1} of {total_photos}...")

                try:
                    img_np = np.array(img.convert('RGB'))
                    detected, _, num_faces = predict_attendance(img_np)
                    photo_face_counts.append((idx + 1, num_faces))

                    if detected:
                        for sid in detected.keys():
                            student_id = int(sid)
                            all_detected_ids.setdefault(student_id, []).append(f"Photo {idx+1}")
                except Exception as e:
                    failed_photos.append((idx + 1, str(e)))
                finally:
                    if 'img_np' in locals():
                        del img_np
                    safe_cleanup_memory()

            progress_bar.progress(1.0)
            total_faces_found = sum(count for _, count in photo_face_counts)
            status_text.success(
                f"Face scan complete! Scanned {total_photos} photo(s). Detected {total_faces_found} total face(s)."
            )

            # Display per-photo face counts
            for p_num, count in photo_face_counts:
                st.caption(f"Photo {p_num}: {count} face(s) detected")

            if failed_photos:
                st.warning(f"Note: {len(failed_photos)} photo(s) had errors and were skipped, but successful results are preserved.")

            enrolled_res = supabase.table('subject_students').select("*, students(*)").eq('subject_id', selected_subject_id).execute()
            enrolled_students = enrolled_res.data

            if not enrolled_students:
                st.warning('No students enrolled in this course')
            else:
                results, attendance_to_log = [], []
                current_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                for node in enrolled_students:
                    student = node['students']
                    sources = all_detected_ids.get(int(student['student_id']), [])
                    is_present = len(sources) > 0

                    results.append({
                        "Name": student['name'],
                        "ID": student['student_id'],
                        "Source": ", ".join(sources) if is_present else "-",
                        "Status": "✅ Present" if is_present else "❌ Absent"
                    })

                    attendance_to_log.append({
                        'student_id': student['student_id'],
                        'subject_id': selected_subject_id,
                        'timestamp': current_timestamp,
                        'is_present': bool(is_present)
                    })

                attendance_result_dialog(pd.DataFrame(results), attendance_to_log)

    with c3:
        if st.button('Use Voice Attendance', type='primary', width='stretch', icon=':material/mic:'):
            voice_attendance_dialog(selected_subject_id)


def teacher_tab_manage_subjects():
    teacher_id = st.session_state.teacher_data['teacher_id']
    col1, col2 = st.columns(2)
    with col1:
        st.header('Manage Subjects', width='stretch')

    with col2:
        if st.button('Create New Subject', width='stretch'):
            create_subject_dialog(teacher_id)

    subjects = get_teacher_subjects(teacher_id)
    if subjects:
        for sub in subjects:
            stats = [
                ("🫂", "Students", sub['total_students']),
                ("🕰️", "Classes", sub['total_classes']),
            ]
            def share_btn():
                if st.button(f"Share Code: {sub['name']}", key=f"share_{sub['subject_code']}", icon=":material/share:"):
                    share_subject_dialog(sub['name'], sub['subject_code'])
                st.space()

            subject_card(
                name=sub['name'],
                code=sub['subject_code'],
                section=sub['section'],
                stats=stats,
                footer_callback=share_btn
            )
    else:
        st.info("NO SUBJECTS FOUND. CREATE ONE ABOVE")


def teacher_tab_attendance_records():
    st.header('Attendance Records')
    teacher_id = st.session_state.teacher_data['teacher_id']
    records = get_attendance_for_teacher(teacher_id)

    if not records:
        return
    
    data = []
    for r in records:
        ts = r.get('timestamp')
        data.append({
            "ts_group": ts.split(".")[0] if ts else None,
            "Time": datetime.fromisoformat(ts).strftime("%Y-%m-%d %I:%M %p") if ts else "N/A",
            "Subject": r['subjects']['name'],
            "Subject Code": r['subjects']['subject_code'],
            "is_present": bool(r.get('is_present', False))
        })

    df = pd.DataFrame(data)

    summary = (
        df.groupby(['ts_group', 'Time', 'Subject', 'Subject Code'])
        .agg(
            Present_Count=('is_present', 'sum'),
            Total_Count=('is_present', 'count')
        ).reset_index()
    )

    summary['Attendance Stats'] = (
        "✅ " + summary['Present_Count'].astype(str) + " /"
        + summary['Total_Count'].astype(str) + ' Students'
    )

    display_df = (
        summary.sort_values(by='ts_group', ascending=False)
        [['Time', 'Subject', 'Subject Code', 'Attendance Stats']]
    )
    
    st.dataframe(display_df, width='stretch', hide_index=True)


def login_teacher(username, password):
    if not username or not password:
        return False
    
    teacher = teacher_login(username, password)
    if teacher:
        st.session_state.user_role = 'teacher'
        st.session_state.teacher_data = teacher
        st.session_state.is_logged_in = True
        return True
    
    return False


def teacher_screen_login():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    st.header('Login using password', text_alignment='center')
    st.space()
    st.space()

    teacher_username = st.text_input(
        "Enter username or email",
        placeholder="e.g. ananyaroy or ananyaroy@school.edu",
        key="teacher_login_identifier"
    )

    teacher_pass = st.text_input(
        "Enter password",
        type='password',
        placeholder="Enter password",
        key="teacher_login_pass"
    )

    # Forgot Password Link
    c_forgot, _ = st.columns([1, 1])
    with c_forgot:
        if st.button("Forgot Password?", type='tertiary', key='btn_forgot_pass_link'):
            st.session_state.teacher_login_type = 'forgot_password'
            st.rerun()

    st.divider()

    btnc1, btnc2 = st.columns(2)

    with btnc1:
        if st.button('Login', icon=':material/passkey:', shortcut='control+enter', width='stretch'):
            if login_teacher(teacher_username, teacher_pass):
                st.toast("Welcome back!", icon="👋")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Invalid username and password combo")

    with btnc2:
        if st.button('Register Instead', type="primary", icon=':material/passkey:', width='stretch'):
            st.session_state.teacher_login_type = 'register'
            st.rerun()

    footer_dashboard()


def teacher_screen_forgot_password():
    """Responsive Forgot Password Request Screen"""
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Back to Login", type='secondary', key='backtologin_forgot', shortcut="control+backspace"):
            st.session_state.teacher_login_type = 'login'
            st.rerun()

    st.header('Forgot Password', text_alignment='center')
    st.space()

    st.markdown(
        "<p style='text-align:center;'>Enter your registered email address or username below. "
        "We will generate a secure, single-use password reset link for your account.</p>",
        unsafe_allow_html=True
    )
    st.space()

    reset_identifier = st.text_input(
        "Registered Email Address or Username",
        placeholder="e.g. ananyaroy@school.edu or ananyaroy",
        key="forgot_pwd_identifier"
    )

    st.divider()

    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("Send Reset Link", type="primary", icon=':material/mail:', width='stretch'):
            if not reset_identifier.strip():
                st.warning("Please enter your registered email address or username.")
            else:
                with st.spinner("Sending reset link..."):
                    success, msg, raw_token, email_status = request_password_reset(reset_identifier)
                    st.success("Reset link was sent to your email. Please check your inbox!")

    with btn_col2:
        if st.button("Back to Login", width='stretch', key="cancel_forgot"):
            st.session_state.teacher_login_type = 'login'
            st.rerun()

    footer_dashboard()


def teacher_screen_reset_password():
    """Password Reset Screen: Validates single-use token and sets new password."""
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Back to Login", type='secondary', key='backtologin_reset', shortcut="control+backspace"):
            st.session_state.teacher_login_type = 'login'
            st.session_state.active_reset_token = None
            if 'reset_token' in st.query_params:
                del st.query_params['reset_token']
            st.rerun()

    st.header('Reset Your Password', text_alignment='center')
    st.space()

    # Retrieve reset token from session state or URL query parameters
    raw_token = st.session_state.get('active_reset_token') or st.query_params.get('reset_token')

    if not raw_token:
        st.error("No password reset token was provided. Please request a new password reset link.")
        if st.button("Request Password Reset", type="primary", width='stretch'):
            st.session_state.teacher_login_type = 'forgot_password'
            st.rerun()
        footer_dashboard()
        return

    # Verify recovery token
    is_valid, teacher_id, error_msg = verify_password_reset_token(raw_token)

    if not is_valid:
        st.error(f"Cannot reset password: {error_msg}")
        st.info("Password reset links expire in 15 minutes and can only be used once.")
        if st.button("Request New Reset Link", type="primary", width='stretch'):
            st.session_state.teacher_login_type = 'forgot_password'
            st.rerun()
        footer_dashboard()
        return

    st.markdown(
        "<p style='text-align:center;'>Your identity has been verified. "
        "Please choose a strong new password for your account.</p>",
        unsafe_allow_html=True
    )

    # Password visibility toggle
    show_new_pass = st.checkbox("Show passwords", value=False, key="toggle_reset_passwords")
    input_field_type = "default" if show_new_pass else "password"

    new_password = st.text_input(
        "New Password",
        type=input_field_type,
        placeholder="Enter at least 8 characters (letters & numbers)",
        key="reset_new_pwd"
    )

    confirm_password = st.text_input(
        "Confirm New Password",
        type=input_field_type,
        placeholder="Re-enter new password",
        key="reset_confirm_pwd"
    )

    # Live password strength hints
    if new_password:
        strong, reason = validate_password_strength(new_password)
        if strong:
            st.caption("✅ Password strength: Strong")
        else:
            st.caption(f"⚠️ {reason}")

    st.divider()

    btn_c1, btn_c2 = st.columns(2)

    with btn_c1:
        if st.button("Update Password", type="primary", width='stretch', key="submit_reset_pwd"):
            if not new_password or not confirm_password:
                st.error("Please enter and confirm your new password.")
            elif new_password != confirm_password:
                st.error("Passwords do not match. Please re-enter matching passwords.")
            else:
                strong, reason = validate_password_strength(new_password)
                if not strong:
                    st.error(reason)
                else:
                    success, update_msg = reset_teacher_password(raw_token, new_password)
                    if success:
                        st.success(update_msg)
                        # Clean up token
                        st.session_state.active_reset_token = None
                        if 'reset_token' in st.query_params:
                            del st.query_params['reset_token']
                        time.sleep(2)
                        st.session_state.teacher_login_type = 'login'
                        st.rerun()
                    else:
                        st.error(update_msg)

    with btn_c2:
        if st.button("Cancel & Return to Login", width='stretch', key="cancel_reset_pwd"):
            st.session_state.teacher_login_type = 'login'
            st.session_state.active_reset_token = None
            if 'reset_token' in st.query_params:
                del st.query_params['reset_token']
            st.rerun()

    footer_dashboard()


def register_teacher(teacher_username, teacher_name, teacher_pass, teacher_pass_confirm, teacher_email=None):
    if not teacher_username or not teacher_name or not teacher_pass:
        return False, "All Fields are required!"
    if check_teacher_exists(teacher_username):
        return False, "Username already taken"
    if teacher_pass != teacher_pass_confirm:
        return False, "Password doesn't match"

    strong, reason = validate_password_strength(teacher_pass)
    if not strong:
        return False, reason
    
    try:
        create_teacher(teacher_username, teacher_pass, teacher_name, email=teacher_email)
        return True, "Successfully Created! Login Now"
    except Exception:
        return False, "Unexpected Error!"


def teacher_screen_register():
    c1, c2 = st.columns(2, vertical_alignment='center', gap='xxlarge')
    with c1:
        header_dashboard()
    with c2:
        if st.button("Go back to Home", type='secondary', key='loginbackbtn', shortcut="control+backspace"):
            st.session_state['login_type'] = None
            st.rerun()

    st.header('Register your teacher profile')
    st.space()
    st.space()

    teacher_username = st.text_input("Enter username", placeholder='ananyaroy')
    teacher_name = st.text_input("Enter name", placeholder='Ananya Roy')
    teacher_email = st.text_input("Enter email (Optional, for password recovery)", placeholder='ananya.roy@school.edu')

    show_reg_pass = st.checkbox("Show passwords", value=False, key="toggle_reg_passwords")
    reg_field_type = "default" if show_reg_pass else "password"

    teacher_pass = st.text_input("Enter password", type=reg_field_type, placeholder="Minimum 8 characters (letters & numbers)")
    teacher_pass_confirm = st.text_input("Confirm your password", type=reg_field_type, placeholder="Re-enter password")

    if teacher_pass:
        strong, reason = validate_password_strength(teacher_pass)
        if strong:
            st.caption("✅ Password strength: Strong")
        else:
            st.caption(f"⚠️ {reason}")

    st.divider()

    btnc1, btnc2 = st.columns(2)

    with btnc1:
        if st.button('Register now', icon=':material/passkey:', shortcut='control+enter', width='stretch'):
            success, message = register_teacher(
                teacher_username,
                teacher_name,
                teacher_pass,
                teacher_pass_confirm,
                teacher_email=teacher_email
            )
            if success:
                st.success(message)
                time.sleep(2)
                st.session_state.teacher_login_type = "login"
                st.rerun()
            else:
                st.error(message)

    with btnc2:
        if st.button('Login Instead', type="primary", icon=':material/passkey:', width='stretch'):
            st.session_state.teacher_login_type = 'login'
            st.rerun()

    footer_dashboard()
