# Business Rules Registry


class BusinessRuleRegistry:
    def __init__(self):
        self._rules = {}

    def register(self, name: str, condition: callable, action: callable, priority: int = 0):
        raise NotImplementedError("Implement in Phase 8")

    def get_applicable(self, fields: dict) -> list[dict]:
        raise NotImplementedError("Implement in Phase 8")
