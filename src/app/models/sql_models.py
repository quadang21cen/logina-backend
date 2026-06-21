from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

# --- User & Authentication Models ---
class UserRole(str):
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: str
    role: str = Field(default=UserRole.STUDENT)
    is_active: bool = Field(default=True)

class User(UserBase, table=True):
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    classes_taught: List["Class"] = Relationship(back_populates="teacher")
    enrollments: List["ClassStudentLink"] = Relationship(back_populates="student")

# --- Class & Student Links ---
class ClassStudentLink(SQLModel, table=True):
    __tablename__ = "class_student_links"
    
    class_id: int = Field(foreign_key="classes.id", primary_key=True)
    student_id: int = Field(foreign_key="users.id", primary_key=True)
    enrolled_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    class_obj: "Class" = Relationship(back_populates="student_links")
    student: User = Relationship(back_populates="enrollments")

class ClassBase(SQLModel):
    name: str
    description: Optional[str] = None

class Class(ClassBase, table=True):
    __tablename__ = "classes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    teacher_id: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    teacher: User = Relationship(back_populates="classes_taught")
    student_links: List[ClassStudentLink] = Relationship(back_populates="class_obj")
    runs: List["QuestRun"] = Relationship(back_populates="class_obj")

# --- Quest Run & Report Models ---
class QuestRunBase(SQLModel):
    quest_id: str  # Referencing MongoDB Quest ID
    status: str = Field(default="PENDING")  # PENDING, ACTIVE, COMPLETED
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

class QuestRun(QuestRunBase, table=True):
    __tablename__ = "quest_runs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    class_id: int = Field(foreign_key="classes.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relationships
    class_obj: Class = Relationship(back_populates="runs")
    reports: List["StudentReport"] = Relationship(back_populates="run")

class StudentReportBase(SQLModel):
    student_id: int = Field(foreign_key="users.id")
    
    # Scores (Rubric Engine 4 axes)
    score_knowledge: float = Field(default=0.0)
    score_evidence: float = Field(default=0.0)
    score_decision: float = Field(default=0.0)
    score_consistency: float = Field(default=0.0)
    
    feedback: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)

class StudentReport(StudentReportBase, table=True):
    __tablename__ = "student_reports"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="quest_runs.id")
    
    # Relationships
    run: QuestRun = Relationship(back_populates="reports")
