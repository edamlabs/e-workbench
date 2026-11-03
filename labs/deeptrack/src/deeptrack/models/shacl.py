"""models.shacl: the SHACL report Open Ontologies' `onto_shacl` returns, the slice the gate reads."""

import msgspec


class Violation(msgspec.Struct, frozen=True, kw_only=True):
    """One broken constraint: which, on which node, along which path, and the shape's own message."""

    constraint: str
    focus_node: str
    message: str = ""
    path: str = ""
    severity: str = ""


class ShaclReport(msgspec.Struct, frozen=True, kw_only=True):
    """The verdict over the whole store: conforms, and every violation when it does not."""

    conforms: bool
    violation_count: int = 0
    violations: tuple[Violation, ...] = ()

    @property
    def text(self) -> str:
        """The violations as the lines the agent reads back when the gate returns its proposal."""
        return "\n".join(f"- {each.message or each.constraint} ({each.focus_node})" for each in self.violations)
