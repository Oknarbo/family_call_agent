"""Exceptions safe for translation at application boundaries."""


class DomainError(Exception):
    """Base class carrying a stable code and user-safe Croatian text."""

    code = "domain_error"
    user_message = "Nešto nije u redu. Pokušaj ponovno."


class UnauthorizedError(DomainError):
    code = "unauthorized"
    user_message = "Nemaš dopuštenje za tu radnju."


class UnknownCallerError(UnauthorizedError):
    code = "unknown_caller"
    user_message = "Ovaj broj nije registriran za korištenje Zvonka. Doviđenja."


class InactiveCallerError(UnauthorizedError):
    code = "inactive_caller"
    user_message = "Ovaj broj trenutačno ne može koristiti Zvonka. Doviđenja."


class NotFoundError(DomainError):
    code = "not_found"
    user_message = "Nisam pronašao traženi podatak."


class ValidationError(DomainError):
    code = "validation_error"
    user_message = "Nisam dobro razumio tražene podatke."


class SchedulingInPastError(ValidationError):
    code = "scheduling_in_past"
    user_message = "To vrijeme je već prošlo. Kada želiš da te podsjetim?"


class DuplicateActionError(DomainError):
    code = "duplicate_action"
    user_message = "To je već zabilježeno."


class InventoryWouldBeNegativeError(ValidationError):
    code = "negative_inventory"
    user_message = "Stanje tableta ne može biti manje od nule."


class ConfirmationRequiredError(DomainError):
    code = "confirmation_required"
    user_message = "Prije toga trebam tvoju potvrdu."


class ProviderUnavailableError(DomainError):
    code = "provider_unavailable"
    user_message = "Ta usluga trenutačno nije dostupna."


class CallNotPlacedError(ProviderUnavailableError):
    """Provider/preflight positively reports that no call was placed."""

    code = "call_not_placed"
