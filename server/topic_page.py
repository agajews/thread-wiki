from .page import Page, Version, VersionDiff


class TopicPage(Page):
    versions = fields.ListField(fields.ReferenceField(TopicVersion))
    diffs = fields.ListField(fields.ReferenceField(TopicVersionDiff))

    def add_version(self, version):
        diff = TopicVersionDiff.compute(self.versions[-1], version)
        if diff.is_empty:
            raise EmptyEdit()
        version.save()
        diff.save()
        self.versions.append(version)
        self.diffs.append(diff)
        self.add_title(version.title)
        try:
            self.save_if_fresh()
        except (RaceCondition, DuplicatePage):
            version.delete()
            diff.delete()
            raise

    def edit(self, sections, summary, name):
        assert g.user is not None
        version = TopicVersion(
            page=self,
            timestamp=timestamp(),
            editor=g.user,
            sections=sections,
            summary=summary,
            name=name,
        )
        self.add_version(version)

    def restore(self, num):
        assert 0 <= num < len(self.versions) - 1
        version = self.versions[num]
        self.edit(version.sections, version.summary, version.name)

    @staticmethod
    def create_or_return(sections, summary, name):
        assert g.user is not None
        version = TopicVersion(
            sections=sections,
            summary=summary,
            name=name,
            timestamp=timestamp(),
            editor=g.user,
        )
        diff = VersionDiff.compute(empty_version, version)
        version.save()
        diff.save()
        page = TopicPage(titles=[version.title], versions=[version], diffs=[diff])
        try:
            page.save()
        except DuplicateKeyError:
            version.delete()
            diff.delete()
            return Page.objects.get({"titles": version.title})
        return page

    @property
    def can_edit(self):
        if g.user is None:
            return False
        if g.user.is_banned:
            return False
        return True


empty_version = TopicVersion(sections=[], summary="", name="")


class TopicVersion(Version):
    sections = fields.EmbeddedDocumentListField(Section)
    summary = fields.CharField()
    name = fields.CharField()

    @property
    def title(self):
        return self.name.replace(" ", "_").replace("/", "|")


class TopicVersionDiff(VersionDiff):
    sections = fields.EmbeddedDocumentListField(SectionDiff)
    summary = fields.CharField()
    summary_diff = fields.CharField()
    summary_changed = fields.BooleanField()
    name = fields.CharField()
    prev_name = fields.CharField()

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
