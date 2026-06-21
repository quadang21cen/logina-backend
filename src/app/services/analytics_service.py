from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.config import settings

class TeacherActionCardSchema(BaseModel):
    title: str = Field(description="Tiêu đề cảnh báo/gợi ý sư phạm ngắn gọn, ví dụ: 'Cảnh báo: Lỗi mâu thuẫn lúa 3 vụ'")
    description: str = Field(description="Mô tả chi tiết lỗi tư duy phổ biến mà nhiều học sinh trong lớp đang mắc phải")
    pedagogical_action: str = Field(description="Gợi ý hành động sư phạm cụ thể cho giáo viên để giảng dạy lại hoặc sửa đổi tài liệu trên lớp")
    priority: str = Field(description="Mức độ ưu tiên: HIGH (Cao), MEDIUM (Trung bình), hoặc LOW (Thấp)")

class TeacherCardsListSchema(BaseModel):
    cards: List[TeacherActionCardSchema] = Field(description="Danh sách các thẻ gợi ý sư phạm")

class AnalyticsService:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3
        )
        self.parser = JsonOutputParser(pydantic_object=TeacherCardsListSchema)

    async def generate_action_cards(
        self, 
        class_metrics: Dict[str, Any], 
        error_logs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Sử dụng Gemini để phân tích hành vi lỗi của cả lớp học và tạo thẻ gợi ý sư phạm (Teacher Action Cards)."""
        
        system_prompt = (
            "Bạn là một chuyên gia tư vấn sư phạm AI cao cấp. Bạn được cung cấp dữ liệu thống kê "
            "về điểm số và nhật ký hành vi lỗi tư duy của một lớp học sau khi hoàn thành Quest bài học.\n\n"
            "Nhiệm vụ của bạn:\n"
            "1. Phân tích các lỗi tư duy phổ biến nhất (dựa trên danh sách các flags và điểm số trung bình).\n"
            "2. Tạo ra danh sách các thẻ hành động sư phạm (Teacher Action Cards) viết bằng Tiếng Việt.\n"
            "3. Mỗi thẻ phải đưa ra gợi ý giảng dạy cực kỳ thiết thực, rõ ràng để giúp giáo viên gỡ rối tư duy cho học sinh ngay trên lớp.\n\n"
            "{format_instructions}"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Dữ liệu thống kê lớp học:\n- Điểm số trung bình: {class_metrics}\n- Nhật ký lỗi tư duy thu thập được: {error_logs}")
        ])

        chain = prompt | self.llm | self.parser
        
        try:
            result = await chain.ainvoke({
                "class_metrics": str(class_metrics),
                "error_logs": str(error_logs),
                "format_instructions": self.parser.get_format_instructions()
            })
            return result.get("cards", [])
        except Exception as e:
            # Fallback nếu gọi LLM lỗi
            return [
                {
                    "title": "Gợi ý củng cố bài học",
                    "description": "Lớp học có một số lỗi chọn sai bằng chứng cho quyết định.",
                    "pedagogical_action": "Giáo viên nên nhắc lại mối liên hệ giữa các nguồn tài liệu số liệu và quyết định nông nghiệp.",
                    "priority": "MEDIUM"
                }
            ]
export_analytics_service = AnalyticsService()
