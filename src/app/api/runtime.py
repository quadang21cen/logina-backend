import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from bson import ObjectId

from app.api.deps import (
    get_current_user, 
    get_db_session, 
    get_redis_client,
    RoleChecker
)
from app.models.sql_models import User, UserRole, QuestRun
from app.models.mongo_models import Quest, EventLog
from app.services.validator import CrossCheckValidator

router = APIRouter(prefix="/runtime", tags=["Quest Runtime"])

class SubmitActionRequest(BaseModel):
    node_id: str
    decision_id: str
    selected_evidence_ids: List[str]

@router.get("/quest/{run_id}")
async def get_runtime_quest(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db_session),
    redis = Depends(get_redis_client)
):
    """Khởi tạo phiên làm bài của học sinh. Load Quest từ MongoDB và caching trạng thái vào Redis."""
    # 1. Kiểm tra lượt giao bài QuestRun trong Postgres
    from sqlalchemy import select
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
            detail="This quest run session is already completed"
        )

    # 2. Lấy thông tin cấu trúc Quest từ MongoDB
    try:
        quest = await Quest.get(ObjectId(quest_run.quest_id))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest package not found in MongoDB"
        )

    # 3. Khởi tạo/Lấy trạng thái Game State từ Upstash Redis
    redis_key = f"game_state:{run_id}:{current_user.id}"
    cached_state = await redis.get(redis_key)
    
    if not cached_state:
        # Khởi tạo game state mặc định
        initial_state = {
            "started_at": datetime.utcnow().isoformat(),
            "completed_nodes": {},
            "status": "IN_PROGRESS"
        }
        await redis.set(redis_key, json.dumps(initial_state), ex=86400)  # TTL 24h
        game_state = initial_state
    else:
        game_state = json.loads(cached_state)

    # 4. Trả về cấu trúc Quest cho giao diện làm bài (Ẩn trường rules để tránh hack đáp án)
    quest_data = quest.dict()
    quest_data.pop("rules", None)
    quest_data["id"] = str(quest.id)

    return {
        "run_id": run_id,
        "game_state": game_state,
        "quest": quest_data
    }

@router.post("/quest/{run_id}/submit-action")
async def submit_action(
    run_id: int,
    action_data: SubmitActionRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db_session),
    redis = Depends(get_redis_client)
):
    """
    Học sinh gửi cặp lựa chọn [Quyết định, Bằng chứng].
    Hệ thống chạy validator kiểm tra chéo, trả về Flags real-time và ghi event logs.
    """
    # 1. Lấy thông tin QuestRun để biết Quest ID tương ứng
    from sqlalchemy import select
    statement = select(QuestRun).where(QuestRun.id == run_id)
    result = await db.execute(statement)
    quest_run = result.scalar_one_or_none()
    
    if not quest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest run session not found"
        )

    # 2. Lấy cấu hình rules từ MongoDB Quest
    quest = await Quest.get(ObjectId(quest_run.quest_id))
    if not quest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest not found"
        )

    # 3. Chạy Cross-check Validator để đối chiếu
    flags = CrossCheckValidator.validate_action(
        rules=quest.rules,
        decision_id=action_data.decision_id,
        selected_evidence_ids=action_data.selected_evidence_ids
    )

    # 4. Cập nhật Game State tạm thời trong Redis
    redis_key = f"game_state:{run_id}:{current_user.id}"
    cached_state = await redis.get(redis_key)
    
    if cached_state:
        game_state = json.loads(cached_state)
    else:
        game_state = {"started_at": datetime.utcnow().isoformat(), "completed_nodes": {}}

    # Lưu lại câu trả lời và flags của Node này vào Redis
    game_state["completed_nodes"][action_data.node_id] = {
        "decision_id": action_data.decision_id,
        "selected_evidence_ids": action_data.selected_evidence_ids,
        "flags": flags,
        "submitted_at": datetime.utcnow().isoformat()
    }
    await redis.set(redis_key, json.dumps(game_state), ex=86400)

    # 5. Lưu nhật ký hành vi EventLog bất đồng bộ vào MongoDB
    event = EventLog(
        run_id=run_id,
        student_id=current_user.id,
        event_type="SUBMIT_ACTION",
        payload={
            "node_id": action_data.node_id,
            "decision_id": action_data.decision_id,
            "selected_evidence_ids": action_data.selected_evidence_ids,
            "flags": flags
        }
    )
    await event.insert()

    return {
        "status": "success",
        "flags": flags,
        "game_state": game_state
    }
