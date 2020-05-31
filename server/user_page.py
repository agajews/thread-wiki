from pymodm import fields, MongoModel, EmbeddedMongoModel
from pymongo.errors import DuplicateKeyError
from flask import g, render_template
from datetime import timedelta

from .page import Page, PageVersion, VersionDiff
from .bookmarks import BookmarksPage
from .html_utils import markup_changes, name_to_title, linkify_page, sanitize_html
from .sections import diff_sections, Section, SectionDiff
from .app import timestamp, url_for, absolute_url
from .mail import send_email
from .errors import *


class UserPage(Page):
    versions = fields.ListField(fields.ReferenceField("UserVersion"))
    diffs = fields.ListField(fields.ReferenceField("UserVersionDiff"))
    primary_diffs = fields.ListField(fields.ReferenceField("UserVersionDiff"))
    primary_version = fields.ReferenceField("UserVersion")
    owner = fields.ReferenceField("User")
    is_frozen = fields.BooleanField(default=False)
    last_emailed = fields.DateTimeField()

    @property
    def name(self):
        return "{} ({})".format(self.versions[-1].name, self.versions[-1].aka)

    def add_version(self, version, is_primary=False):
        diff = UserVersionDiff.compute(self.latest, version)
        if diff.is_empty:
            raise EmptyEdit()
        if is_primary:
            self.primary_version = version
        primary_diff = UserVersionDiff.compute(
            self.primary_version, version, concise=True
        )
        new_links = set(version.links).difference(self.latest.links)
        version.save()
        diff.save()
        primary_diff.save()
        self.versions.append(version)
        self.diffs.append(diff)
        self.primary_diffs.append(primary_diff)
        self.add_title(version.title)
        self.add_search_term(version.name)
        self.last_edited = version.timestamp
        try:
            self.save_if_fresh()
        except (RaceCondition, DuplicatePage):
            version.delete()
            diff.delete()
            primary_diff.delete()
            raise
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
            sections,
            self.latest.summary,
            self.latest.name,
            self.latest.aka,
            is_primary=False,
        )

    def edit(self, sections, summary, name, aka, is_primary=None):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = UserVersion(
            page=self,
            timestamp=timestamp(),
            editor=g.user,
            sections=sections,
            summary=summary,
            name=name,
            aka=aka,
            links=links,
        )
        if is_primary is None:
            is_primary = g.user == self.owner
        self.add_version(version, is_primary=is_primary)

        if self.should_send_email(version):
            self.send_email(version)

        if not self.is_bookmarked:
            bookmarks = BookmarksPage.find()
            bookmarks.add_bookmark(self.title)

    def should_send_email(self, version):
        if len(self.versions) < 4:
            return False
        if g.user == self.owner:
            return False
        if self.last_emailed is None:
            return True
        if version.timestamp - self.last_emailed >= timedelta(days=1):
            return True
        return False

    def send_email(self, version):
        send_email(
            self.owner.email,
            "Edit notification for {} ({}): Someone edited your page on {}".format(
                version.name,
                version.aka,
                version.timestamp.date().strftime("%m/%d/%y"),
            ),
            render_template("edit-email.html", version=version),
            render_template("edit-email.txt", version=version),
        )
        Page.objects.raw({"_id": self._id}).update(
            {"$set": {"last_emailed": version.timestamp}}
        )

    def restore(self, num):
        assert 0 <= num < len(self.versions) - 1
        version = self.versions[num]
        self.edit(
            version.sections,
            version.summary,
            version.name,
            version.aka,
            is_primary=version.editor == self.owner,
        )

    def accept(self):
        assert g.user == self.owner
        self.primary_version = self.latest
        primary_diff = UserVersionDiff.compute(
            self.primary_version, self.primary_version, concise=True
        )
        primary_diff.save()
        self.primary_diffs[-1] = primary_diff
        try:
            self.save_if_fresh()
        except RaceCondition:
            primary_diff.delete()
            raise

    @staticmethod
    def create_or_return(sections, summary, email, aka, owner):
        assert g.user is not None
        links, sections, summary = linkify_page(sections, summary)
        version = UserVersion(
            sections=sections,
            summary=summary,
            name=email,
            aka=aka,
            timestamp=timestamp(),
            editor=g.user,
            links=links,
        )
        empty_version = UserVersion(sections=[], summary="", name="", aka="")
        diff = UserVersionDiff.compute(empty_version, version)
        primary_diff = UserVersionDiff.compute(empty_version, version, concise=True)
        empty_version.save()
        version.save()
        diff.save()
        primary_diff.save()
        page = UserPage(
            titles=[email],
            search_terms=[email],
            versions=[version],
            diffs=[diff],
            primary_diffs=[primary_diff],
            primary_version=empty_version,
            owner=owner,
            last_edited=version.timestamp,
        )
        try:
            page.save()
        except DuplicateKeyError:
            version.delete()
            empty_version.delete()
            diff.delete()
            primary_diff.delete()
            return Page.objects.get({"titles": email})
        empty_version.page = page
        version.page = page
        empty_version.save()
        version.save()
        page.trigger_backlinks(links)
        return page

    def freeze(self):
        assert g.user == self.owner
        self.is_frozen = True
        # this can overwrite a pending edit from someone else, but that's ok
        self.save()

    def unfreeze(self):
        assert g.user == self.owner
        self.is_frozen = False
        self.save()

    @property
    def can_edit(self):
        if g.user is None:
            return False
        if g.user == self.owner:
            return True
        if self.is_frozen:
            return False
        if g.user.is_banned:
            return False
        return True

    @property
    def can_accept(self):
        if g.user is None:
            return False
        if g.user != self.owner:
            return False
        if self.latest != self.primary_version:
            return True


