import random
from copy import deepcopy
from flask import g, abort
from pymongo.errors import DuplicateKeyError
from .app import db, timestamp, app
from .auth import create_or_return_user
from .html_utils import sanitize_html, markup_changes, separate_sections, diff_sections


def generate_user_template(email):
    return "<p>The homo sapiens {0} is simply the best.</p><h2>Best Quotes</h2><p>Yoyoyo, it's my boy {0}</p><h2>Early life</h2><p>One day, our protagonist {0} was born. Later, they went to college.</p>".format(
        email
    )


def generate_nickname():
    return random.choice(
        [
            "Benevolent Dictator",
            "A Reasonable Person",
            "Mother Away From Home",
            "I ran out of ideas for nicknames",
            "The Best Chef This World Has Ever Seen",
            "Pure Instinct",
            "Fascinator",
            "Analyst",
        ]
    )


emptycontent = {"sections": [], "summary": "", "heading": "", "nickname": ""}


def build_user_title(heading, nickname):
    return (heading + "_" + nickname).replace(" ", "_").replace("/", "|")


def build_topic_title(heading):
    return heading.replace(" ", "_").replace("/", "|")


def diff_versions(content_a, content_b, concise=False):
    return {
        "sections": diff_sections(
            content_a["sections"], content_b["sections"], concise=concise
        ),
        "summary": markup_changes(
            content_a["summary"], content_b["summary"], concise=concise
        ),
        "summarychanged": content_a["summary"] != content_b["summary"],
        "headingchanged": content_a["heading"] != content_b["heading"],
        "nicknamechanged": content_a["nickname"] != content_b["nickname"],
        "oldheading": content_a["heading"],
        "oldnickname": content_a["nickname"],
    }


def find_page(title, version="latest", primary=False, noneallowed=False):
    if version == "latest":
        versionsproj = {"$slice": -1}
    elif version == "all":
        versionsproj = 1
    elif isinstance(version, int):
        versionsproj = {"$slice": [version - 1, version]}
    else:
        raise Exception("Oops, something went wrong")
    projection = {
        "versions": versionsproj,
        "numversions": 1,
        "type": 1,
        "currenttitle": 1,
        "owner": 1,
        "isfrozen": 1,
    }
    if primary:
        projection["primary"] = 1
    page = db.pages.find_one({"titles": title}, projection)
    if not noneallowed and (page is None or len(page["versions"]) == 0):
        abort(404)
    return page


def create_topic_page(title):
    if g.user is None:
        abort(404)

    summary, sections = separate_sections(generate_topic_template(title))
    heading = title.replace("_", " ").replace("|", "/")
    content = {"sections": sections, "summary": summary, "heading": heading}
    try:
        db.pages.insert_one(
            {
                "titles": [title],
                "currenttitle": title,
                "type": "topic",
                "numversions": 1,
                "versions": [
                    {
                        "content": content,
                        "diff": diff_versions(emptycontent, content),
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": 1,
                    }
                ],
            }
        )
    except DuplicateKeyError:
        pass


def create_user_page(email):
    if g.user is None:
        abort(404)

    nickname = generate_nickname()
    summary, sections = separate_sections(generate_user_template(email))
    owner_id = create_or_return_user(email)
    content = {
        "sections": sections,
        "summary": summary,
        "heading": email,
        "nickname": nickname,
    }
    try:
        db.pages.insert_one(
            {
                "titles": [email, build_user_title(email, nickname)],
                "currenttitle": email,
                "type": "user",
                "owner": owner_id,
                "primary": emptycontent,
                "numversions": 1,
                "versions": [
                    {
                        "content": content,
                        "diff": diff_versions(emptycontent, content),
                        "primarydiff": diff_versions(
                            emptycontent, content, concise=True
                        ),
                        "isprimary": False,
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": 1,
                    }
                ],
            }
        )
    except DuplicateKeyError:
        pass


def edit_user_page(page, content, emptyallowed=False):
    if not can_edit(page):
        return {"error": "notallowed"}

    isprimary = page["owner"] == g.user["_id"]
    oldcontent = page["versions"][-1]["content"]

    if content == oldcontent:
        if isprimary > page["versions"][-1]["isprimary"] and is_owner(page):
            return accept_user_version(page)
        elif emptyallowed:
            return {
                "currenttitle": page["currenttitle"],
                "version": page["versions"][-1],
                "updated": False,
            }
        return {"error": "emptyedit"}
    return add_user_version(page, content)


def accept_user_version(page):
    version = page["versions"][-1]
    content = version["content"]
    num = version["num"]
    version["isprimary"] = True
    version["primarydiff"] = diff_versions(content, content, concise=True)
    update = db.pages.update_one(
        {
            "titles": page["currenttitle"],
            "versions": {"$size": num},
            "versions.num": num,
        },
        {"$set": {"primary": content, "versions.$": version}},
    )
    if update.modified_count == 0:
        return {"error": "racecondition"}
    return {"currenttitle": page["currenttitle"], "version": version}


