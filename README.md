# Project Management System (PMS)

A Software Engineering project designed to build a centralized, web-based platform for managing projects, tasks, workflows, sprints, and team collaboration.

---

## 👥 Team 11 Profile

| S.No. | Name | SRN | Role / Module Assignment |
| :---: | :--- | :--- | :--- |
| 1 | **Shivansh Sharma** | PES2UG24CS474 | Repo Setup, Architecture, CI/CD Pipeline |
| 2 | **Shibi R Shetty** | PES2UG24CS467 | Frontend Development & Templates |
| 3 | **Sheetal S Bevinakatti** | PES2UG24CS466 | Requirements Analysis, Testing & QA |
| 4 | **Shivanagouda I Patil** | PES2UG24CS471 | Backend Architecture & Project Management Module |

---

## 🏗️ Architecture Overview

The system architecture follows a layered structure separating presentation, application business logic, and data persistence:

![PMS Architecture](docs/architecture.png)

- **Frontend**: HTML5, CSS, and JavaScript rendered via Django templates.
- **Backend API**: Python / Django framework structured into modular applications (`accounts`, `projects`, `tasks`).
- **Data Store**: Relational database (PostgreSQL in production / SQLite for local development & testing).
- **CI/CD Pipeline**: GitHub Actions for automated linting, migration verification, and test execution.

---

## 📁 Repository Structure

```text
Project-Management-System/
├── README.md               # Project overview, architecture, and team guide
├── .gitignore              # Git ignore rules for Python, Django, and virtual environments
├── backend/                # Django backend application root
│   ├── manage.py           # Django administrative utility
│   ├── requirements.txt    # Python dependencies list
│   ├── config/             # Django settings and main URL configuration
│   ├── accounts/           # User authentication and profile module
│   ├── projects/           # Project management module
│   ├── tasks/              # Task and Kanban management module
│   └── tests/              # Test suite for unit and integration testing
├── docs/                   # Approved documents, specifications, and architecture
│   ├── SRS.pdf             # Software Requirements Specification
│   ├── Software-Test-Plan.pdf # Software Test Plan (STP)
│   ├── architecture.png    # System architecture and data flow diagram
│   ├── Project_Proposal.pdf
│   ├── SASD_Specification.docx
│   ├── Sprint1_Requirements_Analysis.pdf
│   └── Requirements_Matrix.pdf
├── templates/              # Django HTML templates (Frontend)
├── static/                 # Static assets: CSS, JavaScript, and images
└── .github/
    └── workflows/
        └── tests.yml       # GitHub Actions automated test workflow
```

---

## 🚀 Getting Started

### 1. Clone Repository
```bash
git clone https://github.com/Project-Management-System-SE/Project-Management-System-SE.git
cd Project-Management-System-SE
```

### 2. Setup Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r backend/requirements.txt
```
