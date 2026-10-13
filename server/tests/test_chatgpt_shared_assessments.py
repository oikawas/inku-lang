"""ChatGPT plan assessments are shared model settings, saved per model.

The author's instruction (2026-10-13): what a ChatGPT plan model is assessed to
be is held as common data, in the same keys as every other provider's, instead
of in each person's registration. An administrator saves it through
PUT /api/settings/models; an entry replaces that model's stored assessment and
leaves the others. Purposes are a person's choice and are not kept here.
"""

from inku_server.model_settings import chatgpt_assessments, default_model_settings, update_model_settings


def test_an_assessment_replaces_its_model_and_leaves_the_others():
    saved = update_model_settings(default_model_settings(), {"chatgpt_models": [
        {"id": "gpt-6-luna", "purposes": ["llm"], "recommendation_vision": 2, "comment_ja": "旧"},
        {"id": "gpt-6-sol", "recommendation_llm": 3, "speed_llm_seconds": 12.2},
    ]})
    again = update_model_settings(saved, {"chatgpt_models": [{"id": "gpt-6-luna", "comment_ja": "新"}]})
    assessments = chatgpt_assessments(again)
    assert assessments["gpt-6-luna"] == {"id": "gpt-6-luna", "label": "gpt-6-luna", "comment_ja": "新"}
    assert (assessments["gpt-6-sol"]["recommendation_llm"], assessments["gpt-6-sol"]["speed_llm_seconds"]) == (3, 12.2)
    assert all("purposes" not in model for model in again["chatgpt_models"])
