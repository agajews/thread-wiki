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


def create_user_page(email):
    if g.user is None:
        raise NotAllowed()

    summary, sections = separate_sections(generate_user_template(email))
    owner = User.create_or_return(email)
    heading = UserPageHeading(email, generate_aka(email))
    content = UserPageContent(heading, summary, sections)
    return UserPage.create_or_return(
        current_title=email,
        titles=[email, heading.title],
        owner=owner._id,
        content=content,
        editor=g.user._id,
        timestamp=timestamp(),
    )


def edit_user_page(page, content):
    if not can_edit(page):
        raise NotAllowed()

    return page.edit(
        content,
        is_primary=page.owner == g.user._id,
        editor=g.user._id,
        timestamp=timestamp(),
    )


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
