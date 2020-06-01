from pymodm import fields, MongoModel
from pymodm.errors import DoesNotExist
from pymongo.errors import DuplicateKeyError
from pymongo.operations import IndexModel
from flask import g, render_template
from urllib.parse import urljoin

from .app import timestamp, url_for
from .html_utils import markup_changes, linkify_page, sanitize_html
from .sections import diff_sections, separate_sections, Section, SectionDiff
from .errors import *


class BookmarksPage(MongoModel):
    user = fields.ReferenceField("User")
    versions = fields.ListField(fields.ReferenceField("BookmarksVersion"))
    diffs = fields.ListField(fields.ReferenceField("BookmarksDiff"))

    class Meta:
        indexes = [IndexModel("user", unique=True)]

    def add_version(self, version):
        diff = BookmarksDiff.compute(self.latest, version)
        print("version", version.summary)
        print("diff", diff.summary)
        print("actual diff", diff.summary_diff)
        if diff.is_empty:
            raise EmptyEdit()
        version.save()
        diff.save()
        self.versions.append(version)
        self.diffs.append(diff)
        self.save()

    @property
    def latest(self):
        return self.versions[-1]

    def add_bookmark(self, title):
        sections = self.latest.sections[:]
        url = urljoin("https://thread.wiki/", url_for("page", title=title))
        body = sanitize_html("<div>{}</div>".format(url))
        if len(sections) == 0:
            sections.append(Section(heading="Unsorted bookmarks", level=2, body=body))
        else:
            sections[-1] = Section(
                heading=sections[-1].heading,
                level=sections[-1].level,
                body=sections[-1].body + body,
            )
        return self.edit(sections, self.latest.summary)

    def is_bookmarked(self, titles):
        if set(titles).intersection(self.latest.links):
            return True
        return False

    def edit(self, sections, summary):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = BookmarksVersion(
            page=self,
            timestamp=timestamp(),
            sections=sections,
            summary=summary,
            links=links,
        )
        self.add_version(version)

    def restore(self, num):
        assert 0 <= num < len(self.versions) - 1
        version = self.versions[num]
        self.edit(version.sections, version.summary)

    @staticmethod
    def create_or_return(sections, summary):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = BookmarksVersion(
            sections=sections, summary=summary, timestamp=timestamp(), links=links,
        )
        empty_version = BookmarksVersion(sections=[], summary="")
        diff = BookmarksDiff.compute(empty_version, version)
        empty_version.save()
        version.save()
        diff.save()
        page = BookmarksPage(versions=[version], diffs=[diff], user=g.user)
        try:
            page.save()
        except DuplicateKeyError:
            empty_version.delete()
            version.delete()
            diff.delete()
            return BookmarksPage.objects.get({"user": g.user._id})
        empty_version.page = page
        version.page = page
        empty_version.save()
        version.save()
        return page

    @staticmethod
    def find():
        assert g.user is not None
        try:
            return BookmarksPage.objects.get({"user": g.user._id})
        except DoesNotExist:
            summary, sections = separate_sections(
                render_template("bookmarks-template.html")
            )
            return BookmarksPage.create_or_return(sections, summary)


class BookmarksVersion(MongoModel):
    page = fields.ReferenceField(BookmarksPage)
    timestamp = fields.DateTimeField()
    sections = fields.EmbeddedDocumentListField(Section, blank=True)
    summary = fields.CharField(blank=True)
    links = fields.ListField(fields.CharField(), default=[], blank=True)


class BookmarksDiff(MongoModel):
    version_a = fields.ReferenceField(BookmarksVersion)
    version_b = fields.ReferenceField(BookmarksVersion)

    sections = fields.EmbeddedDocumentListField(SectionDiff, blank=True)
    summary = fields.CharField(blank=True)
    summary_diff = fields.CharField(blank=True)
    summary_changed = fields.BooleanField()

    @property
    def is_empty(self):
        return not (
            self.summary_changed
            or any(not section.is_empty for section in self.sections)
        )

    @staticmethod
    def compute(version_a, version_b):
        sections = diff_sections(version_a.sections, version_b.sections)
        summary_diff = markup_changes(version_a.summary, version_b.summary)
        return BookmarksDiff(
            version_a=version_a,
            version_b=version_b,
            sections=sections,
            summary=version_b.summary,
            summary_diff=summary_diff,
            summary_changed=version_a.summary != version_b.summary,
        )
