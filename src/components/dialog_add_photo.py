import streamlit as st
from PIL import Image
from src.pipelines.image_utils import (
    validate_image_file,
    process_and_optimize_image,
    safe_cleanup_memory,
    MAX_UPLOAD_SIZE_MB
)


@st.dialog("Capture or upload photos")
def add_photos_dialog():

    st.write('Add classroom photos to scan for attendance')

    if 'photo_tab' not in st.session_state:
        st.session_state.photo_tab = 'camera'

    if 'attendance_images' not in st.session_state:
        st.session_state.attendance_images = []

    if 'processed_photo_signatures' not in st.session_state:
        st.session_state.processed_photo_signatures = set()

    t1, t2 = st.columns(2)

    with t1:
        type_camera = "primary" if st.session_state.photo_tab == 'camera' else 'tertiary'
        if st.button('Camera', type=type_camera, width='stretch'):
            st.session_state.photo_tab = 'camera'

    with t2:
        type_upload = "primary" if st.session_state.photo_tab == 'upload' else 'tertiary'
        if st.button('Upload photos', type=type_upload, width='stretch'):
            st.session_state.photo_tab = 'upload'

    if st.session_state.photo_tab == 'camera':
        cam_photo = st.camera_input('Take Snapshot', key='dialog_cam')
        if cam_photo:
            sig = f"cam_{cam_photo.size}_{getattr(cam_photo, 'name', '')}"
            if sig not in st.session_state.processed_photo_signatures:
                with st.spinner("Processing captured photo..."):
                    opt_img, err = process_and_optimize_image(cam_photo)
                    if opt_img is not None:
                        st.session_state.attendance_images.append(opt_img)
                        st.session_state.processed_photo_signatures.add(sig)
                        st.toast('Photo Captured and Processed')
                        st.rerun()
                    else:
                        st.error(f"Failed to process snapshot: {err}")

    if st.session_state.photo_tab == 'upload':
        uploaded_files = st.file_uploader(
            f'Choose image files (JPG, JPEG, PNG, max {MAX_UPLOAD_SIZE_MB}MB)',
            type=['jpg', 'png', 'jpeg'],
            accept_multiple_files=True,
            key='dialog_upload'
        )

        if uploaded_files:
            newly_added = 0
            errors = []

            for f in uploaded_files:
                sig = f"{f.name}_{f.size}"
                if sig in st.session_state.processed_photo_signatures:
                    continue  # Already processed, prevent duplicate additions on rerun

                # 1. Validate file format, size, and integrity
                is_valid, val_err = validate_image_file(f, filename=f.name)
                if not is_valid:
                    errors.append(f"{f.name}: {val_err}")
                    continue

                # 2. Decode, handle EXIF orientation, and optimize safely
                opt_img, opt_err = process_and_optimize_image(f)
                if opt_img is not None:
                    st.session_state.attendance_images.append(opt_img)
                    st.session_state.processed_photo_signatures.add(sig)
                    newly_added += 1
                else:
                    errors.append(f"{f.name}: {opt_err}")

            safe_cleanup_memory()

            for err_msg in errors:
                st.error(err_msg)

            if newly_added > 0:
                st.toast(f'{newly_added} Photo(s) Added Successfully')
                st.rerun()

    st.divider()
    if st.button('Done', type='primary', width='stretch'):
        st.rerun()

