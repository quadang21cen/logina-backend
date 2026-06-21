import io
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pypdf import PdfReader
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser

from app.config import settings

# --- Pydantic Schema để ép kiểu JSON Structured Output từ Gemini ---

class LabeledItem(BaseModel):
    id: str = Field(description="ID định danh viết tắt, ví dụ: dec_solar, ev_price")
    text: str = Field(description="Nội dung văn bản chi tiết")

class KnowledgePackSchema(BaseModel):
    title: str = Field(description="Tiêu đề tài liệu tóm tắt")
    content: str = Field(description="Nội dung tóm tắt kiến thức cốt lõi, số liệu nổi bật từ giáo trình để học sinh đọc làm bài")

class RoleCardSchema(BaseModel):
    role_name: str = Field(description="Tên vai trò nhập vai, ví dụ: Nhà phân tích môi trường")
    description: str = Field(description="Mô tả bối cảnh và vai trò của học sinh")
    objectives: List[str] = Field(description="Danh sách các mục tiêu cụ thể học sinh cần đạt được")

class ScenarioNodeSchema(BaseModel):
    node_id: str = Field(description="Mã định danh node, ví dụ: node_1")
    title: str = Field(description="Tiêu đề tình huống ngắn gọn")
    description: str = Field(description="Mô tả bối cảnh tình huống thực tế và câu hỏi đặt ra")
    decisions: List[LabeledItem] = Field(description="Danh sách các quyết định (Decisions) học sinh có thể lựa chọn")
    evidence_options: List[LabeledItem] = Field(description="Danh sách các bằng chứng bảo vệ (Evidences) lấy từ tài liệu")

class CrossCheckRuleSchema(BaseModel):
    rule_id: str = Field(description="Mã rule, ví dụ: rule_1")
    decision_id: str = Field(description="ID của Quyết định bị kiểm tra")
    required_evidence_ids: List[str] = Field(description="Danh sách các ID bằng chứng BẮT BUỘC phải chọn đi kèm để quyết định này được công nhận")
    severity: str = Field(description="Mức độ nghiêm trọng của lỗi: CONTRADICTION (Mâu thuẫn hoàn toàn), WEAK_EVIDENCE (Thiếu bằng chứng vững chắc), hoặc INFO")
    message: str = Field(description="Lời giải thích sư phạm chi tiết giải thích tại sao quyết định mâu thuẫn/thiếu bằng chứng")

class CompleteQuestSchema(BaseModel):
    title: str = Field(description="Tiêu đề bài học Quest tổng thể")
    description: str = Field(description="Mô tả tổng quan Quest")
    knowledge_pack: KnowledgePackSchema = Field(description="Khối tài liệu tóm tắt cốt lõi")
    role_card: RoleCardSchema = Field(description="Vai trò nhập vai")
    scenario_nodes: List[ScenarioNodeSchema] = Field(description="Các tình huống và câu hỏi thực tế")
    rules: List[CrossCheckRuleSchema] = Field(description="Các quy định logic kiểm chứng chéo")


