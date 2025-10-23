import sys
import os
import json
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple, Dict

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTextEdit, QLineEdit, QMessageBox, QHeaderView
)

# ------------------ Data Models ------------------

@dataclass
class DayData:
    sessions: List[Tuple[str, str]] = field(default_factory=list)
    notes: str = ""
    running_start: Optional[datetime] = field(default=None, repr=False)

    def total_hours(self) -> float:
        total = 0.0
        for s_iso, e_iso in self.sessions:
            s = datetime.fromisoformat(s_iso)
            e = datetime.fromisoformat(e_iso)
            total += (e - s).total_seconds() / 3600.0
        if self.running_start:
            total += (datetime.now() - self.running_start).total_seconds() / 3600.0
        return total

    def to_dict(self):
        return {"sessions": self.sessions, "notes": self.notes}

    @staticmethod
    def from_dict(d):
        obj = DayData()
        obj.sessions = d.get("sessions", [])
        obj.notes = d.get("notes", "")
        return obj


@dataclass
class TaskRowData:
    task: str
    subtask: str
    days: List[DayData] = field(default_factory=lambda: [DayData() for _ in range(7)])

    def total_hours(self) -> float:
        return sum(day.total_hours() for day in self.days)

    def to_dict(self):
        return {
            "task": self.task,
            "subtask": self.subtask,
            "days": [d.to_dict() for d in self.days]
        }

    @staticmethod
    def from_dict(d):
        tr = TaskRowData(task=d["task"], subtask=d["subtask"])
        tr.days = [DayData.from_dict(dd) for dd in d.get("days", [])]
        return tr


# ------------------ UI Components ------------------

