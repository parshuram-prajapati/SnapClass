# Smart Attendance App

Smart Attendance App is an AI-assisted attendance management application built with Streamlit. It provides separate student and teacher portals, subject management, face-based student recognition, optional voice attendance, and attendance history stored in Supabase.

## Key Features

- **Teacher accounts:** registration, login, profile management, password reset email, and secure password hashing.
- **Student accounts:** face-based registration and FaceID login.
- **Face attendance:** detect multiple faces in classroom photographs and match them against enrolled student embeddings.
- **Voice attendance:** record classroom audio and compare speakers with registered voice profiles.
- **Subject management:** create subjects, share join codes, and enroll or unenroll students.
- **Attendance records:** view and save present/absent results for each subject.
- **Supabase backend:** store users, subjects, embeddings, and attendance logs.

## How It Works

### Face Recognition

Smart Attendance App uses YuNet for face detection and SFace for face embedding extraction. Registration stores normalized 128-dimensional SFace embeddings for each student. During attendance, faces are detected in submitted photographs and compared with the Supabase embedding database.

The recognition threshold can be changed in `src/pipelines/face_pipeline.py`. The current default match threshold is `0.45`, while student FaceID login uses `0.55`.

### Voice Recognition

Student voice profiles are generated with the Resemblyzer voice encoder. For voice attendance, classroom audio is split into speech segments and each segment is compared with enrolled student voice embeddings.

## Technology Stack

- Python
- Streamlit
- Supabase
- NumPy and Pandas
- OpenCV-compatible YuNet and SFace ONNX models
- Resemblyzer and Librosa
- bcrypt
- SMTP email
- Segno and Pillow

## Project Structure

```text
app.py                         # Streamlit application entry point
src/
  components/                  # Dialogs, headers, footers, and subject UI
  database/                    # Supabase configuration and data operations
  pipelines/                   # Face and voice recognition pipelines
  screens/                     # Home, student, and teacher screens
  services/                    # Email and password-reset services
  ui/                          # Shared layout and theme helpers
models/                        # YuNet and SFace ONNX model files
dataset/                       # Local student image data
tests/                         # Automated tests
supabase_migration.sql         # Password-reset database migration
```

## Prerequisites

- Python 3.10 or newer
- A Supabase project
- A camera for face registration and login
- A microphone for voice enrollment and attendance
- An SMTP account if password-reset emails are required

## Installation

Clone the repository and enter the project directory:

```powershell
git clone <your-repository-url>
cd ai-attendance-project-app-main
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Supabase Setup

Create the required application tables in your Supabase project. The schema must include the following core tables and relationships:

- `teachers`
- `students`
- `subjects`
- `subject_students`
- `attendance_logs`
- `student_face_embeddings`
- `password_resets`

The repository's `supabase_migration.sql` creates the `password_resets` table and adds the teacher `email` column. Run this SQL in the Supabase SQL Editor before enabling password reset:

1. Open **Supabase Dashboard → SQL Editor**.
2. Open `supabase_migration.sql`.
3. Run the migration.

## Configuration

Create `.streamlit/secrets.toml` in the project root. This file is ignored by Git.

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-supabase-anon-key"
SUPABASE_SERVICE_ROLE_KEY = "your-supabase-service-role-key"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USER = "your-email@example.com"
SMTP_PASSWORD = "your-app-password"
SMTP_SENDER_NAME = "Smart Attendance App"
APP_BASE_URL = "http://localhost:8501"
```

Alternatively, the application can read these values from environment variables. Supabase is required for normal application operation. `SUPABASE_SERVICE_ROLE_KEY`, SMTP settings, and `APP_BASE_URL` are optional for selected features, but should be kept server-side and must never be exposed in public client code.

### Supported Environment Variable Names

| Purpose | Names |
|---|---|
| Supabase | `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| SMTP | `SMTP_HOST` or `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER` or `SMTP_EMAIL`, `SMTP_PASSWORD` or `SMTP_PASS`, `SMTP_SENDER_NAME` |
| Application URL | `APP_BASE_URL` |

## Running the Application

Start Streamlit from the project root:

```powershell
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Usage

### Teacher

1. Register or log in from the Teacher portal.
2. Create subjects and share the generated subject code or join link.
3. Open **Take Attendance** and select a subject.
4. Add classroom photographs or record classroom voice audio.
5. Run face or voice analysis.
6. Review the present/absent results and save the attendance log.
7. Use **Attendance Records** to review saved records.

### Student

1. Register a new face profile or log in using FaceID.
2. Enroll in a subject using its subject code or join link.
3. View enrolled subjects and attendance statistics.
4. Unenroll from a subject when needed.

## Password Reset

Teacher password reset works with email addresses or usernames:

1. Run `supabase_migration.sql`.
2. Configure SMTP and `APP_BASE_URL`.
3. Request a password reset from the teacher login screen.
4. Open the emailed link within 15 minutes.
5. Choose a password containing at least eight characters, one letter, and one number.

Reset tokens are hashed before storage and are designed for one-time use.

## Tests

Run the image utility tests with:

```powershell
python -m unittest tests/test_image_utils.py
```

Or run test discovery:

```powershell
python -m unittest discover -s tests
```

## Security and Privacy

- Do not commit `.streamlit/secrets.toml`.
- Keep Supabase service-role credentials and SMTP passwords private.
- Use restricted Supabase RLS policies for production deployments.
- Obtain appropriate consent before storing and processing face or voice data.
- Calibrate recognition thresholds using representative test data before production use.

## Troubleshooting

- **Supabase URL or API key is missing:** verify `.streamlit/secrets.toml` or environment variables.
- **Face not recognized:** improve lighting, face position, image quality, or add more registration samples.
- **No face detected:** confirm the face is visible and not obstructed.
- **Voice profile unavailable:** complete voice enrollment for the student before using voice attendance.
- **Password reset email not sent:** verify SMTP host, port, credentials, and `APP_BASE_URL`.