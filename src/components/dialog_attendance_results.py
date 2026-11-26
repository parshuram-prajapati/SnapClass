import streamlit as st
from src.database.db import create_attendance

def show_attendance_result(df, logs):
    st.write('Please review attendance before confirming.')
    st.dataframe(df, hide_index=True, width='stretch')

    col1, col2 = st.columns(2)

    with col1:
        if st.button('Discard', width='stretch'):
            st.session_state.voice_attendance_results = None
            st.session_state.attendance_images = []
            st.rerun()

    with col2:
        if st.button('Confirm & Save', width='stretch', type='primary'):
            try:
                teacher_data = st.session_state.get("teacher_data") or {}
                teacher_id = teacher_data.get("teacher_id")
                if teacher_id is None:
                    raise PermissionError("Teacher login is required to save attendance.")

                create_attendance(logs, teacher_id)
                st.toast("Attendance taken")
                st.session_state.attendance_images = []
                st.session_state.voice_attendance_results = None
                st.rerun()
            except Exception:
                st.error(
                    "Sync failed. Attendance was not saved; "
                    "check server logs for the database error code."
                )



@st.dialog("Attendance Reports")
def attendance_result_dialog(df, logs):
    show_attendance_result(df, logs)


