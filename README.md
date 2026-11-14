# PUMO TECHNOVATION EXAM PORTAL – POONAMALLEE

**Official Branding**: PUMO TECHNOVATION EXAM PORTAL  
**Branch**: POONAMALLEE  
**Developed By**: **SARATHY & THIRUMAL**  
**Copyright**: © 2026 PUMO TECHNOVATION. All Rights Reserved.  
**Theme**: Professional Blue  

---

## 📌 Project Overview
A complete, secure, professional, and scalable Online Examination Management Platform designed specifically for **PUMO TECHNOVATION, POONAMALLEE**. 

Built with **Python Django 5.1**, **MySQL 8**, **Bootstrap 5**, **PyMuPDF**, and **Client-Side AI Proctoring**, this platform provides complete role-separated workflows for:
1. **Super Admin**: Platform overview, trainers & students management, courses & batches, audit logs.
2. **Trainer**: Manual Question Bank, PDF Question paper upload & extraction, review & approval, exam creation, live session monitoring, AI proctoring alerts review, and result publishing.
3. **Student**: Distraction-free exam room, countdown timer, question palette, auto-saving, webcam AI proctoring detection, and personal published results.

---

## 🚀 Quick Start Guide (How to Run the Project)

### 1. Prerequisites
- **Python 3.10+** (tested and verified on Python 3.10.5)
- **MySQL Server 8.x** running on `localhost:3306`

---

### 2. Activate the Virtual Environment
Open a terminal (PowerShell or Command Prompt) in the project root directory:

```powershell
# Navigate to the project directory
cd e:\PUMO_EXAM_PORTAL

# Activate the virtual environment
.\venv\Scripts\Activate.ps1
```

*(If you ever need to recreate or install dependencies in a new environment)*:
```powershell
pip install -r requirements.txt
```

---

### 3. Configure Database (`.env`)
The database configuration is automatically loaded from the `.env` file:

```env
SECRET_KEY=pumo-secret-key-exam-portal-poonamallee-sarathy-thirumal-2026-secure
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,::1

DB_ENGINE=django.db.backends.mysql
DB_NAME=pumo_exam_portal
DB_USER=root
DB_PASSWORD=Sarathy@123
DB_HOST=127.0.0.1
DB_PORT=3306
```

---

### 4. Run Database Migrations
Apply the database schema to your MySQL database:

```powershell
python manage.py makemigrations
python manage.py migrate
```

---

### 5. Seed Demo Accounts & Sample Data (One-Click Setup)
Populate the platform with initial users, courses, batches, sample questions, and a ready-to-attend exam:

```powershell
python manage.py seed_data
```

---

### 6. Start the Development Server
Launch the Django server:

```powershell
python manage.py runserver
```

Now open your web browser and visit:
👉 **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## 🔑 Demo Login Credentials

The single unified login system automatically directs users to their respective dashboard based on their role:

| Role | Username | Password | Dashboard Access |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin` | `Sarathy@123` | Full admin management, metrics, courses, trainers, students, audits |
| **Trainer** | `trainer` | `Trainer@123` | Question bank, PDF import, exam scheduler, proctoring alerts, results |
| **Student** | `student` | `Student@123` | Assigned exams, live exam room, countdown timer, personal scores |

---

## 🌟 Core System Modules

### 1. Unified Authentication & Role Redirection
- Single secure login page with PUMO Technovation branding.
- Server-side role checks with `@role_required` and `RoleRequiredMixin`.
- Students can never access Trainer or Admin views or APIs.
- Trainers cannot access Super Admin-only configurations.

### 2. Super Admin Dashboard
- Live platform statistics (Students, Trainers, Courses, Batches, Exams).
- Manage Trainers (create, edit, toggle status).
- Manage Students (create, assign to batches, view history).
- Course & Batch organization.
- Audit activity logs tracking key portal actions.

### 3. Trainer Dashboard & Question Bank
- **Manual Question Bank**: Create Single MCQ, Multiple Select, Coding, and Practical questions with explanation and marks.
- **PDF Question Paper Import**: Upload PDF questions, extract text via PyMuPDF/pdfplumber, review questions in an editable approval table, select correct answers, and approve into Question Bank.
- **Exam Management**: Schedule exams, assign specific batches or students, configure duration, pass marks, and enable AI proctoring.
- **Live Monitoring & AI Proctoring Review**: Inspect proctoring alerts (face absence, multi-face detection, tab switching) flagged during student sessions.
- **Result Evaluation**: Automatically compute MCQ scores, review submissions, and publish results.

### 4. Student Portal & Distraction-Free Exam Room
- Clear view of assigned, upcoming, and completed examinations.
- Exam room with:
  - Server-synchronized countdown timer.
  - Interactive question navigation palette (Answered, Unanswered, Marked for Review).
  - Background auto-saving of answers.
  - Client-side AI webcam proctoring (monitors face presence, multiple faces, tab switching, and fullscreen status).
  - Auto-submission on timer expiry.
- Personal score card showing marks, percentage, pass/fail status, and trainer feedback.

---

## 📁 Clean & Maintainable Architecture

```text
PUMO_EXAM_PORTAL/
├── accounts/               # Custom User model, authentication, login/logout, role decorators
├── portal/                 # Courses, Batches, Student/Trainer profiles, Audit logs
├── exams/                  # Question Bank, PDF extraction, Exam Room, AI proctoring, Results
├── config/                 # Project settings, URLs, WSGI
├── templates/
│   ├── base/               # Base templates with Professional Blue styling & mandatory footer
│   ├── authentication/     # PUMO branded login page
│   ├── admin_portal/       # Super Admin dashboard and management screens
│   ├── trainer/            # Trainer dashboard, question bank, PDF import, exam monitor
│   └── student/            # Student dashboard, exam taking room, results
├── static/
│   ├── css/                # Professional Blue theme CSS
│   └── js/                 # Exam timer, auto-save, AI webcam proctoring script
├── media/                  # Uploaded PDF question papers and practical submissions
├── .env                    # Active local environment variables
├── requirements.txt        # Python package dependencies
├── manage.py               # Django management script
└── README.md               # Project documentation & execution guide
```

---

## 🏷️ Mandatory Developer Credits & Footer

Every page on this platform features the required corporate footer:

```
PUMO TECHNOVATION EXAM PORTAL – POONAMALLEE
Developed By SARATHY & THIRUMAL
© 2026 PUMO TECHNOVATION. All Rights Reserved.
```
