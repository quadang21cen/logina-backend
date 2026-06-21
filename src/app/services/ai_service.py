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
    image_url: Optional[str] = Field(default=None, description="Đường dẫn ảnh minh họa cho tình huống. Mặc định là null.")

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

# --- Schemas cho từng bước trong Pipeline tạo 10 Nodes ---

class NodeOutlineItem(BaseModel):
    node_id: str = Field(description="node_1 đến node_10")
    concept: str = Field(description="Ý tưởng chính hoặc sự kiện chính của Node, ví dụ: 'Phát hiện hạn mặn và kiểm tra số liệu'")

class QuestOutlineSchema(BaseModel):
    title: str = Field(description="Tiêu đề Quest")
    description: str = Field(description="Mô tả tổng quan")
    knowledge_pack: KnowledgePackSchema = Field(description="Tài liệu tóm tắt cốt lõi")
    role_card: RoleCardSchema = Field(description="Vai trò nhập vai")
    node_outlines: List[NodeOutlineItem] = Field(description="Danh sách phác thảo cho đúng 10 node")

class NodesBatchSchema(BaseModel):
    nodes: List[ScenarioNodeSchema] = Field(description="Danh sách chi tiết các node được sinh ra")

class RulesSchema(BaseModel):
    rules: List[CrossCheckRuleSchema] = Field(description="Danh sách các luật kiểm chứng chéo cho các node")


