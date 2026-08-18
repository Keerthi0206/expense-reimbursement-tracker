"""
Small rules engine deciding when a request needs a second approval tier,
beyond the normal single-reviewer approval. Two rule types, checked in
order -- either one triggers the second tier:

  1. Amount threshold: anything over SECOND_APPROVAL_AMOUNT_THRESHOLD
  2. Category rule: certain categories always need it regardless of amount
     (training/professional-development expenses commonly need a second
     sign-off in real organizations, independent of cost)

Fixed in code rather than admin-editable, same scoping decision as
core/budget.py -- a real version would move this into the database with
an admin UI to edit the rules.
"""
import os

SECOND_APPROVAL_AMOUNT_THRESHOLD = float(os.getenv("SECOND_APPROVAL_AMOUNT_THRESHOLD", "500"))
SECOND_APPROVAL_CATEGORIES = {"training"}


def requires_second_approval(category: str, amount: float) -> bool:
    if category in SECOND_APPROVAL_CATEGORIES:
        return True
    return amount > SECOND_APPROVAL_AMOUNT_THRESHOLD
