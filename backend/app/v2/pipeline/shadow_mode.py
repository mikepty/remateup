# Shadow Mode — Runs V2 alongside V1 for comparison without side effects


class ShadowModeCoordinator:
    def __init__(self, pipeline_v1, pipeline_v2):
        self._v1 = pipeline_v1
        self._v2 = pipeline_v2
        self._enabled = False

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def run_shadow(self, document_paths: list[str], pais: str) -> dict:
        raise NotImplementedError("Implement in Phase 14 (after V2 pipeline is complete)")
