from .page import Page, LazyVersions
from .app import db


class TopicPageContent(Model):
    heading = Field(UserPageHeading)
    summary = Field(Paragraph)
    sections = List(Section)

    @property
    def title(self):
        return self.heading.title


class TopicPageHeading(Model):
    name = Field(String)
    aka = Field(String)

    @property
    def title(self):
        return self.name.replace(" ", "_").replace("/", "|")


empty_content = TopicPageContent(
    heading=TopicPageHeading(name="", aka=""), summary=Paragraph(""), sections=[]
)


class TopicPageVersion(Model):
    content = Field(UserPageContent)
    diff = Field(UserPageVersionDiff)
    timestamp = Field(Float)
    editor = Field(ObjectRef)
    num = Field(Int)
    flag = Field(VersionFlag, required=False)


class TopicPageHeadingDiff(Model):
    heading_a = Field(UserPageHeading)
    heading_b = Field(UserPageHeading)
    changed = Field(Boolean)

    @staticmethod
    def compute(heading_a, heading_b, concise=False):
        changed = heading_a == heading_b
        return HeadingDiff(heading_a, heading_b, changed)


class TopicPageVersionDiff(Model):
    sections = List(SectionDiff)
    summary = Field(ParagraphDiff)
    heading = Field(UserPageHeadingDiff)


class TopicPage(Page):
    Version = TopicPageVersion

    def __init__(self, _id, versions, title):
        self._id = _id
        self.versions = versions
        self.title = title

    @staticmethod
    def from_dict(page):
        return TopicPage(page["_id"], LazyVersions.from_dict(page), page["title"])

    @property
    def heading(self):
        return self.versions[-1].content.heading.name

    @staticmethod
    def create_or_return(title, owner, content):
        diff = VersionDiff.compute(empty_content, content)
        version = TopicPageVersion(
            content, diff, editor=g.user._id, timestamp=timestamp(), num=0
        )
        try:
            insert = db.pages.insert_one(
                {
                    "titles": [title],
                    "title": title,
                    "type": "topic",
                    "num_versions": 1,
                    "versions": [version.to_dict()],
                }
            )
        except DuplicateKeyError:
            return Page.find(title)
        versions = LazyVersions(title, 1, {0: version})
        return TopicPage(insert.inserted_id, versions, title)

    def add_version(self, version):
        self.versions.append(version)
        self.title = version.content.title
        try:
            update = db.pages.update_one(
                {"titles": self.title, "versions": {"$size": len(self.versions)}},
                {
                    "$set": {
                        "num_versions": len(self.versions) + 1,
                        "title": self.title,
                    },
                    "$push": {"versions": version.to_dict()},
                    "$addToSet": {"titles": self.title},
                },
            )
        except DuplicateKeyError:
            raise DuplicateKey()
        if update.modified_count == 0:
            raise RaceCondition()

    def edit(self, content):
        if content == self.versions[-1].content:
            raise EmptyEdit()
        diff = VersionDiff.compute(self.versions[-1].content, content)
        version = UserPageVersion(
            content=content,
            diff=diff,
            editor=g.user._id,
            timestamp=timestamp(),
            num=len(self.versions),
        )
        self.add_version(version)

    def restore_version(self, num):
        self.edit(self.versions[num].content)
