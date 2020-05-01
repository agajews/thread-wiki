from .errors import PageNotFound, VersionNotFound
from .html_utils import markup_changes, diff_sections, Section, SectionDiff
from .model import Model


class VersionFlag(Model):
    sender = ObjectRef
    timestamp = Float
    page = ObjectRef
    num = Int

    @staticmethod
    def update_flags(recipient):
        flags = db.flags.find_one({"user": recipient})
        first = None
        banned_until = None
        for flag in flags["flags"]:
            if first is None:
                first = flag["sender"]
            elif first != flag["sender"]:
                first = None
                banned_until = flag["timestamp"] + 3600 * 24
        db.flags.update_one(
            flags, {"$set": {"banned_until": banned_until, "dirty": False}}
        )


class LazyVersions:
    def __init__(self, page, num_versions, versions_dict):
        self.page = page
        self.num_versions = num_versions
        self.versions_dict = versions_dict

    @property
    def full(self):
        return len(self.versions_dict) == self.num_versions

    def __getitem__(self, num):
        wrapped_num = num % self.num_versions
        if wrapped_num not in self.versions_dict:
            self.versions_dict[wrapped_num] = self.page.find_version(wrapped_num)
        return self.versions_dict[wrapped_num]

    def __len__(self):
        return self.num_versions

    def __iter__(self):
        if not self.full:
            for version in self.page.find_all_versions():
                self.versions_dict[version.num] = version
        return (self.versions_dict(num) for num in range(self.num_versions))

    def append(self, version):
        self.versions_dict[self.num_versions] = version
        self.num_versions += 1

    @staticmethod
    def from_dict(self, page):
        versions = [
            self.page.Version.from_dict(version) for version in page["versions"]
        ]
        return LazyVersions(
            page, page["num_versions"], {version.num: version for version in versions}
        )


class Page:
    @staticmethod
    def find(
        title, preload_version=-1, preload_all_versions=False, preload_primary=False
    ):
        proj = {"num_versions": 1, "type": 1, "title": 1, "owner": 1, "is_frozen": 1}
        if preload_all_versions:
            proj["versions"] = 1
        elif preload_version is not None:
            proj["versions"] = {"$slice": preload_version}
        if preload_primary:
            proj["primary"] = 1
        page = db.pages.find_one({"titles": title}, proj)
        if page is None:
            raise PageNotFound()
        if page["type"] == "user":
            return UserPage.from_dict(page)
        elif page["type"] == "topic":
            return TopicPage.from_dict(page)
        raise Exception()

    def find_version(self, num):
        page = db.pages.find_one(
            {"titles": self.title}, {"versions": {"$slice": [num, 1]}}
        )
        if page is None:
            raise PageNotFound()
        if len(page["versions"]) == 0:
            raise VersionNotFound()
        return self.Version.from_dict(page["versions"][0])

    def find_all_versions(self):
        page = db.pages.find_one({"titles": self.title}, {"versions": 1})
        if page is None:
            raise PageNotFound()
        return [self.Version.from_dict(version) for version in page["versions"]]

    def flag_version(self, num):
        if not 0 < num < len(self.versions) - 1:
            raise Malformed()
        sender = g.user._id
        recipient = self.versions[num].editor
        flag = VersionFlag(sender=sender, timestamp=timestamp(), page=self._id, num=num)
        self.versions[num].flag = flag
        update = db.pages.update_one(
            {"titles": self.title, "versions.{}.flag".format(num): None},
            {"$set": {"versions.{}.flag".format(num): flag.to_dict()}},
        )
        if update.modified_count == 0:
            raise AlreadyFlagged()
        db.flags.update_one(
            {"user": recipient},
            {"$push": flag.to_dict()},
            {"$set": {"dirty": True}},
            upsert=True,
        )
        VersionFlag.update_flags(recipient)

    def unflag_version(self, num):
        self.versions[num].flag = None
        db.pages.update_one(
            {"titles": self.title}, {"$set": {"versions.{}.flag".format(num): None}}
        )
        recipient = self.versions[num].editor
        db.flags.update_one(
            {"user": recipient},
            {
                "$pull": {"flags": {"page": self._id, "num": num}},
                "$set": {"dirty": True},
            },
        )
        VersionFlag.update_flags(recipient)
