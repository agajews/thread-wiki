from .page import Page, LazyVersions


class UserPageContent(PageContent):
    Heading = UserPageHeading


class UserPageHeading:
    def __init__(self, name, aka):
        self.name = name
        self.aka = aka

    def __eq__(self, other):
        return (self.name, self.aka) == (other.name, other.aka)

    @property
    def title(self):
        return (self.name + "_" + self.aka).replace(" ", "_").replace("/", "|")

    @staticmethod
    def from_dict(heading):
        return UserPageHeading(heading["name"], heading["aka"])

    def to_dict(self):
        return {"name": self.name, "aka": self.aka}

    def copy(self):
        return UserPageHeading(self.name.copy(), self.aka.copy())


empty_content = UserPageContent(UserPageHeading("", ""), "", [])


class UserPageVersion:
    def __init__(
        self, content, diff, primary_diff, is_primary, editor, timestamp, num, flag=None
    ):
        self.content = content
        self.diff = diff
        self.primary_diff = primary_diff
        self.is_primary = is_primary
        self.editor = editor
        self.timestamp = timestamp
        self.num = num
        self.flag = flag

    @staticmethod
    def from_dict(version):
        flag = None
        if "flag" in version:
            flag = VersionFlag.from_dict(version["flag"])
        return UserPageVersion(
            UserPageContent.from_dict(version["content"]),
            VersionDiff.from_dict(version["diff"]),
            VersionDiff.from_dict(version["primary_diff"]),
            version["is_primary"],
            version["editor"],
            version["timestamp"],
            version["num"],
            flag=flag,
        )

    def to_dict(self):
        return {
            "content": self.content.to_dict(),
            "diff": self.diff.to_dict,
            "primary_diff": self.primary_diff.to_dict(),
            "is_primary": self.is_primary,
            "editor": self.editor,
            "timestamp": self.timestamp,
            "num": self.num,
            "flag": self.flag.to_dict(),
        }

    @property
    def title(self):
        return self.content.title


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
            self._primary = UserPageContent.find_primary(self.title)
        return self._primary

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
        primary_diff = VersionDiff.compute(primary, content)
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
        self.title = version.title
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
        self.versions[-1].primary_diff = VersionDiff.compute(self.primary, self.primary)
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
