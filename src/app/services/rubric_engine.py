from typing import List, Dict, Any

class RubricEngine:
    @staticmethod
    def calculate_scores(game_state: Dict[str, Any], total_nodes: int) -> Dict[str, float]:
        """
        Tính toán điểm 4 trục năng lực (thang điểm 100):
        1. Knowledge (Kiến thức): Tỉ lệ đọc tài liệu học tập và chọn đúng bằng chứng khoa học.
        2. Evidence (Bằng chứng): Tỉ lệ bằng chứng được đính kèm phù hợp trên tổng số quyết định.
        3. Decision (Quyết định): Tỉ lệ quyết định tối ưu đã chọn.
        4. Consistency (Tính nhất quán): Bị trừ điểm dựa trên số lỗi mâu thuẫn (CONTRADICTION) bị phạt.
        """
        completed_nodes = game_state.get("completed_nodes", {})
        
        # Nếu chưa làm node nào, cho 0 điểm
        if not completed_nodes or total_nodes == 0:
            return {
                "knowledge": 0.0,
                "evidence": 0.0,
                "decision": 0.0,
                "consistency": 0.0
            }
            
        nodes_count = len(completed_nodes)
        
        # 1. Trục Decision & Evidence cơ bản
        decision_score = (nodes_count / total_nodes) * 100
        
        evidence_submitted_count = 0
        contradiction_count = 0
        weak_evidence_count = 0
        
        for node_id, data in completed_nodes.items():
            evidences = data.get("selected_evidence_ids", [])
            flags = data.get("flags", [])
            
            if len(evidences) > 0:
                evidence_submitted_count += 1
                
            for flag in flags:
                severity = flag.get("severity")
                if severity == "CONTRADICTION":
                    contradiction_count += 1
                elif severity == "WEAK_EVIDENCE":
                    weak_evidence_count += 1

        # Trục Evidence: Tỉ lệ có chọn bằng chứng bảo vệ
        evidence_score = (evidence_submitted_count / nodes_count) * 100
        
        # Trục Knowledge: Phạt nhẹ dựa trên việc thiếu bằng chứng khoa học vững chắc
        knowledge_penalty = weak_evidence_count * 15
        knowledge_score = max(0.0, 100.0 - knowledge_penalty)
        
        # Trục Consistency: Phạt nặng dựa trên số lỗi mâu thuẫn trực tiếp
        consistency_penalty = contradiction_count * 25
        consistency_score = max(0.0, 100.0 - consistency_penalty)
        
        return {
            "knowledge": round(knowledge_score, 2),
            "evidence": round(evidence_score, 2),
            "decision": round(decision_score, 2),
            "consistency": round(consistency_score, 2)
        }
