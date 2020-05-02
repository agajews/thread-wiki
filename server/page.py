from .sections import Section, SectionDiff, separate_sections, diff_sections
from .html_utils import markup_changes
from .user import User


class Page(MongoModel):
    titles = fields.ListField(fields.CharField())
    freshness = fields.IntegerField(default=0)

    def save_if_fresh(self):
        old_freshness = self.freshness
        self.freshness += 1
        try:
            update = self._mongometa.collection.replace_one(
                {"_id": self._id, "freshness": old_freshness}, self.to_son()
            )
        except DuplicateKeyError:
            raise DuplicatePage()
        if update.modified_count == 0:
            raise RaceCondition()

    def add_title(self, title):
        if title in self.titles:
            self.titles.remove(version.title)
        self.titles.append(version.title)

    @classmethod
    def find(title):
        try:
            return Page.objects.get({"titles": title})
        except DoesNotExist:
            raise PageNotFound()


class Version(MongoModel):
    page = fields.ReferenceField(Page)
    timestamp = fields.DateTimeField()
    editor = fields.ReferenceField(User)
    flag = fields.ReferenceField(Flag, default=None)

    def flag(self):
        assert g.user is not None
        assert self.flag is None
        self.flag = Flag(sender=g.user, timestamp=timestamp(), version=self)
        try:
            self.flag.save()
        except DuplicateKeyError:
            raise AlreadyFlagged()
        self.save()
        self.editor.add_flag(self.flag)

    def unflag(self):
        assert self.flag is not None
        assert g.user == self.flag.sender
        flag = self.flag
        self.flag = None
        self.save()
        flag.delete()


class VersionDiff(MongoModel):
    version_a = fields.ReferenceField(Version)
    version_b = fields.ReferenceField(Version)