class DayCell(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.hours = QLineEdit("0.00")
        self.hours.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hours.setReadOnly(True)
        layout.addWidget(self.hours)

        self.toggle_btn = QPushButton("Start")
        self.toggle_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 6px; padding: 4px;")
        layout.addWidget(self.toggle_btn)

        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Notes…")
        layout.addWidget(self.notes)

    def set_hours(self, hrs: float):
        self.hours.setText(f"{hrs:.2f}")

    def set_running(self, running: bool):
        if running:
            self.toggle_btn.setText("Stop")
            self.toggle_btn.setStyleSheet("background-color: #E53935; color: white; border-radius: 6px; padding: 4px;")
        else:
            self.toggle_btn.setText("Start")
            self.toggle_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 6px; padding: 4px;")


class TaskCell(QWidget):
    def __init__(self, task, subtask, delete_callback, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        left = QVBoxLayout()
        lbl_t = QLabel(task if task else "(No Task)")
        lbl_t.setStyleSheet("font-weight: bold; color: #2C3E50;")
        lbl_st = QLabel(subtask if subtask else "(No Subtask)")
        lbl_st.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        left.addWidget(lbl_t)
        left.addWidget(lbl_st)
        layout.addLayout(left)

        del_btn = QPushButton("🗑 Delete")
        del_btn.setStyleSheet("background-color:#B71C1C; color:white; border-radius:6px; padding:4px;")
        del_btn.clicked.connect(delete_callback)
        layout.addWidget(del_btn)


# ------------------ Main App ------------------

class TimesheetApp(QWidget):
    DATA_FILE = "timesheet_data.json"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Weekly Timesheet")
        self.resize(1300, 800)

        self.week_start = self._monday_of(date.today())
        self.active_timer: Optional[Tuple[int, int]] = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_running_timer)

        self.data_store: Dict[str, List[TaskRowData]] = {}
        self.rows: List[TaskRowData] = []
        self.cells: List[List[DayCell]] = []

        # Employee data
        self.employee_data = {
    "Dipangsu Mukherjee": "Technical",
    "Soumya Maity": "Technical",
    "Prithish Biswas": "Development",
    "Arya Majumdar": "Development",
    "Shahbaz Ali": "Technical",
    "Souma Banerjee": "Sales",
    "Shivangi Singh": "Sales",
    "Ritu Das": "Marketing",
    "Soumya Manna": "Development",
    "Jayant Rai": "Technical",
    "Ayos Ghosh": "Operation",
    "Sayam Rozario": "Admin",
    "Sneha Simran": "Admin",
    "Pompi Goswami": "Human Resource",
    "Joydeep Chakraborty": "Sales",
    "Peea P Bal": "Placement",
    "Romit Roy": "Admin",
    "Soumi Roy": "Admin",
    "Subhasis Marick": "Accountant",
    "Hrithik Lall": "Technical",
    "Subhojit Chakraborty": "Technical",
    "Rohit Kumar Singh": "Technical",
    "Sujay Kumar Lodh": "Technical",
    "Rahul Kumar Chakraborty": "Placement",
    "Sandipan Kundu": "Development",
    "Sachin Kumar Giri": "Technical",
    "Anamika Dutta": "Sales",
    "Sohini Das": "Sales",
    "Aheli Some": "Technical",
    "Shubham Kumar Choudhari": "Technical",
    "Mithun Jana": "Technical",
    "Saikat Dutta": "Development",
    "Ankan Roy": "Sales",
    "Utsav Majumdar": "Sales"
}

        
        # --- ADDED: Department-specific tasks and subtasks ---
        self.department_tasks = {
    "Sales": {
        "Lead Management": [
            "New Lead Calling",
            "Old Lead Follow-up",
            "Webinar & Seminar Coordination",
            "CRM Management",
            "Lead Management & Conversion Optimization"
        ],
        "Sales Conversion Activities": [
            "Product Demonstration (Online Demo)",
            "Office/ College Visit Booking",
            "Office/College Visit Client Handling",
            "Active Follow-up (Post-Demo/Visit)"
        ],
        "Revenue & Financial Operations": [
            "Revenue Generation & Target Achievement",
            "Bajaj EMI Process Management",
            "EMI Collection & Due Management",
            "Ex-SP EMI Collection",
            "Revenue Audit"
        ],
        "Client & Student Management": [
            "Client Relationship Management",
            "Handling Existing Students of Former Team Members",
            "Class Schedule Management"
        ],
        "Reporting & Strategy": [
            "Sales Strategy & Planning",
            "Reporting & Forecasting",
            "Daily Activity Report Submission"
        ],
        "Team Management & Collaboration": [
            "Daily Standups",
            "Daily Follow-up of Team Members’ Leads",
            "Sales Team Recruitment & Interviewing",
            "New Employee Training"
        ],
        "Cross-Functional Coordination": [
            "Coordination - Technical Team",
            "Coordination - Marketing Team",
            "Coordination - Accounts Team",
            "Coordination - Operations Team",
            "Compliance & Process Improvement"
        ],
        "Meeting": ["Meeting"],
        "Adhoc": ["Others (Please fill the comment)"]
    },
    "Technical": {
        "Curriculum Development": [
            "Training Module Development (SEO, SEM, Analytics, etc.)",
            "Customized Curriculum for B2B Clients",
            "Presentation (PPT) Preparation",
            "Creating Class Notes & Supplementary Resources",
            "Integrating Case Studies & Practical Exercises",
            "Project & Assignment Preparation"
        ],
        "Training Delivery & Student Engagement": [
            "Conducting Sessions (Data Analytics, Cloud, Cyber Security, etc.)",
            "Clearing Student Doubts",
            "Managing Class Schedules & Batch Monitoring"
        ],
        "Student Assessment & Career Support": [
            "Conducting Student Mock Interviews",
            "Providing Pre-Interview Brush-up Sessions",
            "Assignment & Test Paper Grading",
            "Internship & Live Project Support"
        ],
        "Research & Development (R&D)": [
            "R&D on New Subjects & Teaching Methods",
            "R&D on AI Tools & Technologies",
            "Reviewing & Revising Existing Course Content",
            "Developing PPT for Course Content",
            "Developing New Data Sources"
        ],
        "Business Development & Outreach": [
            "Conducting Demo Sessions for Admissions (B2C & B2B)",
            "Webinar & Seminar Planning",
            "College Visits & Online Workshops",
            "Collaboration with Industry for Internships",
            "Collaboration with Authorized Training Centers (ATCs)",
            "Providing Market Insights to Sales Teams"
        ],
        "Administration & Reporting": [
            "Coordination with Admin & Operations Teams",
            "Updating Daily Task Reports",
            "Automating Trackers & Internal Processes",
            "Managing Government Tender Processes"
        ],
        "Team & Quality Management": [
            "Trainer Development & Mentoring",
            "Interviewing & Selecting New Trainers",
            "Implementing Quality Control for Training Delivery"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    },
    "Admin": {
        "Learner Onboarding & Support": [
            "Conduct LMS Walkthrough for New Learners",
            "Act as Primary Point of Contact (POC) for Learners",
            "Create and Manage Learner Cohorts & WhatsApp Groups",
            "Welcome New Learners (Kits / ID Cards)",
            "Resolve Learner Queries (WhatsApp & Tickets)",
            "Handle Incoming Calls from Learners",
            "Contact Learners for Feedback"
        ],
        "Scheduling & Logistics": [
            "Schedule & Reschedule Classes/Exams",
            "Plan & Execute Seminars and Events",
            "Manage Travel and Accommodation Requests",
            "Monitor Training Logistics"
        ],
        "Strategic Operations & Process Management": [
            "Strategize Batch Planning with HODs",
            "Streamline & Improve Organizational Processes",
            "Handle High-Level Escalations",
            "Calculate Training Costs for Sales Quotations"
        ],
        "Inter-Departmental Coordination": [
            "Coordinate with Placement Team for Learner Transition",
            "Coordinate with HR for Policy Implementation",
            "Coordinate with Accounts (Trainer Pay, Expenses, etc.)",
            "Coordinate with HODs on Performance Feedback"
        ],
        "Quality Assurance & Performance": [
            "Conduct Audits on Live Classrooms",
            "Enforce Standard Operating Procedure (SOP) Compliance",
            "Monitor Student and Trainer Performance",
            "Implement Skill Matrix for Resource Utilization"
        ],
        "Certificate & Vendor Management": [
            "Ensure Digital Certificate Distribution",
            "Manage Vendor for Hard Copy Certificates"
        ],
        "Strategic Planning & Process Management": [
            "Strategize Batch Planning with HODs",
            "Streamline & Improve Organizational Processes",
            "Implement Skill Matrix for Resource Utilization",
            "Enforce Standard Operating Procedure (SOP) Compliance"
        ],
        "Performance & Quality Management": [
            "Oversee Student & Trainer Performance",
            "Conduct Audits on Live Classrooms",
            "Monitor Training Logistics & Quality"
        ],
        "Inter-Departmental Coordination (Extended)": [
            "Coordinate with Sales for Pricing & Quotations",
            "Coordinate with Placement Team for Learner Transition",
            "Coordinate with HR for Policy Implementation",
            "Coordinate with Accounts for Remuneration & Expenses"
        ],
        "Escalation & Issue Resolution": [
            "Handle High-Level Operational Escalations"
        ],
        "Logistics & Event Management": [
            "Plan & Execute Seminars and Events",
            "Manage Travel and Accommodation Requests"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    },
    "Development": {
        "Project Management & Scrum": [
            "Conduct Daily Scrum Meetings & Standups",
            "Manage Jira Boards & Sprint Progress",
            "Conduct Sprint Planning & Backlog Grooming",
            "Track Blockers, Dependencies & Resources",
            "Prepare Project Progress Reports",
            "Create & Maintain Project Documentation"
        ],
        "UI/UX & Graphic Design": [
            "Create Social Media Creatives (Posts, Carousels)",
            "Design Print Media (Banners, Brochures)",
            "Design UI Modules (Websites, Apps, Templates)",
            "Maintain UI/UX Design System",
            "Conduct UX Research & Brainstorming"
        ],
        "Frontend Development": [
            "Develop/Modify Frontend Modules",
            "Build Responsive Components",
            "Develop Landing Pages & Email Templates",
            "Manage Git & Version Control",
            "Frontend Testing & Debugging",
            "Monitor & Optimize Frontend Performance"
        ],
        "Backend & Database Development": [
            "Setup Backend/DB for New Projects (APIs)",
            "Backend Bug Fixing & Troubleshooting",
            "Perform Database Maintenance & Updates"
        ],
        "Website & LMS Maintenance": [
            "General Website/LMS Maintenance & Updates",
            "Export Leads from LMS/Panel",
            "Deploy Production Updates"
        ],
        "System & Server Administration": [
            "Manage Employee Email Accounts & Issues",
            "Monitor Server Uptime & Performance",
            "Manage Email Backups & Migrations",
            "Apply Security Patches & System Upgrades"
        ],
        "Training & Collaboration": [
            "Conduct Technical Training Sessions",
            "Cross-Functional Collaboration & Meetings",
            "Identify Team Training Needs"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    },
    "Human Resource": {
        "Recruitment & Onboarding": [
            "Job Posting, Screening & Sourcing",
            "Interview Coordination & Scheduling",
            "Issuing Offer & Appointment Letters",
            "New Joiner Documentation & Onboarding",
            "Induction & System Integration"
        ],
        "Payroll & Compensation": [
            "Salary Sheet Preparation & Calculation",
            "Payslip Generation & Distribution",
            "PF & ESIC Management (Application, Challan, etc.)",
            "TDS Calculation & Form 16 Distribution",
            "Managing Reimbursements & Advances"
        ],
        "Employee Lifecycle & Exit Management": [
            "Performance Appraisal Coordination",
            "Issuing HR Letters (Confirmation, Promotion, Warning, etc.)",
            "Handling Exit Formalities & Final Settlement",
            "Issuing Relieving & Experience Letters"
        ],
        "Employee Relations & Engagement": [
            "Grievance Handling & Resolution",
            "Planning & Executing Employee Engagement Activities",
            "Conducting Employee Surveys & Feedback Sessions",
            "Managing Disciplinary Actions & PIPs"
        ],
        "HR Administration & Compliance": [
            "Maintaining Employee Master Data & Trackers",
            "Managing Daily Attendance & Leave Records",
            "ID Card & Visiting Card Management",
            "Policy Documentation & Enforcement",
            "Managing Office Hygiene & Admin Tasks"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    },
    "Marketing": {
        "Content Strategy & Ideation": [
            "Creative Campaign Ideation",
            "Social Media Content Ideation & Research",
            "Website Content Planning",
            "B2B/B2C Project Content Strategy (Seminars, etc.)"
        ],
        "Content Creation & Writing": [
            "Blog & Technical Article Writing",
            "Social Media Copywriting (Captions & Post Content)",
            "Website Content Writing",
            "Brochure & Print Material Content",
            "Quora Content Creation"
        ],
        "Graphic & Video Production": [
            "Social Media Graphic Design (Static & Motion)",
            "Video Creation & Editing",
            "Brochure & Print Asset Design"
        ],
        "Social Media Management": [
            "Content Scheduling & Posting",
            "Community Engagement",
            "Social Media Performance Reporting"
        ],
        "Project & Team Management": [
            "Assigning Tasks to Content & Design Teams",
            "Content Editing, Proofreading & Delivery",
            "Monitoring Quality & Deadlines",
            "Coordinating with Printing Vendors"
        ],
        "Internal Collaboration & Events": [
            "Participation in Office Event Organization",
            "Cross-functional Content Meetings"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    },
    "Placement": {
        "Corporate Outreach & Tie-Ups": [
            "Relationship Building & Company Tie-Ups",
            "B2B Support & Collaboration"
        ],
        "Candidate Training & Grooming": [
            "Resume Building & Correction",
            "Soft Skills & Personal Branding Sessions",
            "Mock Interview Drills",
            "Job Placement Workshops"
        ],
        "Placement & Interview Management": [
            "Lining Up Interviews",
            "Database Management",
            "Tracking Placement Achievements"
        ],
        "Student Support & Onboarding": [
            "Conducting New Batch Orientation",
            "Grievance Handling",
            "B2C Support"
        ],
        "Team & Cross-Functional Coordination": [
            "Weekly Meetings (Sales, HODs)",
            "Support to Marketing (Testimonials, Offer Letters)",
            "Coordination with Development Team",
            "Monitoring Team Performance"
        ],
        "Adhoc": ["Others (Please fill the comment)"],
        "Meeting": ["Meeting"]
    }
}



        self._load_data()
        self._build_ui()
        self._on_employee_changed() # Call this to initialize the UI for the first employee

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Top Section
        top = QHBoxLayout()
        self.emp_combo = QComboBox()
        self.emp_combo.addItems(sorted(list(self.employee_data.keys())))
        self.emp_combo.currentTextChanged.connect(self._on_employee_changed) # --- MODIFIED ---
        top.addWidget(QLabel("Employee:"))
        top.addWidget(self.emp_combo)

        self.dept_field = QLineEdit()
        self.dept_field.setReadOnly(True)
        top.addWidget(QLabel("Department:"))
        top.addWidget(self.dept_field)

        # Task Dropdowns
        self.task_combo = QComboBox()
        self.subtask_combo = QComboBox()
        self.task_combo.setEditable(True)
        self.subtask_combo.setEditable(True)
        
        # --- ADDED: Connect task change to update subtasks ---
        self.task_combo.currentTextChanged.connect(self._on_task_changed)

        top.addWidget(QLabel("Task:"))
        top.addWidget(self.task_combo)
        top.addWidget(QLabel("Subtask:"))
        top.addWidget(self.subtask_combo)

        self.add_task_btn = QPushButton("➕ Add Task")
        self.add_task_btn.clicked.connect(self._add_task)
        self.add_task_btn.setStyleSheet("background-color:#2196F3; color:white; border-radius:6px; padding:6px;")
        top.addWidget(self.add_task_btn)
        layout.addLayout(top)

        # Table
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["TASK / SUBTASK", "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN", "TOTAL"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.week_total_lbl = QLabel("WEEKLY TOTAL: 0.00 h")
        self.week_total_lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #1A237E;")
        layout.addWidget(self.week_total_lbl)
        
    # --- ADDED: Functions to manage cascading dropdowns ---
    def _on_task_changed(self, selected_task: str):
        """Updates the subtask combobox based on the selected task."""
        self.subtask_combo.clear()
        
        dept = self.dept_field.text()
        department_specific_tasks = self.department_tasks.get(dept, {})
        
        subtasks = department_specific_tasks.get(selected_task, [])
        self.subtask_combo.addItems(subtasks)

    # ---------- Data ----------
    def _data_key(self):
        return f"{self.emp_combo.currentText()}::{self.week_start.isoformat()}"

    def _load_data(self):
        if os.path.exists(self.DATA_FILE):
            try:
                with open(self.DATA_FILE, "r") as f:
                    raw = json.load(f)
                for key, rows in raw.items():
                    self.data_store[key] = [TaskRowData.from_dict(r) for r in rows]
            except Exception:
                self.data_store = {}

    def _save_data(self):
        out = {k: [r.to_dict() for r in v] for k, v in self.data_store.items()}
        with open(self.DATA_FILE, "w") as f:
            json.dump(out, f, indent=2)

    def _on_employee_changed(self): # --- MODIFIED ---
        """Handles employee selection change."""
        emp = self.emp_combo.currentText()
        dept = self.employee_data.get(emp, "")
        self.dept_field.setText(dept)
        
        # Update task combo based on department
        self.task_combo.clear()
        department_specific_tasks = self.department_tasks.get(dept, {})
        if department_specific_tasks:
            self.task_combo.addItems(sorted(department_specific_tasks.keys()))
        
        # This will trigger _on_task_changed automatically to update subtasks
        
        self._load_employee_week()

    def _load_employee_week(self):
        emp = self.emp_combo.currentText()
        if not emp: return
        key = self._data_key()
        if key not in self.data_store:
            self.data_store[key] = []
        self.rows = self.data_store[key]
        self._build_table()

    # ---------- Add/Delete Task ----------
    def _add_task(self):
        task = self.task_combo.currentText().strip()
        subtask = self.subtask_combo.currentText().strip()
        if not task:
            QMessageBox.warning(self, "Invalid", "Please enter or select a Task.")
            return
        new_row = TaskRowData(task, subtask)
        self.rows.append(new_row)
        self._save_data()
        self._build_table()

    def _delete_task(self, index):
        confirm = QMessageBox.question(
            self, "Confirm Delete", "Are you sure you want to delete this task?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            del self.rows[index]
            self._save_data()
            self._build_table()

    # ---------- Table ----------
    def _build_table(self):
        self.table.setRowCount(0)
        self.cells.clear()

        for ri, row in enumerate(self.rows):
            self.table.insertRow(ri)
            self.table.setRowHeight(ri, 160)
            cell_widget = TaskCell(row.task, row.subtask, lambda _, r=ri: self._delete_task(r))
            self.table.setCellWidget(ri, 0, cell_widget)

            day_widgets = []
            for di in range(7):
                dc = DayCell()
                dc.set_hours(row.days[di].total_hours())
                dc.toggle_btn.clicked.connect(lambda _, r=ri, d=di, w=dc: self._toggle_timer(r, d, w))
                day_widgets.append(dc)
                self.table.setCellWidget(ri, di + 1, dc)
            self.cells.append(day_widgets)

            total = QLineEdit(f"{row.total_hours():.2f}")
            total.setReadOnly(True)
            total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(ri, 8, total)

        self._add_total_row()
        self._update_week_total()

    def _add_total_row(self):
        if not self.rows:
            return
        total_row = self.table.rowCount()
        self.table.insertRow(total_row)
        self.table.setRowHeight(total_row, 40)
        total_lbl = QLabel("🧮 Daily Total")
        total_lbl.setStyleSheet("font-weight:bold; color:#1B5E20; padding-left: 10px;")
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.table.setCellWidget(total_row, 0, total_lbl)

        for di in range(7):
            total_day = sum(r.days[di].total_hours() for r in self.rows)
            field = QLineEdit(f"{total_day:.2f}")
            field.setReadOnly(True)
            field.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(total_row, di + 1, field)

        week_total = sum(r.total_hours() for r in self.rows)
        total_field = QLineEdit(f"{week_total:.2f}")
        total_field.setReadOnly(True)
        total_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(total_row, 8, total_field)

    # ---------- Timer ----------
    def _toggle_timer(self, ri, di, widget):
        dd = self.rows[ri].days[di]

        if self.active_timer == (ri, di):
            self._stop_timer(ri, di, widget)
            return

        if self.active_timer:
            QMessageBox.warning(self, "Active Timer", "Please stop the current timer first.")
            return

        if di != date.today().weekday():
            QMessageBox.warning(self, "Invalid", "You can only start today's timer.")
            return

        dd.running_start = datetime.now()
        widget.set_running(True)
        self.active_timer = (ri, di)
        self._enable_all_buttons(False, except_widget=widget)
        self.timer.start()

    def _stop_timer(self, ri, di, widget):
        dd = self.rows[ri].days[di]
        if dd.running_start:
            dd.sessions.append((dd.running_start.isoformat(), datetime.now().isoformat()))
            dd.running_start = None
        widget.set_running(False)
        widget.set_hours(dd.total_hours())
        self.active_timer = None
        self._enable_all_buttons(True)
        self.timer.stop()
        self._save_data()
        self._build_table()

    def _update_running_timer(self):
        if not self.active_timer:
            return
        ri, di = self.active_timer
        hrs = self.rows[ri].days[di].total_hours()
        self.cells[ri][di].set_hours(hrs)
        self._update_week_total()

    def _enable_all_buttons(self, enable: bool, except_widget=None):
        for row in self.cells:
            for cell in row:
                if cell != except_widget:
                    cell.toggle_btn.setEnabled(enable)

    def _update_week_total(self):
        total = sum(r.total_hours() for r in self.rows)
        self.week_total_lbl.setText(f"WEEKLY TOTAL: {total:.2f} h")

    def _monday_of(self, d: date) -> date:
        return d - timedelta(days=d.weekday())


# ------------------ Run ------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QWidget { font-family: Segoe UI; font-size: 13px; }")
    win = TimesheetApp()
    win.show()
    sys.exit(app.exec())

