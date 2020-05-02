class UserError(Exception):
    pass


class RaceCondition(UserError):
    pass


class DuplicatePage(UserError):
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


class UserNotFound(UserError):
    pass


class IncorrectPassword(UserError):
    pass


class Malformed(UserError):
    pass