class AiService:
    def __init__(self):
        # Khởi tạo Gemini Model thông qua LangChain
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.2
        )

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

    async def generate_quest_outline(self, curriculum_text: str) -> Dict[str, Any]:
        """Bước 1: Tạo bộ khung Quest, vai trò và phác thảo 10 node tình huống."""
        parser = JsonOutputParser(pydantic_object=QuestOutlineSchema)
        system_prompt = (
            "Bạn là chuyên gia sư phạm. Nhiệm vụ của bạn là đọc giáo trình sau và thiết kế bộ khung tổng quan cho bài học Quest nhập vai.\n"
            "Hãy viết mô tả kịch bản tổng quan, vai trò của học sinh, và phác thảo đúng 10 node tình huống logic từ node_1 đến node_10 liên kết chặt chẽ.\n"
            "{format_instructions}\n"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Giáo trình học tập:\n\n{curriculum_text}")
        ])
        chain = prompt | self.llm | parser
        return await chain.ainvoke({
            "curriculum_text": curriculum_text,
            "format_instructions": parser.get_format_instructions()
        })

    async def generate_nodes_batch(
        self, 
        curriculum_text: str, 
        outline: Dict[str, Any], 
        batch_outlines: List[Dict[str, Any]], 
        previous_nodes: List[Dict[str, Any]] = []
    ) -> List[Dict[str, Any]]:
        """Bước 2: Tạo chi tiết (Decisions, Evidences) cho một cụm Node cụ thể."""
        parser = JsonOutputParser(pydantic_object=NodesBatchSchema)
        system_prompt = (
            "Bạn là chuyên gia thiết kế sư phạm AI. Dựa trên tài liệu gốc, bối cảnh Quest học tập, và mô tả ý tưởng các node cần triển khai, "
            "hãy tạo chi tiết (Decisions, Evidence Options) cho các node được chỉ định dưới đây.\n"
            "Đảm bảo các bằng chứng (Evidence Options) được trích từ tài liệu gốc. Trường image_url để mặc định là null.\n"
            "Nếu có các node đã sinh từ trước, hãy đảm bảo các node mới kế thừa và kết nối hợp lý.\n\n"
            "{format_instructions}\n"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Tài liệu gốc:\n{curriculum_text}\n\nQuest Outline:\n{outline}\n\nCác node cần sinh trong đợt này:\n{batch_outlines}\n\nCác node đã sinh trước đó làm ngữ cảnh:\n{previous_nodes}")
        ])
        chain = prompt | self.llm | parser
        res = await chain.ainvoke({
            "curriculum_text": curriculum_text,
            "outline": str(outline),
            "batch_outlines": str(batch_outlines),
            "previous_nodes": str(previous_nodes),
            "format_instructions": parser.get_format_instructions()
        })
        return res.get("nodes", [])

    async def compile_cross_check_rules(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Bước 3: Tổng hợp 10 Node đã sinh để thiết kế ra bộ luật kiểm chứng chéo (rules)."""
        parser = JsonOutputParser(pydantic_object=RulesSchema)
        system_prompt = (
            "Bạn là chuyên gia kiểm tra logic sư phạm. Đọc kỹ 10 node tình huống dưới đây, đối chiếu các lựa chọn Quyết định (decisions) "
            "với danh mục Bằng chứng (evidence_options).\n"
            "Hãy thiết kế các luật kiểm chứng chéo (rules) chi tiết để phát hiện lỗi mâu thuẫn (CONTRADICTION - nếu chọn quyết định không phù hợp hoặc bằng chứng tự vạch trần quyết định đó) "
            "hoặc thiếu bằng chứng khoa học (WEAK_EVIDENCE).\n\n"
            "{format_instructions}\n"
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Danh sách 10 Nodes chi tiết:\n\n{nodes}")
        ])
        chain = prompt | self.llm | parser
        res = await chain.ainvoke({
            "nodes": str(nodes),
            "format_instructions": parser.get_format_instructions()
        })
        return res.get("rules", [])

    async def generate_quest_draft_full(self, curriculum_text: str) -> Dict[str, Any]:
        """Tổ hợp toàn bộ quy trình 3 bước để sinh Quest bài học 10 nodes hoàn chỉnh."""
        # 1. Tạo Outline tổng quan
        outline = await self.generate_quest_outline(curriculum_text)
        
        node_outlines = outline.get("node_outlines", [])
        # Nếu AI trả về ít hơn 10, ta tự chuẩn hóa để đảm bảo có tối đa 10 phác thảo
        
        # 2. Sinh chi tiết theo từng cụm (Cụm 1: Node 1-4, Cụm 2: Node 5-7, Cụm 3: Node 8-10)
        all_nodes = []
        
        # Batch 1: Node 1 đến 4
        batch1 = node_outlines[0:4]
        nodes1 = await self.generate_nodes_batch(curriculum_text, outline, batch1, [])
        all_nodes.extend(nodes1)
        
        # Batch 2: Node 5 đến 7
        batch2 = node_outlines[4:7]
        if batch2:
            nodes2 = await self.generate_nodes_batch(curriculum_text, outline, batch2, all_nodes)
            all_nodes.extend(nodes2)
            
        # Batch 3: Node 8 đến 10
        batch3 = node_outlines[7:10]
        if batch3:
            nodes3 = await self.generate_nodes_batch(curriculum_text, outline, batch3, all_nodes)
            all_nodes.extend(nodes3)
            
        # 3. Tạo bộ rules tổng hợp chéo
        rules = await self.compile_cross_check_rules(all_nodes)
        
        return {
            "title": outline.get("title", "Logina AI Quest"),
            "description": outline.get("description", ""),
            "knowledge_pack": outline.get("knowledge_pack"),
            "role_card": outline.get("role_card"),
            "scenario_nodes": all_nodes,
            "rules": rules
        }

    async def regenerate_individual_node(
        self, 
        current_quest: Dict[str, Any], 
        node_id: str, 
        feedback: str
    ) -> Dict[str, Any]:
        """Chỉnh sửa và sinh lại duy nhất một Node cụ thể dựa trên feedback của giáo viên và cập nhật các rules tương ứng."""
        node_parser = JsonOutputParser(pydantic_object=ScenarioNodeSchema)
        rules_parser = JsonOutputParser(pydantic_object=RulesSchema)
        
        # 1. Sinh lại thông tin Node
        node_system_prompt = (
            "Bạn là trợ lý thiết kế kịch bản sư phạm. Giáo viên đã tạo ra một Quest bài học, "
            "tuy nhiên họ muốn chỉnh sửa duy nhất thông tin của Node mang ID '{node_id}' dựa trên ý kiến đóng góp (feedback).\n"
            "Hãy phân tích bối cảnh và sinh lại chi tiết Node này (giữ nguyên id của node). Trường image_url để mặc định là null.\n\n"
            "{format_instructions}"
        )
        node_prompt = ChatPromptTemplate.from_messages([
            ("system", node_system_prompt),
            ("user", "Nội dung Quest hiện tại:\n{current_quest}\n\nÝ kiến đóng góp chỉnh sửa:\n\"{feedback}\"")
        ])
        node_chain = node_prompt | self.llm | node_parser
        updated_node = await node_chain.ainvoke({
            "node_id": node_id,
            "current_quest": str(current_quest),
            "feedback": feedback,
            "format_instructions": node_parser.get_format_instructions()
        })
        
        # 2. Sinh lại các rules liên quan trực tiếp đến các quyết định của Node mới này
        rules_system_prompt = (
            "Dựa trên thông tin của Node vừa được cập nhật dưới đây, hãy tạo danh sách các luật kiểm chứng chéo (rules) "
            "tương ứng cho các quyết định (decisions) của Node này.\n\n"
            "{format_instructions}"
        )
        rules_prompt = ChatPromptTemplate.from_messages([
            ("system", rules_system_prompt),
            ("user", "Thông tin Node đã cập nhật:\n{updated_node}")
        ])
        rules_chain = rules_prompt | self.llm | rules_parser
        updated_rules = await rules_chain.ainvoke({
            "updated_node": str(updated_node),
            "format_instructions": rules_parser.get_format_instructions()
        })
        
        return {
            "node": updated_node,
            "rules": updated_rules.get("rules", [])
        }
