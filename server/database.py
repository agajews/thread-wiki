from flask import g
from pymongo.errors import DuplicateKeyError
from .app import db, timestamp
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
    return (heading + "_" + nickname).replace(" ", "_")


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
    nickname = generate_nickname()
    summary, sections = separate_sections(generate_user_template(email))
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
                "type": "user",
                "owner": email,
                "primary": emptycontent,
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


def edit_user_page(page, content):
    num = page["versions"][-1]["num"]
    isprimary = page["owner"] == g.user["email"]
    primary = content if isprimary else page["primary"]
    newtitle = build_user_title(content["heading"], content["nickname"])

    oldcontent = page["versions"][-1]["content"]
    if content == oldcontent:
        return {"error": "emptyedit"}

    try:
        update = db.pages.update_one(
            {"titles": page["titles"][-1], "versions": {"$size": num}},
            {
                "$set": {"primary": primary},
                "$push": {
                    "versions": {
                        "content": content,
                        "diff": diff_versions(oldcontent, content),
                        "primarydiff": diff_versions(primary, content, concise=True),
                        "isprimary": isprimary,
                        "editor": g.user["_id"],
                        "timestamp": timestamp(),
                        "num": num + 1,
                    }
                },
                "$addToSet": {"titles": newtitle},
            },
        )
    except DuplicateKeyError:
        return {"error": "duplicatekey"}
    if update.modified_count == 0:
        return {"error": "racecondition"}
    return {"newtitle": newtitle}
