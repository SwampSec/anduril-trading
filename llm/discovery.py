from __future__ import annotations

AUTO_MODEL_VALUES = frozenset({"", "auto", "local-model"})


def is_auto_model(configured: str) -> bool:
    return configured.strip().lower() in AUTO_MODEL_VALUES


def pick_model_id(model_ids: list[str], configured: str) -> str:
    if not model_ids:
        raise RuntimeError(
            "LM Studio returned no models. Load a model and start the local server."
        )

    if not is_auto_model(configured):
        target = configured.strip()
        if target not in model_ids:
            raise RuntimeError(
                f"LMSTUDIO_MODEL={target!r} is not loaded. "
                f"Available: {', '.join(model_ids[:5])}"
            )
        return target

    if len(model_ids) == 1:
        return model_ids[0]

    return model_ids[0]
