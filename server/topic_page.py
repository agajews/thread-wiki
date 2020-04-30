from .page import Page, LazyVersions


class TopicPageContent(PageContent):
    Heading = TopicPageHeading


class TopicPageHeading:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return self.name == other.name

    @property
    def title(self):
        return self.name.replace(" ", "_").replace("/", "|")

    @staticmethod
    def from_dict(heading):
        return TopicPageHeading(heading)

    def to_dict(self):
        return self.name

    def copy(self):
        return TopicPageHeading(self.name.copy())


empty_content = TopicPageContent(TopicPageHeading(""), "", [])


class TopicPageVersion:
    def __init__(self, content, diff, editor, timestamp, num, flag=None):
        self.content = content
        self.diff = diff
        self.editor = editor
        self.timestamp = timestamp
        self.num = num
        self.flag = flag

    @staticmethod
    def from_dict(version):
        flag = None
        if "flag" in version:
            flag = VersionFlag.from_dict(version["flag"])
        return TopicPageVersion(
            TopicPageContent.from_dict(version["content"]),
            VersionDiff.from_dict(version["diff"]),
            version["editor"],
            version["timestamp"],
            version["num"],
            flag=flag,
        )

    def to_dict(self):
        return {
            "content": self.content.to_dict(),
            "diff": self.diff.to_dict,
            "editor": self.editor,
            "timestamp": self.timestamp,
            "num": self.num,
            "flag": self.flag.to_dict(),
        }

    @property
    def title(self):
        return self.content.title


class TopicPage(Page):
    Version = TopicPageVersion

    def __init__(self, _id, versions, title):
        self._id = _id
        self.versions = versions
        self.title = title

    @staticmethod
    def from_dict(page):
        return TopicPage(page["_id"], LazyVersions.from_dict(page), page["title"])

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
        self.title = version.title
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
