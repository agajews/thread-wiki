from .action import UserPageAction, reload, is_owner


class Freeze(UserPageAction):
    authorizers = [is_owner]

    def execute(self):
        self.page.freeze()

    respond = reload


class Unfreeze(UserPageAction):
    authorizers = [is_owner]

    def execute(self):
        self.page.unfreeze()

    respond = reload
