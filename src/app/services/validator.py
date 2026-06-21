import json
from typing import List, Dict, Any, Tuple

class CrossCheckValidator:
    @staticmethod
    def evaluate_rule(rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """
        Thực thi một rule logic.
        Dữ liệu truyền vào (data) thường có cấu trúc:
        {
            "decision_id": "dec_solar",
            "selected_evidence_ids": ["ev_solar_clean", "ev_price"]
        }
        Cấu trúc rule mẫu:
        {
            "decision_id": "dec_solar",
            "required_evidence_ids": ["ev_solar_clean"],
            "severity": "CONTRADICTION",
            "message": "Bạn chọn pin mặt trời nhưng thiếu bằng chứng về mức độ sạch của nó."
        }
        """
        rule_decision = rule.get("decision_id")
        
        # Nếu rule này áp dụng cho quyết định khác, bỏ qua (coi như pass)
        if rule_decision and rule_decision != data.get("decision_id"):
            return True
            
        required_evidences = rule.get("required_evidence_ids", [])
        selected_evidences = data.get("selected_evidence_ids", [])
        
        # Kiểm tra xem toàn bộ bằng chứng bắt buộc có nằm trong các bằng chứng học sinh đã chọn không
        # Nếu thiếu bất kỳ bằng chứng bắt buộc nào, rule bị vi phạm (trả về False)
        for req_ev in required_evidences:
            if req_ev not in selected_evidences:
                return False
                
        return True

    @classmethod
    def validate_action(
        cls, 
        rules: List[Dict[str, Any]], 
        decision_id: str, 
        selected_evidence_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Đối soát toàn bộ các rule và trả về các Flags cảnh báo lỗi tư duy nếu có.
        """
        flags = []
        data = {
            "decision_id": decision_id,
            "selected_evidence_ids": selected_evidence_ids
        }
        
        for rule in rules:
            is_valid = cls.evaluate_rule(rule, data)
            if not is_valid:
                flags.append({
                    "rule_id": rule.get("rule_id"),
                    "severity": rule.get("severity", "WEAK_EVIDENCE"),
                    "message": rule.get("message", "Thiếu bằng chứng xác thực cho quyết định này.")
                })
                
        return flags
