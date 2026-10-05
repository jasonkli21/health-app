"""Domain-facing errors translated by the API boundary into stable responses."""


class ProfileNotFound(Exception):
    pass


class ProfileConflict(Exception):
    pass


class ProfileValidationError(Exception):
    pass


class DailyNotFound(Exception):
    pass


class DailyConflict(Exception):
    pass


class DailyValidationError(Exception):
    pass


class DailySnapshotLimitExceeded(Exception):
    pass


class PlanningNotFound(Exception):
    pass


class PlanningConflict(Exception):
    pass


class PlanningValidationError(Exception):
    pass
