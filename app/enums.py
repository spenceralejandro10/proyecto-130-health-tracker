from enum import StrEnum


class DataOrigin(StrEnum):
    MEASURED = "measured"
    DEVICE_ESTIMATED = "device_estimated"
    SYSTEM_CALCULATED = "system_calculated"
    SELF_REPORTED = "self_reported"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


class ValidationStatus(StrEnum):
    CONFIRMED = "confirmed"
    ESTIMATED = "estimated"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    DISCARDED = "discarded"


class ReminderAction(StrEnum):
    DONE = "done"
    SNOOZE = "snooze"
    DISMISS = "dismiss"
