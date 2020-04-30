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


class PageNotFound(Exception):
    pass


class VersionNotFound(Exception):
    pass


class Malformed(Exception):
    pass


class PageErrorHandler:
    RaceCondition =
    EmptyEdit =
    FlagYourself =
    AlreadyFlagged = "Lel, someone else flagged this already."
    NotAllowed = "Lel, looks like you're not allowed to do that."


class UserPageErrorHandler(PageErrorHandler):
    DuplicateKey = "Lel, someone with the same name already has that nickname!"


class TopicPageErrorHandler(PageErrorHandler):
    DuplicateKey = "Lel, a page with that name already exists!"
