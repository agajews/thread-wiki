from .page import Page, PageContent, LazyVersions
from .app import db
from .model import Model


class UserPageContent(Model):
    heading = Field(UserPageHeading)
    summary = Field(Paragraph)
    sections = List(Section)

    @property
    def title(self):
        return self.heading.title


class UserPageHeading(Model):
    name = Field(String)
    aka = Field(String)

    @property
    def title(self):
        return (self.name + "_" + self.aka).replace(" ", "_").replace("/", "|")


empty_content = UserPageContent(
    heading=UserPageHeading(name="", aka=""), summary=Paragraph(""), sections=[]
)


class UserPageVersion(Model):
    content = Field(UserPageContent)
    diff = Field(UserPageVersionDiff)
    primary_diff = Field(UserPageVersionDiff)
    is_primary = Field(Boolean)
    timestamp = Field(Float)
    editor = Field(ObjectRef)
    num = Field(Int)
    flag = Field(VersionFlag, required=False)


class UserPageHeadingDiff(Model):
    heading_a = Field(UserPageHeading)
    heading_b = Field(UserPageHeading)
    changed = Field(Boolean)

    @staticmethod
    def compute(heading_a, heading_b, concise=False):
        changed = heading_a == heading_b
        return HeadingDiff(heading_a, heading_b, changed)


class UserPageVersionDiff(Model):
    sections = List(SectionDiff)
    summary = Field(ParagraphDiff)
    heading = Field(UserPageHeadingDiff)


class UserPage(Page):
    Version = UserPageVersion

    def __init__(self, _id, versions, title, owner, primary, is_frozen):
        self._id = _id
        self.versions = versions
        self.title = title
        self.owner = owner
        self.is_frozen = is_frozen
        self._primary = primary

    @property
    def primary(self):
        if self._primary is None:
            page = db.pages.find_one({"titles": self.title}, {"primary": 1})
            if page is None:
                raise PageNotFound()
            self._primary = UserPageContent.from_dict(page["primary"])
        return self._primary

    @property
    def heading(self):
        return self.versions[-1].content.heading.name

    @staticmethod
    def from_dict(page):
        return UserPage(
            page["_id"],
            LazyVersions.from_dict(page),
            page["title"],
            page["owner"],
            page["is_frozen"],
            UserPageContent.from_dict(page["primary"]),
        )

    @staticmethod
    def create_or_return(title, owner, content):
        diff = VersionDiff.compute(empty_content, content)
        primary = empty_content
        primary_diff = VersionDiff.compute(primary, content, concise=True)
        version = UserPageVersion(
            content,
            diff,
            primary_diff,
            is_primary=False,
            editor=g.user._id,
            timestamp=timestamp(),
            num=0,
        )
        is_frozen = False
        try:
            insert = db.pages.insert_one(
                {
                    "titles": [title],
                    "title": title,
                    "type": "user",
                    "owner": owner,
                    "primary": primary.to_dict(),
                    "num_versions": 1,
                    "versions": [version.to_dict()],
                    "is_frozen": is_frozen,
                }
            )
        except DuplicateKeyError:
            return Page.find(title)
        versions = LazyVersions(title, 1, {0: version})
        return UserPage(insert.inserted_id, versions, title, owner, primary, is_frozen)

    def add_version(self, version):
        self.versions.append(version)
        self.title = version.content.title
        stuff_to_set = {"num_versions": len(self.versions) + 1, "title": self.title}
        if version.is_primary:
            self.primary = version.content
            stuff_to_set["primary"] = self.primary
        try:
            update = db.pages.update_one(
                {"titles": self.title, "versions": {"$size": len(self.versions)}},
                {
                    "$set": stuff_to_set,
                    "$push": {"versions": version.to_dict()},
                    "$addToSet": {"titles": self.title},
                },
            )
        except DuplicateKeyError:
            raise DuplicateKey()
        if update.modified_count == 0:
            raise RaceCondition()

    def accept_latest(self):
        self.versions[-1].is_primary = True
        self.primary = self.versions[-1].content
        self.versions[-1].primary_diff = VersionDiff.compute(
            self.primary, self.primary, concise=True
        )
        update = db.pages.update_one(
            {"titles": self.title, "versions": {"$size": len(self.versions)}},
            {
                "$set": {
                    "primary": self.primary,
                    "versions.{}".format(self.versions[-1].num): self.versions[-1],
                }
            },
        )
        if update.modified_count == 0:
            raise RaceCondition()

    def edit(self, content):
        if content == self.versions[-1].content:
            raise EmptyEdit()
        diff = VersionDiff.compute(self.versions[-1].content, content)
        is_primary = g.user.is_owner(self)
        if is_primary:
            self.primary = content
        primary_diff = VersionDiff.compute(self.primary, content, concise=True)
        version = UserPageVersion(
            content=content,
            diff=diff,
            primary_diff=primary_diff,
            is_primary=is_primary,
            editor=g.user._id,
            timestamp=timestamp(),
            num=len(self.versions),
        )
        self.add_version(version)

    def restore_version(self, num):
        if num == len(self.versions) - 1 and g.user.is_owner(self):
            self.accept_latest()
        else:
            self.edit(self.versions[num].content)

    def freeze(self):
        self.is_frozen = True
        db.pages.update_one({"titles": self.title}, {"$set": {"is_frozen": True}})

    def unfreeze(self):
        self.is_frozen = False
        db.pages.update_one({"titles": self.title}, {"$set": {"is_frozen": False}})