class UserVersion(PageVersion):
    sections = fields.EmbeddedDocumentListField(Section, blank=True)
    summary = fields.CharField(blank=True)
    name = fields.CharField(blank=True)
    aka = fields.CharField(blank=True)

    @property
    def title(self):
        return name_to_title(self.name + " (" + self.aka + ")")


class UserVersionDiff(VersionDiff):
    # TODO: make sure everything is blankable
    sections = fields.EmbeddedDocumentListField(SectionDiff, blank=True)
    summary = fields.CharField(blank=True)
    summary_diff = fields.CharField(blank=True)
    summary_changed = fields.BooleanField()
    name = fields.CharField(blank=True)
    prev_name = fields.CharField(blank=True)
    aka = fields.CharField(blank=True)
    prev_aka = fields.CharField(blank=True)

    @property
    def heading_changed(self):
        return self.name_changed or self.aka_changed

    @property
    def name_changed(self):
        return self.name != self.prev_name

    @property
    def aka_changed(self):
        return self.aka != self.prev_aka

    @property
    def is_empty(self):
        return not (
            self.summary_changed
            or self.heading_changed
            or any(not section.is_empty for section in self.sections)
        )

    @staticmethod
    def compute(version_a, version_b, concise=False):
        sections = diff_sections(
            version_a.sections, version_b.sections, concise=concise
        )
        summary_diff = markup_changes(
            version_a.summary, version_b.summary, concise=concise
        )
        name = version_b.name
        prev_name = version_a.name
        aka = version_b.aka
        prev_aka = version_a.aka
        return UserVersionDiff(
            version_a=version_a,
            version_b=version_b,
            sections=sections,
            summary=version_b.summary,
            summary_diff=summary_diff,
            summary_changed=version_a.summary != version_b.summary,
            name=name,
            prev_name=prev_name,
            aka=aka,
            prev_aka=prev_aka,
        )

    @property
    def sections_dict(self):
        return {
            section.idx: section for section in self.sections if not section.deleted
        }
