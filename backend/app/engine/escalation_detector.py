"""EscalationDetector: determines whether to use primary or fallback model.

Evaluates user messages against configurable heuristics to decide whether
the primary model is sufficient or the message should be routed to the
fallback (stronger) model.  The evaluation is fully deterministic — the
same ``message`` and ``conversation_depth`` always produce the same
:class:`EscalationDecision`.

Heuristics (all configurable):

* **Message length** — messages exceeding ``length_threshold`` characters
  suggest complex tasks and trigger escalation.
* **Complexity keywords** — presence of keywords like ``"analyze"``,
  ``"compare"``, ``"explain in detail"``, ``"step by step"``,
  ``"debug"``, ``"refactor"`` triggers escalation.
* **Conversation depth** — conversations exceeding
  ``context_depth_threshold`` turns may benefit from a stronger model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_COMPLEXITY_KEYWORDS: list[str] = [
    "analyze",
    "compare",
    "explain in detail",
    "step by step",
    "debug",
    "refactor",
]


@dataclass
class EscalationDecision:
    """Result of an escalation evaluation.

    Attributes:
        should_escalate: ``True`` when the message should be routed to
            the fallback model.
        reason: Human-readable explanation of why escalation was (or was
            not) triggered.
        was_error_retry: ``True`` when escalation is due to a primary
            model error rather than heuristic evaluation.  Defaults to
            ``False``; set by the caller when retrying after a primary
            model failure.
    """

    should_escalate: bool
    reason: str
    was_error_retry: bool = False


class EscalationDetector:
    """Determines whether to use primary or fallback model.

    Args:
        length_threshold: Minimum message length (in characters) that
            triggers escalation.  Defaults to ``500``.
        complexity_keywords: List of keywords whose presence in the
            message triggers escalation.  Defaults to a built-in list
            including ``"analyze"``, ``"compare"``, ``"explain in detail"``,
            ``"step by step"``, ``"debug"``, and ``"refactor"``.
        context_depth_threshold: Minimum conversation depth (number of
            turns) that triggers escalation.  Defaults to ``20``.
    """

    def __init__(
        self,
        length_threshold: int = 500,
        complexity_keywords: list[str] | None = None,
        context_depth_threshold: int = 20,
    ) -> None:
        self.length_threshold = length_threshold
        self.complexity_keywords = (
            complexity_keywords
            if complexity_keywords is not None
            else list(_DEFAULT_COMPLEXITY_KEYWORDS)
        )
        self.context_depth_threshold = context_depth_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self, message: str, conversation_depth: int
    ) -> EscalationDecision:
        """Evaluate whether the message requires the fallback model.

        The evaluation is deterministic: the same *message* and
        *conversation_depth* always produce the same result.

        Args:
            message: The user message text to evaluate.
            conversation_depth: The current number of turns in the
                conversation.

        Returns:
            An :class:`EscalationDecision` indicating whether to
            escalate and why.
        """
        reasons: list[str] = []

        if len(message) > self.length_threshold:
            reasons.append(
                f"message length ({len(message)}) exceeds threshold "
                f"({self.length_threshold})"
            )

        matched_keywords = self._find_complexity_keywords(message)
        if matched_keywords:
            kw_display = ", ".join(f'"{kw}"' for kw in matched_keywords)
            reasons.append(f"complexity keywords detected: {kw_display}")

        if conversation_depth > self.context_depth_threshold:
            reasons.append(
                f"conversation depth ({conversation_depth}) exceeds threshold "
                f"({self.context_depth_threshold})"
            )

        if reasons:
            reason = "; ".join(reasons)
            logger.debug("Escalation triggered: %s", reason)
            return EscalationDecision(should_escalate=True, reason=reason)

        return EscalationDecision(
            should_escalate=False,
            reason="no escalation heuristics triggered",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_complexity_keywords(self, message: str) -> list[str]:
        """Return the subset of configured keywords found in *message*.

        Matching is case-insensitive.  Keywords are checked in
        configuration order so that the result is deterministic.
        """
        lower_message = message.lower()
        return [kw for kw in self.complexity_keywords if kw.lower() in lower_message]
