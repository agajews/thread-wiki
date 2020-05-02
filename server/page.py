from pymodm import fields, MongoModel, EmbeddedMongoModel
from pymodm.errors import DoesNotExist
from pymongo.errors import DuplicateKeyError
from pymongo.operations import IndexModel

from .sections import Section, SectionDiff, separate_sections, diff_sections
from .html_utils import markup_changes
from .user import User
from .app import timestamp
from .errors import *


class Page(MongoModel):
    # TODO: markup indexes
    titles = fields.ListField(fields.CharField())
    freshness = fields.IntegerField(default=0)

    class Meta:
        indexes = [IndexModel("titles", unique=True)]

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

    @property
    def title(self):
        return self.titles[-1]

    @staticmethod
    def find(title):
        try:
            return Page.objects.get({"titles": title})
        except DoesNotExist:
            raise PageNotFound()


class Version(MongoModel):
    page = fields.ReferenceField(Page)
    timestamp = fields.DateTimeField()
    editor = fields.ReferenceField(User)
    flag = fields.EmbeddedDocumentField(Flag, default=None)
    is_flagged = fields.BooleanField()  # just bookkeeping for the index

    class Meta:
        indexes = [IndexModel([("editor", ASCENDING), ("is_flagged", ASCENDING)])]

    def flag(self):
        assert g.user is not None
        assert self.flag is None
        self.flag = Flag(sender=g.user, timestamp=timestamp(), version=self)
        update = Version.objects.raw({"_id": self._id, "flag": None}).update(
            {"flag": self.flag.to_son(), "is_flagged": True}
        )
        if update.modified_count == 0:
            raise AlreadyFlagged()

    def unflag(self):
        assert self.flag is not None
        assert g.user == self.flag.sender
        Version.objects.raw({"_id": self._id}).update(
            {"flag": None, "is_flagged": False}
        )


class VersionDiff(MongoModel):
    version_a = fields.ReferenceField(Version)
    version_b = fields.ReferenceField(Version)


class Flag(EmbeddedMongoModel):
    version = fields.ReferenceField(Version)
    sender = fields.ReferenceField(User)
    timestamp = fields.DateTimeField()
