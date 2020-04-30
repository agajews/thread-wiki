from .action import PageAction, reload


class FlagVersion(PageAction):
    authorizers = [can_edit]

    def setup(self, num):
        self.num = num

    def execute(self):
        self.page.flag_version(self.num)

    respond = reload


class UnflagVersion(PageAction):
    def setup(self, num):
        self.num = num

    def authorize(self):
        if g.user is None:
            raise NotAllowed()
        flag = self.page.versions[self.num].flag
        if flag is None:
            raise NotAllowed()
        if not flag.sender == g.user._id:
            raise NotAllowed()

    def execute(self):
        self.page.unflag_version(self.num)

    respond = reload


class FlagAndUndoVersion(PageAction):
    authorizers = [can_edit]

    def execute(self):
        num_to_flag = len(self.page.versions) - 1
        num_to_restore = num_to_flag - 1
        self.page.restore_version(num_to_restore)
        self.page.flag_version(num_to_flag)

    respond = reload
