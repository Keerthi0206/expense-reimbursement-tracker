"""
Per-category budget thresholds. Exceeding one doesn't block a request --
some legitimate expenses genuinely cost more than usual -- it just surfaces
a warning to the requester at creation time and a visible flag to reviewers.

Fixed in code rather than admin-editable, to keep this scoped for the
hackathon timeline. A real version would move this into the database with
an admin UI to edit it.
"""

CATEGORY_BUDGET_LIMITS = {
    "travel": 800.0,
    "meals": 150.0,
    "office_supplies": 300.0,
    "software_subscriptions": 500.0,
    "event_expenses": 1000.0,
    "training": 600.0,
    "other": 300.0,
}

DEFAULT_BUDGET_LIMIT = 300.0


def get_budget_limit(category: str) -> float:
    return CATEGORY_BUDGET_LIMITS.get(category, DEFAULT_BUDGET_LIMIT)


def exceeds_budget(category: str, amount: float) -> bool:
    return amount > get_budget_limit(category)
