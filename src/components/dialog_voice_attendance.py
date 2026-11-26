
import streamlit as st
import pandas as pd

from datetime import datetime, timezone

from src.pipelines.voice_pipeline import process_bulk_audio
from src.database.config import supabase
from src.components.dialog_attendance_results import show_attendance_result


@st.dialog("Voice Attendance")
def voice_attendance_dialog(selected_subject_id):

    st.write(
        "Record classroom audio of students saying "
        "'I am present'. The AI will attempt to recognize enrolled students."
    )

    audio_data = st.audio_input("Record classroom audio")

    if st.button(
        "Analyze Audio",
        width="stretch",
        type="primary"
    ):

        # 1. Validate audio input
        if audio_data is None:
            st.warning("Please record or upload audio before analyzing.")
            st.stop()

        audio_bytes = audio_data.getvalue()

        if not audio_bytes:
            st.warning("The recorded audio is empty. Please record again.")
            st.stop()

        with st.spinner("Processing voice data..."):

            try:
                # 2. Fetch students enrolled in the selected subject
                enrolled_res = (
                    supabase.table("subject_students")
                    .select("*, students(*)")
                    .eq("subject_id", selected_subject_id)
                    .execute()
                )

                enrolled_students = enrolled_res.data or []

                if not enrolled_students:
                    st.warning("No students are enrolled in this subject.")
                    st.stop()

                # 3. Build voice candidate database
                candidates_dict = {}

                for node in enrolled_students:

                    student = node.get("students")

                    if not student:
                        continue

                    student_id = student.get("student_id")
                    voice_embedding = student.get("voice_embedding")

                    if student_id and voice_embedding:
                        candidates_dict[student_id] = voice_embedding

                if not candidates_dict:
                    st.error(
                        "No enrolled students have registered voice profiles."
                    )
                    st.stop()

                # 4. Recognize speakers
                detected_scores = process_bulk_audio(
                    audio_bytes,
                    candidates_dict,
                    threshold=0.65
                )

                if detected_scores is None:
                    detected_scores = {}

                # 5. Generate attendance results
                results = []
                attendance_to_log = []

                current_timestamp = datetime.now(
                    timezone.utc
                ).isoformat()

                for node in enrolled_students:

                    student = node.get("students")

                    if not student:
                        continue

                    student_id = student.get("student_id")
                    student_name = student.get("name", "Unknown")

                    # A student is present only if their ID
                    # was returned by the recognition pipeline.
                    is_present = student_id in detected_scores

                    score = detected_scores.get(student_id)

                    results.append({
                        "Name": student_name,
                        "ID": student_id,
                        "Voice Similarity": (
                            round(float(score), 3)
                            if is_present and score is not None
                            else "-"
                        ),
                        "Status": (
                            "✅ Present"
                            if is_present
                            else "❌ Absent"
                        )
                    })

                    attendance_to_log.append({
                        "student_id": student_id,
                        "subject_id": selected_subject_id,
                        "timestamp": current_timestamp,
                        "is_present": bool(is_present)
                    })

                # 6. Store results in Streamlit session
                st.session_state.voice_attendance_results = (
                    pd.DataFrame(results),
                    attendance_to_log
                )

                st.success(
                    f"Voice analysis completed. "
                    f"{len(detected_scores)} student(s) recognized."
                )

            except Exception:
                st.exception(
                    Exception("Unable to process voice attendance. Check the server logs.")
                )

    # 7. Display attendance results
    if st.session_state.get("voice_attendance_results"):

        st.divider()

        df_results, logs = st.session_state.voice_attendance_results

        show_attendance_result(df_results, logs)
