import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from bson import ObjectId
from sqlalchemy import select, func

from app.api.deps import (
    get_current_user, 
    get_db_session, 
    get_redis_client,
    RoleChecker
)
from app.models.sql_models import User, UserRole, QuestRun, StudentReport
from app.models.mongo_models import Quest, EventLog
from app.services.rubric_engine import RubricEngine
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

class StudentReportOut(BaseModel):
    id: int
    run_id: int
    student_id: int
    score_knowledge: float
    score_evidence: float
    score_decision: float
    score_consistency: float
    feedback: Optional[str]
    completed_at: datetime

class TeacherDashboardOut(BaseModel):
    total_students: int
    completed_students: int
    average_scores: Dict[str, float]
    action_cards: List[Dict[str, Any]]

@router.post("/quest/{run_id}/submit-quest", response_model=StudentReportOut)
async def submit_quest(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db_session),
    redis = Depends(get_redis_client)
):
    """
    Nộp bài làm chính thức.
    Tính điểm Rubric 4 trục, lưu báo cáo vào Postgres và dọn dẹp Redis cache.
    """
    # 1. Tìm QuestRun để lấy thông tin quest_id tương ứng
    statement = select(QuestRun).where(QuestRun.id == run_id)
    result = await db.execute(statement)
    quest_run = result.scalar_one_or_none()
    
    if not quest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest run session not found"
        )
        
    if quest_run.status == "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This quest run has already been completed and submitted"
        )

    # 2. Đếm tổng số Scenario Nodes trong MongoDB Quest để tính thang điểm
    quest = await Quest.get(ObjectId(quest_run.quest_id))
    if not quest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest not found in MongoDB"
        )
    total_nodes = len(quest.scenario_nodes)

    # 3. Lấy Game State tạm từ Redis
    redis_key = f"game_state:{run_id}:{current_user.id}"
    cached_state = await redis.get(redis_key)
    
    if not cached_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No progress found in Redis cache. Cannot submit."
        )
        
    game_state = json.loads(cached_state)

    # 4. Tính điểm 4 trục năng lực qua Rubric Engine
    scores = RubricEngine.calculate_scores(game_state, total_nodes)

    # 5. Lưu báo cáo điểm StudentReport vào PostgreSQL
    report = StudentReport(
        run_id=run_id,
        student_id=current_user.id,
        score_knowledge=scores["knowledge"],
        score_evidence=scores["evidence"],
        score_decision=scores["decision"],
        score_consistency=scores["consistency"],
        feedback=f"Hoàn thành Quest '{quest.title}' vào lúc {datetime.utcnow().strftime('%H:%M %d/%m/%Y')}.",
        completed_at=datetime.utcnow()
    )
    db.add(report)
    
    # Cập nhật trạng thái QuestRun (nếu cần thiết, trong MVP đơn giản)
    # quest_run.status = "COMPLETED"
    
    await db.commit()
    await db.refresh(report)

    # 6. Dọn dẹp cache Redis
    await redis.delete(redis_key)

    return report

@router.get("/student/{run_id}", response_model=StudentReportOut)
async def get_student_report(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db_session)
):
    """Học sinh xem kết quả báo cáo điểm 4 trục của chính mình sau Quest."""
    statement = select(StudentReport).where(
        (StudentReport.run_id == run_id) & 
        (StudentReport.student_id == current_user.id)
    )
    result = await db.execute(statement)
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found for this quest run"
        )
    return report

@router.get("/teacher/class/{class_id}", response_model=TeacherDashboardOut, dependencies=[Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))])
async def get_teacher_class_analytics(
    class_id: int,
    db = Depends(get_db_session)
):
    """
    Dashboard Giáo viên.
    Tổng hợp điểm trung bình của cả lớp từ Postgres + Gọi Gemini phân tích event logs từ MongoDB
    để tự động sinh ra các Pedagogical Teacher Action Cards.
    """
    # 1. Lấy toàn bộ lượt giao Quest (Runs) của lớp này
    runs_statement = select(QuestRun).where(QuestRun.class_id == class_id)
    runs_result = await db.execute(runs_statement)
    runs = runs_result.scalars().all()
    run_ids = [r.id for r in runs]
    
    if not run_ids:
        return {
            "total_students": 0,
            "completed_students": 0,
            "average_scores": {"knowledge": 0, "evidence": 0, "decision": 0, "consistency": 0},
            "action_cards": []
        }

    # 2. Lấy toàn bộ báo cáo điểm của học sinh thuộc các Run này
    reports_statement = select(StudentReport).where(StudentReport.run_id.in_(run_ids))
    reports_result = await db.execute(reports_statement)
    reports = reports_result.scalars().all()
    
    if not reports:
        return {
            "total_students": 0,
            "completed_students": 0,
            "average_scores": {"knowledge": 0, "evidence": 0, "decision": 0, "consistency": 0},
            "action_cards": []
        }

    # 3. Tính điểm trung bình 4 trục
    avg_k = sum(r.score_knowledge for r in reports) / len(reports)
    avg_e = sum(r.score_evidence for r in reports) / len(reports)
    avg_d = sum(r.score_decision for r in reports) / len(reports)
    avg_c = sum(r.score_consistency for r in reports) / len(reports)
    
    class_metrics = {
        "knowledge": round(avg_k, 2),
        "evidence": round(avg_e, 2),
        "decision": round(avg_d, 2),
        "consistency": round(avg_c, 2)
    }

    # 4. Gom nhật ký lỗi tư duy từ MongoDB EventLog của các lượt run này
    # Lấy các event submit chứa lỗi (flags)
    error_logs = []
    events = await EventLog.find(EventLog.run_id.in_(run_ids)).to_list(100) # Giới hạn 100 log gần nhất
    for event in events:
        flags = event.payload.get("flags", [])
        if flags:
            error_logs.append({
                "node_id": event.payload.get("node_id"),
                "decision_id": event.payload.get("decision_id"),
                "flags": flags
            })

    # 5. Gọi AI Analytics Service để sinh ra Teacher Action Cards
    analytics_service = AnalyticsService()
    action_cards = await analytics_service.generate_action_cards(
        class_metrics=class_metrics,
        error_logs=error_logs
    )

    return {
        "total_students": len(reports),  # Tạm thời trong MVP lấy số lượng đã nộp bài
        "completed_students": len(reports),
        "average_scores": class_metrics,
        "action_cards": action_cards
    }
