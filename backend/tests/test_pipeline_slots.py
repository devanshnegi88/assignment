from app.services.pipeline import slots_to_constraints
from app.retrieval.hybrid import RetrievalConstraints


def test_slots_to_constraints_maps_seniority_and_purpose():
    slots = {"seniority": "mid-level", "assessment_purpose": "selection", "technical_skills": ["sql"]}
    constraints = slots_to_constraints(slots)
    assert isinstance(constraints, RetrievalConstraints)
    assert "Mid-Professional" in constraints.job_levels
    assert "K" in constraints.test_type_codes
    assert "A" in constraints.test_type_codes


def test_slots_to_constraints_handles_personality_and_competencies():
    slots = {"personality_requirements": ["openness"], "competencies": ["communication"]}
    constraints = slots_to_constraints(slots)
    assert "P" in constraints.test_type_codes
    assert "C" in constraints.test_type_codes
