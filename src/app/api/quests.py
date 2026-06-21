import json
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from app.api.deps import get_current_user, get_redis_client, RoleChecker
from app.models.sql_models import User, UserRole
from app.models.mongo_models import Quest
from app.services.ai_service import AiService

router = APIRouter(prefix="/quests", tags=["Quests"])

teacher_required = Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))

class FeedbackRequest(BaseModel):
    feedback: str

@router.post("/generate-draft", dependencies=[teacher_required])
async def generate_draft(
    files: Optional[List[UploadFile]] = File(None),
    curriculum_text: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis_client)
):
    """
    Bước 1: Nhận PDF và/hoặc text giáo trình -> Gọi AI chạy Pipeline 3 bước tạo 10 Nodes -> Lưu nháp vào Redis.
    """
    ai_service = AiService()
    combined_text = ""
    
    # 1. Đọc text từ các file PDF tải lên
    if files:
        for file in files:
            if not file.filename.endswith(".pdf"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File {file.filename} is not a PDF. Only PDF upload is supported."
                )
            try:
                content = await file.read()
                text = ai_service.extract_text_from_pdf(content)
                combined_text += f"\n--- FILE: {file.filename} ---\n" + text
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error reading PDF file {file.filename}: {str(e)}"
                )

    # 2. Cộng gộp với text giáo trình nhập trực tiếp
    if curriculum_text:
        combined_text += "\n" + curriculum_text

    if not combined_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No source materials provided. Please upload a PDF or enter text curriculum."
        )

    # 3. Chạy AI Pipeline tạo Quest Draft
    try:
        quest_draft = await ai_service.generate_quest_draft_full(combined_text)
        
        # Lưu nháp vào Redis (Key định danh bằng ID của giáo viên, TTL = 24h)
        redis_key = f"draft:quest:{current_user.id}"
        await redis.set(redis_key, json.dumps(quest_draft), ex=86400)
        
        return quest_draft
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Quest generation failed: {str(e)}"
        )

@router.get("/draft", dependencies=[teacher_required])
async def get_draft(
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis_client)
):
    """
    Lấy thông tin Quest nháp hiện tại của giáo viên từ Redis.
    """
    redis_key = f"draft:quest:{current_user.id}"
    cached_draft = await redis.get(redis_key)
    if not cached_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active quest draft found. Create a new one first."
        )
    return json.loads(cached_draft)

@router.patch("/draft/node/{node_id}", dependencies=[teacher_required])
async def regenerate_node(
    node_id: str,
    data: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis_client)
):
    """
    Bước 2: Sửa đổi và sinh lại duy nhất một Node câu hỏi cụ thể, cập nhật rules liên quan và lưu vào Redis.
    """
    redis_key = f"draft:quest:{current_user.id}"
    cached_draft = await redis.get(redis_key)
    if not cached_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quest draft not found in cache. Please generate a draft first."
        )
    
    quest_draft = json.loads(cached_draft)
    
    # Tìm xem node_id có tồn tại trong draft không
    scenario_nodes = quest_draft.get("scenario_nodes", [])
    node_index = next((i for i, n in enumerate(scenario_nodes) if n["node_id"] == node_id), None)
    if node_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID '{node_id}' not found in the current draft"
        )
        
    # Gọi AI regenerate riêng node đó
    ai_service = AiService()
    try:
        updated_data = await ai_service.regenerate_individual_node(
            current_quest=quest_draft,
            node_id=node_id,
            feedback=data.feedback
        )
        
        # Cập nhật thông tin node mới vào draft
        quest_draft["scenario_nodes"][node_index] = updated_data["node"]
        
        # Cập nhật hoặc đè các rules kiểm chứng chéo liên quan đến node này
        updated_node_decisions = [d["id"] for d in updated_data["node"].get("decisions", [])]
        
        # Lọc bỏ các rule cũ liên quan đến decisions của node này
        current_rules = quest_draft.get("rules", [])
        filtered_rules = [r for r in current_rules if r["decision_id"] not in updated_node_decisions]
        
        # Thêm các rules mới được sinh cho node này
        filtered_rules.extend(updated_data["rules"])
        quest_draft["rules"] = filtered_rules
        
        # Lưu đè lại vào Redis
        await redis.set(redis_key, json.dumps(quest_draft), ex=86400)
        
        return quest_draft
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate node: {str(e)}"
        )

@router.post("/publish", dependencies=[teacher_required])
async def publish_quest(
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis_client)
):
    """
    Bước 3: Lưu chính thức bản nháp từ Redis vào MongoDB (Publish).
    """
    redis_key = f"draft:quest:{current_user.id}"
    cached_draft = await redis.get(redis_key)
    if not cached_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No quest draft found in cache to publish."
        )
    
    draft = json.loads(cached_draft)
    
    try:
        # Tạo object Quest của MongoDB
        quest = Quest(
            title=draft["title"],
            description=draft.get("description", ""),
            creator_id=current_user.id,
            is_published=True,  # Đánh dấu xuất bản chính thức
            knowledge_pack=draft.get("knowledge_pack"),
            role_card=draft.get("role_card"),
            scenario_nodes=draft.get("scenario_nodes", []),
            rules=draft.get("rules", [])
        )
        await quest.insert()
        
        # Xóa cache nháp trên Redis
        await redis.delete(redis_key)
        
        return {
            "status": "success",
            "message": "Quest successfully published to MongoDB",
            "quest_id": str(quest.id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish quest to MongoDB: {str(e)}"
        )
