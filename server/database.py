import random
from copy import deepcopy
from flask import g, abort
from pymongo.errors import DuplicateKeyError
from .app import db, timestamp
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


def create_user_page(email):
    if g.user is None:
        abort(404)

    nickname = generate_nickname()
    summary, sections = separate_sections(generate_user_template(email))
    content = {
        "sections": sections,
        "summary": summary,
        "heading": email,
        "nickname": nickname,
    }
    try:
        owner_id = create_or_return_user(email)
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
                        "isempty": False,
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": 1,
                    }
                ],
            }
        )
    except DuplicateKeyError:
        pass


def edit_user_page(page, content):
    if g.user is None:
        abort(401)

    isprimary = page["owner"] == g.user["_id"]
    oldcontent = page["versions"][-1]["content"]

    if content == oldcontent and isprimary > page["versions"][-1]["isprimary"]:
        return accept_user_version(page)
    elif content == oldcontent:
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
    return {"currenttitle": newtitle, "version": version}


def flag_version(page):
    if g.user is None:
        abort(401)
    num = page["versions"][0]["num"]
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
        abort(400)
    num = page["versions"][0]["num"]
    recipient = page["versions"][0]["editor"]
    if g.user is None or g.user["_id"] != page["versions"][0]["flagsender"]:
        abort(401)
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
