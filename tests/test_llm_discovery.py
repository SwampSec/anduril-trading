import pytest

from llm.discovery import is_auto_model, pick_model_id


@pytest.mark.unit
def test_auto_model_tokens():
    assert is_auto_model("")
    assert is_auto_model("auto")
    assert is_auto_model("AUTO")
    assert is_auto_model("local-model")
    assert not is_auto_model("qwen-7b")


@pytest.mark.unit
def test_pick_model_auto_single():
    assert pick_model_id(["model-a"], "auto") == "model-a"


@pytest.mark.unit
def test_pick_model_auto_multiple_uses_first():
    assert pick_model_id(["model-a", "model-b"], "auto") == "model-a"


@pytest.mark.unit
def test_pick_model_explicit():
    assert pick_model_id(["model-a", "model-b"], "model-b") == "model-b"


@pytest.mark.unit
def test_pick_model_explicit_missing_raises():
    with pytest.raises(RuntimeError, match="not loaded"):
        pick_model_id(["model-a"], "model-b")


@pytest.mark.unit
def test_pick_model_empty_list_raises():
    with pytest.raises(RuntimeError, match="no models"):
        pick_model_id([], "auto")
