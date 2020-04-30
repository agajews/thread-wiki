class Action:
    ErrorHandler = None
    authorizers = []

    def __init__(self, page, *args, **kwargs):
        self.page = page
        self.setup(*args, **kwargs)

    def authorize(self):
        for authorizer in self.authorizers:
            authorizer()

    def execute(self):
        pass

    def run(self):
        self.authorize()
        self.execute()
        return self.respond()

    @property
    def params(self):
        return request.get_json(silent=True)

    def require(self, param, cls=None):
        if param not in self.params:
            raise Malformed()
        val = self.params[param]
        if cls is not None:
            return self.cast(val, cls)
        return val

    def cast(self, val, cls):
        try:
            val = cls(val)
        except Exception:
            raise Malformed()
        return val


def reload(self):
    return jsonify({"redirect": get_param("href")})


def redirect(href):
    def respond(self):
        return jsonify({"redirect": href})

    return respond


def can_edit(self):
    if g.user is None or not g.user.can_edit(self.page):
        raise NotAllowed()


def is_owner(self):
    if g.user is None or not g.user.is_owner(self.page):
        raise NotAllowed()


def check_race(self):
    if len(self.page.versions) != self.require("num_versions", int):
        raise RaceCondition()


class PageAction(Action):
    def run(self):
        try:
            super().run()
        except RaceCondition:
            self.error_message(
                "Lel, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening the edit page in a new tab)."
            )
        except EmptyEdit:
            self.error_message("Lel, doesn't look like you changed anything.")
        except FlagYourself:
            self.error_message("Lel, can't flag yourself.")
        except AlreadyFlagged:
            self.error_message("Lel, someone else flagged this already.")
        except NotAllowed:
            self.error_message("Lel, looks like you're not allowed to do that.")


class UserPageAction(PageAction):
    def run(self):
        try:
            super().run()
        except DuplicateKey:
            self.error_message(
                "Lel, someone with the same name already has that nickname!"
            )


class TopicPageAction(PageAction):
    def run(self):
        try:
            super().run()
        except DuplicateKey:
            self.error_message("Lel, a page with that name already exists!")
