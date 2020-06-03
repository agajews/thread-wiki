from pymodm import fields, MongoModel, EmbeddedMongoModel
from pymongo.errors import DuplicateKeyError
from flask import g

from .page import Page, PageVersion, VersionDiff
from .bookmarks import BookmarksPage
from .html_utils import markup_changes, name_to_title, linkify_page, sanitize_html
from .sections import diff_sections, Section, SectionDiff
from .app import timestamp, url_for, absolute_url
from .errors import *


class TopicPage(Page):
    versions = fields.ListField(fields.ReferenceField("TopicVersion"))
    diffs = fields.ListField(fields.ReferenceField("TopicVersionDiff"))

    @property
    def name(self):
        return self.versions[-1].name

    def add_version(self, version, backlink=True):
        diff = TopicVersionDiff.compute(self.latest, version)
        if diff.is_empty:
            raise EmptyEdit()
        new_links = set(version.links).difference(self.latest.links)
        version.save()
        diff.save()
        self.versions.append(version)
        self.diffs.append(diff)
        self.add_title(version.title)
        self.add_search_term(version.name)
        self.last_edited = version.timestamp
        try:
            self.save_if_fresh()
        except (RaceCondition, DuplicatePage):
            version.delete()
            diff.delete()
            raise
        if backlink:
            self.trigger_backlinks(new_links)

    @property
    def latest(self):
        return self.versions[-1]

    def add_backlink(self, titles):
        if set(titles).intersection(self.latest.links):
            return
        sections = self.latest.sections[:]
        url = absolute_url(url_for("page", title=titles[-1]))
        body = sanitize_html("<div>{}</div>".format(url))
        if len(sections) == 0:
            sections.append(Section(heading="Unsorted links", level=2, body=body))
        else:
            sections[-1] = Section(
                heading=sections[-1].heading,
                level=sections[-1].level,
                body=sections[-1].body + body,
            )
        return self.edit(
            sections, self.latest.summary, self.latest.name, backlink=False
        )

    def edit(self, sections, summary, name, backlink=True):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = TopicVersion(
            page=self,
            timestamp=timestamp(),
            editor=g.user,
            sections=sections,
            summary=summary,
            name=name,
            links=links,
        )
        self.add_version(version, backlink=backlink)

        if not self.is_bookmarked:
            bookmarks = BookmarksPage.find()
            bookmarks.add_bookmark(self.title)

    def restore(self, num):
        assert 0 <= num < len(self.versions) - 1
        version = self.versions[num]
        self.edit(version.sections, version.summary, version.name)

    @staticmethod
    def create_or_return(sections, summary, name):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = TopicVersion(
            sections=sections,
            summary=summary,
            name=name,
            timestamp=timestamp(),
            editor=g.user,
            links=links,
        )
        empty_version = TopicVersion(sections=[], summary="", name="")
        diff = TopicVersionDiff.compute(empty_version, version)
        empty_version.save()
        version.save()
        diff.save()
        page = TopicPage(
            titles=[version.title],
            search_terms=[name],
            versions=[version],
            diffs=[diff],
            last_edited=version.timestamp,
        )
        try:
            page.save()
        except DuplicateKeyError:
            empty_version.delete()
            version.delete()
            diff.delete()
            return Page.objects.get({"titles": version.title})
        empty_version.page = page
        version.page = page
        empty_version.save()
        version.save()
        page.trigger_backlinks(links)
        return page

    @property
    def can_edit(self):
        if g.user is None:
            return False
        if g.user.is_banned:
            return False
        return True


class TopicVersion(PageVersion):
    sections = fields.EmbeddedDocumentListField(Section, blank=True)
    summary = fields.CharField(blank=True)
    name = fields.CharField(blank=True)

    @property
    def title(self):
        return name_to_title(self.name)


class TopicVersionDiff(VersionDiff):
    sections = fields.EmbeddedDocumentListField(SectionDiff, blank=True)
    summary = fields.CharField(blank=True)
    summary_diff = fields.CharField(blank=True)
    summary_changed = fields.BooleanField()
    name = fields.CharField(blank=True)
    prev_name = fields.CharField(blank=True)

    @property
    def is_empty(self):
        return not (
            self.summary_changed
            or self.name_changed
            or any(not section.is_empty for section in self.sections)
        )

    @property
    def name_changed(self):
        return self.name != self.prev_name

    @staticmethod
    def compute(version_a, version_b):
        sections = diff_sections(version_a.sections, version_b.sections)
        summary_diff = markup_changes(version_a.summary, version_b.summary)
        name = version_b.name
        prev_name = version_a.name
        return TopicVersionDiff(
            version_a=version_a,
            version_b=version_b,
            sections=sections,
            summary=version_b.summary,
            summary_diff=summary_diff,
            summary_changed=version_a.summary != version_b.summary,
            name=name,
            prev_name=prev_name,
        )
