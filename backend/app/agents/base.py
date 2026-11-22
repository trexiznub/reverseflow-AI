"""Agent interface shared by the six REVERSEFLOW agents.

Each agent is a node with explicit inputs, outputs and dependencies. The
orchestrator executes them as a dependency graph (LangGraph-style state graph,
implemented here without the dependency so the demo runs offline).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session


@dataclass
class AgentContext:
    db: Session
    run_id: str
    trigger: str
    event: dict
    scenario_date: date
    settings: dict
    state: dict = field(default_factory=dict)  # agent_id -> outputs
    messages: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)

    def send(self, sender: str, receiver: str, topic: str, payload: dict):
        self.messages.append({"ts": datetime.now(), "sender": sender, "receiver": receiver, "topic": topic, "payload": payload})


@dataclass
class AgentResult:
    outputs: dict
    recommendations: list = field(default_factory=list)
    alerts: list = field(default_factory=list)


class Agent:
    id: str = ""
    name: str = ""
    group: str = ""
    purpose: str = ""
    inputs: list[str] = []
    depends_on: list[str] = []
    models: list[str] = []

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        return {"id": self.id, "name": self.name, "group": self.group, "purpose": self.purpose, "inputs": self.inputs,
                "depends_on": self.depends_on, "models": self.models}


def rec(kind: str, title: str, rationale: str, evidence: dict, entity_type: str, entity_id: str, *, impact: float = 0,
        cost: float = 0, confidence: float = 0.7, priority: str = "medium", source: str = "template") -> dict:
    return {"kind": kind, "title": title, "rationale": rationale, "evidence": evidence, "entity_type": entity_type,
            "entity_id": entity_id, "impact_inr": round(float(impact), 2), "cost_inr": round(float(cost), 2),
            "confidence": round(float(confidence), 3), "priority": priority, "explanation_source": source}


def alert(severity: str, audience: str, title: str, body: str, entity_type: str, entity_id: str, scope_id: str | None = None) -> dict:
    return {"severity": severity, "audience": audience, "title": title, "body": body, "entity_type": entity_type,
            "entity_id": entity_id, "scope_id": scope_id}
