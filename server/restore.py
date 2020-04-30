from .action import PageAction, reload, can_edit, check_race


class RestoreVersion(PageAction):
    authorizers = [can_edit, check_race]

    def setup(self, num):
        self.num = num

    def execute(self):
        self.page.restore_version(self.num)

    respond = reload
