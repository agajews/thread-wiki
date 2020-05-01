class UserError(Exception):
    pass


class RaceCondition(UserError):
    pass


class DuplicateKey(UserError):
    pass


class EmptyEdit(UserError):
    pass


class FlagYourself(UserError):
    pass


class AlreadyFlagged(UserError):
    pass


class NotAllowed(UserError):
    pass


class PageNotFound(UserError):
    pass


class VersionNotFound(UserError):
    pass


class Malformed(UserError):
    pass
