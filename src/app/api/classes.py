from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, get_db_session, RoleChecker
from app.models.sql_models import User, UserRole, Class, ClassStudentLink, QuestRun

router = APIRouter(prefix="/classes", tags=["Classes & Students"])

# Cấu hình Pydantic DTO
class ClassOut(BaseModel):
    id: int
    name: str
    description: str | None
    teacher_id: int

class ClassCreate(BaseModel):
    name: str
    description: str | None = None

class AssignQuestRequest(BaseModel):
    quest_id: str  # MongoDB Quest ID

class QuestRunOut(BaseModel):
    id: int
    class_id: int
    quest_id: str
    status: str

class StudentOut(BaseModel):
    id: int
    email: str
    full_name: str

@router.get("/", response_model=List[ClassOut])
async def get_classes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Lấy danh sách các lớp học thuộc quyền quản lý của giáo viên hoặc lớp mà học sinh tham gia."""
    if current_user.role == UserRole.TEACHER:
        statement = select(Class).where(Class.teacher_id == current_user.id)
    else:
        # Lấy danh sách class mà học sinh được enroll
        statement = select(Class).join(ClassStudentLink).where(ClassStudentLink.student_id == current_user.id)
        
    result = await db.execute(statement)
    classes = result.scalars().all()
    return classes

@router.post("/", response_model=ClassOut, dependencies=[Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))])
async def create_class(
    data: ClassCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Giáo viên tạo một lớp học mới."""
    new_class = Class(
        name=data.name,
        description=data.description,
        teacher_id=current_user.id
    )
    db.add(new_class)
    await db.commit()
    await db.refresh(new_class)
    return new_class

from datetime import datetime

@router.post("/{class_id}/assign-quest", response_model=QuestRunOut, dependencies=[Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))])
async def assign_quest(
    class_id: int,
    data: AssignQuestRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Giáo viên giao một Quest cho lớp học (Tạo QuestRun)."""
    # Kiểm tra xem class có tồn tại không
    class_statement = select(Class).where(Class.id == class_id)
    class_result = await db.execute(class_statement)
    class_obj = class_result.scalar_one_or_none()
    
    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
        
    # Tạo lượt chơi mới cho cả lớp
    new_run = QuestRun(
        class_id=class_id,
        quest_id=data.quest_id,
        status="ACTIVE",
        started_at=datetime.utcnow()
    )
    db.add(new_run)
    await db.commit()
    await db.refresh(new_run)
    return new_run


@router.get("/{class_id}/students", response_model=List[StudentOut], dependencies=[Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))])
async def get_class_students(
    class_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Giáo viên xem danh sách các học sinh thuộc lớp học này."""
    statement = select(User).join(ClassStudentLink).where(ClassStudentLink.class_id == class_id)
    result = await db.execute(statement)
    students = result.scalars().all()
    return students
