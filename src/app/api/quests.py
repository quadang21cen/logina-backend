from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel

from app.api.deps import get_current_user, RoleChecker
from app.models.sql_models import User, UserRole
from app.models.mongo_models import Quest
from app.services.ai_service import AiService

router = APIRouter(prefix="/quests", tags=["Quests"])

# Phân quyền: chỉ Giáo viên mới được tương tác các API soạn bài này
teacher_required = Depends(RoleChecker(allowed_roles=[UserRole.TEACHER]))

class RegenerateRequest(BaseModel):
    current_quest: Dict[str, Any]
    section: str  # "knowledge_pack", "role_card", "scenario_nodes", "rules"
    index: Optional[int] = None
    feedback: str

class SaveQuestRequest(BaseModel):
    title: str
    description: str
    knowledge_pack: Dict[str, Any]
    role_card: Dict[str, Any]
    scenario_nodes: List[Dict[str, Any]]
    rules: List[Dict[str, Any]]

@router.post("/generate-draft", dependencies=[teacher_required])
async def generate_draft(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    """Nạp liệu (Upload nhiều file PDF) -> AI (Gemini + LangChain) tự động bóc tách sinh cấu trúc Quest nháp."""
    ai_service = AiService()
    combined_text = ""
    
    # 1. Trích xuất text từ các file PDF
    for file in files:
        if not file.filename.endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {file.filename} is not a PDF file. Currently only PDF upload is supported."
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

    # 2. Gọi Gemini bóc tách qua LangChain
    try:
        quest_draft = await ai_service.generate_quest_draft(combined_text)
        return quest_draft
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Engine failed to parse curriculum: {str(e)}"
        )

@router.post("/regenerate-node", dependencies=[teacher_required])
async def regenerate_node(
    data: RegenerateRequest
):
    """AI sinh lại một khối dữ liệu cụ thể (Node, Role Card,...) dựa trên feedback sửa đổi của Giáo viên."""
    ai_service = AiService()
    try:
        updated_block = await ai_service.regenerate_section(
            current_quest=data.current_quest,
            section=data.section,
            index=data.index,
            feedback=data.feedback
        )
        return updated_block
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate section: {str(e)}"
        )

@router.post("/save", dependencies=[teacher_required])
async def save_quest(
    data: SaveQuestRequest,
    current_user: User = Depends(get_current_user)
):
    """Lưu chính thức Quest bài học nháp của Giáo viên vào MongoDB."""
    try:
        quest = Quest(
            title=data.title,
            description=data.description,
            creator_id=current_user.id,
            is_published=False,  # Lưu dưới dạng nháp trước (Draft)
            knowledge_pack=data.knowledge_pack,
            role_card=data.role_card,
            scenario_nodes=data.scenario_nodes,
            rules=data.rules
        )
        await quest.insert()
        return {
            "message": "Quest saved successfully as Draft",
            "quest_id": str(quest.id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save quest: {str(e)}"
        )