class AiService:
    def __init__(self):
        # Khởi tạo Gemini Model thông qua LangChain
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.2
        )
        self.parser = JsonOutputParser(pydantic_object=CompleteQuestSchema)

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes) -> str:
        """Đọc văn bản từ file PDF tải lên."""
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text_content = page.extract_text()
            if text_content:
                text += text_content + "\n"
        return text

    async def generate_quest_draft(self, curriculum_text: str) -> CompleteQuestSchema:
        """Sử dụng LangChain và Gemini để bóc tách giáo trình thành Quest Package cấu trúc JSON."""
        system_prompt = (
            "Bạn là một chuyên gia thiết kế sư phạm AI cao cấp. Nhiệm vụ của bạn là chuyển đổi chương trình học (Curriculum-to-Quest) "
            "thành một kịch bản tình huống thực tế (Quest Package) dành cho học sinh. Học sinh sẽ nhập vai đưa ra quyết định dựa trên bằng chứng.\n\n"
            "Hãy phân tích tài liệu giáo trình dưới đây và tạo cấu trúc dữ liệu chính xác theo định dạng JSON quy định.\n"
            "Lưu ý quan trọng:\n"
            "1. Knowledge Pack: Tóm tắt lại các dữ kiện khoa học/thực tế nổi bật từ tài liệu.\n"
            "2. Role Card: Thiết kế vai trò nhập vai hấp dẫn (ví dụ: Chuyên gia môi trường, Bác sĩ dịch tễ, kỹ sư mùa vụ).\n"
            "3. Scenario Nodes: Tạo ít nhất từ 1 đến 3 tình huống thực tế liên tiếp thách thức học sinh đưa ra Quyết định (Decision) từ các lựa chọn có sẵn, "
            "và phải chọn các Bằng chứng (Evidence) phù hợp trong danh mục để bảo vệ quyết định của mình.\n"
            "4. Rules: Thiết kế các luật logic kiểm chứng chéo (Cross-check rules). Ví dụ: Nếu học sinh chọn Quyết định A (có hại cho kinh tế) "
            "nhưng không chọn Bằng chứng B (dữ liệu chứng minh thiệt hại) thì hệ thống sẽ Trigger Flag báo lỗi mâu thuẫn.\n\n"
            "{format_instructions}\n"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Đây là nội dung tài liệu giáo trình:\n\n{curriculum_text}")
        ])

        # Kết hợp prompt, llm và parser
        chain = prompt | self.llm | self.parser
        
        # Chạy chuỗi để gen ra JSON Quest
        result = await chain.ainvoke({
            "curriculum_text": curriculum_text,
            "format_instructions": self.parser.get_format_instructions()
        })
        
        return result

    async def regenerate_section(
        self, 
        current_quest: Dict[str, Any], 
        section: str, 
        index: Optional[int], 
        feedback: str
    ) -> Dict[str, Any]:
        """Gemini hỗ trợ Generate lại một phần nhỏ của Quest dựa trên feedback của Giáo viên (Human-in-the-loop)."""
        
        # Định nghĩa Prompt tùy chỉnh cho khâu sửa đổi
        system_prompt = (
            "Bạn là một trợ lý thiết kế kịch bản sư phạm. Giáo viên đã tạo ra một Quest bài học, "
            "tuy nhiên họ muốn chỉnh sửa một phần cụ thể dựa trên ý kiến đóng góp (feedback).\n\n"
            "Nhiệm vụ của bạn:\n"
            "Hãy đọc toàn bộ nội dung Quest hiện tại, tập trung vào mục cần chỉnh sửa: '{section}' "
            "(nếu là mảng thì chỉ số index là '{index}').\n"
            "Tiến hành sinh lại hoặc sửa đổi duy nhất phần đó dựa trên feedback sau:\n"
            "Feedback: \"{feedback}\"\n\n"
            "Yêu cầu đầu ra:\n"
            "Trả về duy nhất nội dung phần đã được sửa đổi dưới dạng JSON khớp hoàn chỉnh với schema của mục đó.\n"
            "Không trả về bất kỳ văn bản giải thích nào ngoài khối JSON sạch."
        )
        
        # Lấy schema tương ứng với từng phần để LLM hiểu cấu trúc trả ra
        if section == "knowledge_pack":
            parser = JsonOutputParser(pydantic_object=KnowledgePackSchema)
        elif section == "role_card":
            parser = JsonOutputParser(pydantic_object=RoleCardSchema)
        elif section == "scenario_nodes":
            parser = JsonOutputParser(pydantic_object=ScenarioNodeSchema)
        elif section == "rules":
            parser = JsonOutputParser(pydantic_object=CrossCheckRuleSchema)
        else:
            parser = JsonOutputParser()

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n\n{format_instructions}"),
            ("user", "Nội dung Quest hiện tại: {current_quest}")
        ])
        
        chain = prompt | self.llm | parser
        
        updated_block = await chain.ainvoke({
            "section": section,
            "index": str(index) if index is not None else "N/A",
            "feedback": feedback,
            "current_quest": str(current_quest),
            "format_instructions": parser.get_format_instructions()
        })
        
        return updated_block
