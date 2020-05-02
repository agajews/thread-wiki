from .page import Page, Version, VersionDiff


class UserPage(Page):
    versions = fields.ListField(fields.ReferenceField(UserVersion))
    diffs = fields.ListField(fields.ReferenceField(UserVersionDiff))
    primary_diffs = fields.ListField(fields.ReferenceField(UserVersionDiff))
    primary_version = fields.ReferenceField(UserVersion)
    owner = fields.ReferenceField(User)
    is_frozen = fields.BooleanField(default=False)

    def add_version(self, version):
        diff = UserVersionDiff.compute(self.versions[-1], version)
        if diff.is_empty:
            raise EmptyEdit()
        if version.is_primary:
            self.primary_version = version
        primary_diff = UserVersionDiff.compute(
            self.primary_version, version, concise=True
        )
        version.save()
        diff.save()
        primary_diff.save()
        self.versions.append(version)
        self.diffs.append(diff)
        self.primary_diffs.append(primary_diff)
        self.add_title(version.title)
        try:
            self.save_if_fresh()
        except (RaceCondition, DuplicatePage):
            version.delete()
            diff.delete()
            primary_diff.delete()
            raise

    def edit(self, sections, summary, name, aka):
        assert g.user is not None
        version = UserVersion(
            page=self,
            timestamp=timestamp(),
            editor=g.user,
            sections=sections,
            summary=summary,
            name=name,
            aka=aka,
            is_primary=g.user == self.owner,
        )
        self.add_version(version)

    def restore(self, num):
        assert 0 <= num < len(self.versions) - 1
        version = self.versions[num]
        self.edit(version.sections, version.summary, version.name, version.aka)

    def accept(self):
        assert g.user == self.owner
        self.primary_version = self.versions[-1]
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
    def create_or_return(sections, summary, name, aka, owner):
        assert g.user is not None
        version = UserVersion(
            sections=sections,
            summary=summary,
            name=name,
            aka=aka,
            timestamp=timestamp(),
            editor=g.user,
            is_primary=False,
        )
        diff = UserVersionDiff.compute(empty_version, version)
        primary_diff = UserVersionDiff.compute(empty_version, version, concise=True)
        version.save()
        diff.save()
        primary_diff.save()
        page = UserPage(
            titles=[version.title],
            versions=[version],
            diffs=[diff],
            primary_diffs=[primary_diff],
            primary_version=version,
            owner=owner,
        )
        try:
            page.save()
        except DuplicateKeyError:
            version.delete()
            diff.delete()
            primary_diff.delete()
            return Page.objects.get({"titles": version.title})
        return page

    def freeze(self):
        assert g.user == self.owner
        self.is_frozen = True
        # this can overwrite a pending edit from someone else, but that's ok
        self.save()

    def unfreeze(self):
        assert g.user == self.owner
        self.is_frozen = True
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
        if self.versions[-1] != self.primary_version:
            return True


class UserVersion(Version):
    sections = fields.EmbeddedDocumentListField(Section)
    summary = fields.CharField()
    name = fields.CharField()
    aka = fields.CharField()

    @property
    def title(self):
        return (self.name + "_" + self.aka).replace(" ", "_").replace("/", "|")


class UserVersionDiff(VersionDiff):
    sections = fields.EmbeddedDocumentListField(SectionDiff)
    summary = fields.CharField()
    summary_diff = fields.CharField()
    summary_changed = fields.BooleanField()
    name = fields.CharField()
    prev_name = fields.CharField()
    aka = fields.CharField()
    prev_aka = fields.CharField()

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
            or self.name_changed
            or any(not section.is_empty for section in self.sections)
        )

    @staticmethod
    def compute(version_a, version_b):
        sections = diff_sections(version_a.sections, version_b.sections)
        summary_diff = markup_changes(version_a.summary, version_b.summary)
        name = version_b.name
        prev_name = version_a.name
        aka = version_b.aka
        prev_aka = version_a.aka
        return TopicVersionDiff(
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
