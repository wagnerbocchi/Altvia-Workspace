"""Native ticket state vocabulary and graph, independent of HTTP and storage."""

from typing import Literal

Status = Literal["new", "open", "pending_customer", "pending_third_party", "resolved", "closed"]
TICKET_TRANSITIONS = {
    "new": {"open"},
    "open": {"pending_customer", "pending_third_party", "resolved"},
    "pending_customer": {"open", "resolved"},
    "pending_third_party": {"open", "resolved"},
    "resolved": {"closed", "open"},
    "closed": {"open"},
}
