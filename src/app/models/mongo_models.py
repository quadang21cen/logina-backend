from datetime import datetime
from typing import List, Dict, Any, Optional
from beanie import Document
from pydantic import Field

# --- MongoDB: Quest Config & Package ---
class KnowledgePack(Document):
    title: str
    content: str
    resources: List[Dict[str, Any]] = []  # S3 File Links, Chart Data, Maps, etc.

class RoleCard(Document):
    role_name: str
    description: str
    objectives: List[str]

class ScenarioNode(Document):
    node_id: str
    title: str
    description: str
    decisions: List[Dict[str, Any]]  # List of decision options (with ID, text, etc.)
    evidence_options: List[Dict[str, Any]]  # List of available evidence items

class Quest(Document):
    title: str
    description: str
    creator_id: int  # Relates to User.id in Postgres
    is_published: bool = Field(default=False)
    knowledge_pack: Optional[Dict[str, Any]] = None
    role_card: Optional[Dict[str, Any]] = None
    scenario_nodes: List[Dict[str, Any]] = []
    rules: List[Dict[str, Any]] = []  # JSONLogic rules
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "quests"

# --- MongoDB: Event Behavior Logs (Time-series log) ---
class EventLog(Document):
    run_id: int  # Relates to QuestRun.id in Postgres
    student_id: int  # Relates to User.id in Postgres
    event_type: str  # READ_DATA, SELECT_EVIDENCE, SUBMIT_DECISION, etc.
    payload: Dict[str, Any]  # Details of the action
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "event_logs"
