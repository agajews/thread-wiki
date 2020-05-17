from pymodm import fields, MongoModel, EmbeddedMongoModel
from pymodm.errors import DoesNotExist
from pymongo import ASCENDING, TEXT
from pymongo.errors import DuplicateKeyError
from pymongo.operations import IndexModel
from flask import g

from .sections import Section, SectionDiff, separate_sections, diff_sections
from .html_utils import markup_changes
from .app import timestamp
from .errors import *


class Page(MongoModel):
    titles = fields.ListField(fields.CharField())
    freshness = fields.IntegerField(default=0)
    search_terms = fields.ListField(fields.CharField())
    last_edited = fields.DateTimeField(default=0)

    class Meta:
        indexes = [
            IndexModel("titles", unique=True),
            IndexModel([("search_terms", TEXT)]),
        ]

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
            self.titles.remove(title)
        self.titles.append(title)

    def add_search_term(self, term):
        if term not in self.search_terms:
            self.search_terms.append(term)

    def trigger_backlinks(self, new_links):
        for link in new_links:
            try:
                page = Page.find(link)
            except PageNotFound:
                pass
            if page.can_edit:
                try:
                    page.add_backlink(self.titles)
                except RaceCondition:
                    # would be nice to still make the link eventually hmm...
                    pass

    @property
    def title(self):
        return self.titles[-1]

    @staticmethod
    def find(title):
        try:
            return Page.objects.get({"titles": title})
        except DoesNotExist:
            raise PageNotFound()

    @staticmethod
    def search(query, limit=20):
        return list(Page.objects.raw({"$text": {"$search": query}}).limit(limit))


class PageVersion(MongoModel):
    page = fields.ReferenceField(Page)
    timestamp = fields.DateTimeField()
    editor = fields.ReferenceField("User")
    flag = fields.EmbeddedDocumentField("Flag")
    is_flagged = fields.BooleanField(default=False)
    links = fields.ListField(fields.CharField(), default=[], blank=True)

    class Meta:
        indexes = [IndexModel([("editor", ASCENDING), ("is_flagged", ASCENDING)])]

    def set_flag(self):
        assert g.user is not None
        assert not self.is_flagged
        assert g.user != self.editor
        self.flag = Flag(sender=g.user, timestamp=timestamp(), version=self)
        modified_count = PageVersion.objects.raw(
            {"_id": self._id, "is_flagged": False}
        ).update({"$set": {"flag": self.flag.to_son(), "is_flagged": True}})
        if modified_count == 0:
            raise AlreadyFlagged()

    def set_unflag(self):
        assert self.is_flagged
        assert g.user == self.flag.sender
        PageVersion.objects.raw({"_id": self._id}).update(
            {"$set": {"flag": None, "is_flagged": False}}
        )


class VersionDiff(MongoModel):
    version_a = fields.ReferenceField(PageVersion)
    version_b = fields.ReferenceField(PageVersion)


class Flag(EmbeddedMongoModel):
    version = fields.ReferenceField(PageVersion)
    sender = fields.ReferenceField("User")
    timestamp = fields.DateTimeField()
