from .sections import Section, SectionDiff, separate_sections, diff_sections
from .html_utils import markup_changes
from .user import User


class Page(MongoModel):
    titles = fields.ListField(fields.CharField())
    freshness = fields.IntegerField(default=0)

    def save_if_fresh(self):
        old_freshness = self.freshness
        self.freshness += 1
        update = self._mongometa.collection.replace_one(
            {"_id": self._id, "freshness": old_freshness}, self.to_son()
        )
        if update.modified_count == 0:
            raise RaceCondition()

    def add_title(self, title):
        if title in self.titles:
            self.titles.remove(version.title)
        self.titles.append(version.title)


class Version(MongoModel):
    page = fields.ReferenceField(Page)
    timestamp = fields.DateTimeField()
    editor = fields.ReferenceField(User)
    flag = fields.EmbeddedDocumentField(Flag)

    def 


class VersionDiff(MongoModel):
    version_a = fields.ReferenceField(Version)
    version_b = fields.ReferenceField(Version)