def add_user_version(page, content):
    num = page["versions"][-1]["num"]
    isprimary = page["owner"] == g.user["_id"]
    oldcontent = page["versions"][-1]["content"]
    primary = content if isprimary else page["primary"]
    newtitle = build_user_title(content["heading"], content["nickname"])

    diff = diff_versions(oldcontent, content)
    primarydiff = diff_versions(primary, content, concise=True)

    version = {
        "content": content,
        "diff": diff,
        "primarydiff": primarydiff,
        "isprimary": isprimary,
        "editor": g.user["_id"],
        "timestamp": timestamp(),
        "num": num + 1,
    }
    try:
        update = db.pages.update_one(
            {"titles": page["currenttitle"], "versions": {"$size": num}},
            {
                "$set": {
                    "primary": primary,
                    "currenttitle": newtitle,
                    "numversions": num + 1,
                },
                "$push": {"versions": version},
                "$addToSet": {"titles": newtitle},
            },
        )
    except DuplicateKeyError:
        return {"error": "duplicatekey"}
    if update.modified_count == 0:
        return {"error": "racecondition"}
    return {"currenttitle": newtitle, "version": version, "updated": True}


def edit_topic_page(page, content, emptyallowed=False):
    if not can_edit(page):
        return {"error": "notallowed"}

    oldcontent = page["versions"][-1]["content"]
    if content == oldcontent:
        if emptyallowed:
            return {
                "currenttitle": page["currenttitle"],
                "version": page["versions"][-1],
                "updated": False,
            }
        return {"error": "emptyedit"}
    return add_topic_version(page, content)


def add_topic_version(page, content):
    num = page["versions"][-1]["num"]
    oldcontent = page["versions"][-1]["content"]
    newtitle = build_topic_title(content["heading"])
    diff = diff_versions(oldcontent, content)

    version = {
        "content": content,
        "diff": diff,
        "editor": g.user["_id"],
        "timestamp": timestamp(),
        "num": num + 1,
    }
    try:
        update = db.pages.update_one(
            {"titles": page["currenttitle"], "versions": {"$size": num}},
            {
                "$set": {"currenttitle": newtitle, "numversions": num + 1},
                "$push": {"versions": version},
                "$addToSet": {"titles": newtitle},
            },
        )
    except DuplicateKeyError:
        return {"error": "duplicatekey"}
    if update.modified_count == 0:
        return {"error": "racecondition"}
    return {"currenttitle": newtitle, "version": version, "updated": True}


def flag_version(page):
    if not can_edit(page):
        return {"error": "notallowed"}
    if g.user["_id"] == page["versions"][0]["editor"]:
        return {"error": "flagyourself"}

    num = page["versions"][0]["num"]
    if not 1 < num < page["numversions"]:
        abort(400)

    recipient = page["versions"][0]["editor"]
    flagtime = timestamp()
    update = db.pages.update_one(
        {
            "titles": page["currenttitle"],
            "versions.{}.isflagged".format(num - 1): {"$ne": True},
        },
        {
            "$set": {
                "versions.{}.isflagged".format(num - 1): True,
                "versions.{}.flagsender".format(num - 1): g.user["_id"],
                "versions.{}.flagtime".format(num - 1): flagtime,
            }
        },
    )
    if update.modified_count == 0:
        return {"error": "alreadyflagged"}

    db.flags.update_one(
        {"user": recipient},
        {
            "$push": {
                "flags": {
                    "flagtime": flagtime,
                    "flagsender": g.user["_id"],
                    "page": page["_id"],
                    "num": num,
                }
            },
            "$set": {"dirty": True},
        },
        upsert=True,
    )

    update_flags(recipient)
    return {"success": True}


def unflag_version(page):
    if not page["versions"][0].get("isflagged"):
        return {"success": True}
    if g.user is None or g.user["_id"] != page["versions"][0]["flagsender"]:
        return {"error": "notallowed"}

    num = page["versions"][0]["num"]
    recipient = page["versions"][0]["editor"]
    db.pages.update_one(
        {"titles": page["currenttitle"]},
        {
            "$set": {
                "versions.{}.isflagged".format(num - 1): False,
                "versions.{}.flagsender".format(num - 1): None,
                "versions.{}.flagtime".format(num - 1): None,
            }
        },
    )
    db.flags.update_one(
        {"user": recipient},
        {
            "$pull": {"flags": {"page": page["_id"], "num": num}},
            "$set": {"dirty": True},
        },
    )
    update_flags(recipient)
    return {"success": True}


def update_flags(recipient):
    flags = db.flags.find_one({"user": recipient})
    first = None
    banneduntil = None
    for flag in flags["flags"]:
        if first is None:
            first = flag["flagsender"]
        elif first != flag["flagsender"]:
            first = None
            banneduntil = flag["flagtime"] + 3600 * 24
    update = db.flags.update_one(
        flags, {"$set": {"banneduntil": banneduntil, "dirty": False}}
    )


def freeze_page(page):
    if not is_owner(page):
        return  # implicitly reloading the page so the user can see they're not logged in
    db.pages.update_one({"titles": page["currenttitle"]}, {"$set": {"isfrozen": True}})


def unfreeze_page(page):
    if not is_owner(page):
        return  # implicitly reloading the page so the user can see they're not logged in
    db.pages.update_one({"titles": page["currenttitle"]}, {"$set": {"isfrozen": False}})


def can_edit(page):
    if g.user is None:
        return False
    if is_owner(page):
        return True
    if page.get("isfrozen"):
        return False
    flags = db.flags.find_one({"user": g.user["_id"]}, {"banneduntil": 1})
    if flags is None:
        return True
    banneduntil = flags.get("banneduntil")
    if banneduntil is None:
        return True
    return timestamp() > banneduntil


def is_owner(page):
    if g.user is None:
        return False
    return page.get("owner") == g.user["_id"]


@app.context_processor
def inject_permissions():
    return dict(can_edit=can_edit, is_owner=is_owner)
