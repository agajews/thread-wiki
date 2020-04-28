from flask import render_template, abort, request, jsonify, g, redirect
import re
from copy import deepcopy
from .app import app, db, timestamp, url_for
from .auth import verify_password, generate_auth_token
from .html_utils import sanitize_html, sanitize_text, separate_sections
from .database import (
    create_user_page,
    edit_user_page,
    flag_version,
    unflag_version,
    freeze_page,
    unfreeze_page,
    can_edit,
)


@app.route("/")
def index():
    pages = db.pages.find(
        {}, {"titles": {"$slice": -1}, "versions.heading": {"$slice": -1}}
    )
    return render_template("index.html", pages=pages)


def find_page(title, version="latest", primary=False):
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
    if page is None or len(page["versions"]) == 0:
        abort(404)
    return page


def is_valid_email(email):
    if re.match("^[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+.)+edu$", email):
        return True
    return False


@app.route("/page/<title>/")
def page(title):
    page = find_page(title)
    if page is not None and page["type"] == "user":
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title, page=page
        )
    if is_valid_email(title):
        create_user_page(title)
        page = find_page(title)
        return render_template(
            "user-page.html", version=page["versions"][-1], title=title, page=page
        )

    abort(404)  # eventually, create new topic page


@app.route("/page/<title>/edit/")
def edit(title):
    page = find_page(title)
    if not can_edit(page):
        abort(401)
    if page is not None and page["type"] == "user":
        return render_template(
            "edit-user-page.html", version=page["versions"][-1], title=title
        )
    abort(404)


def get_param(key):
    data = request.get_json(silent=True)
    if data is None or key not in data:
        abort(400)
    return data[key]


def signal(response=None, redirect=None, html=None):
    return jsonify({"response": response, "redirect": redirect, "html": html})


def failedit(errorkey, errorid):
    editerrors = {
        "racecondition": "Lel, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening edit page in a new tab).",
        "duplicatekey": "Lel, someone with the same name already has that nickname!",
        "emptyedit": "Lel, doesn't look like you changed anything.",
        "flagyourself": "Lel, can't flag yourself.",
        "alreadyflagged": "Lel, someone else flagged this already.",
        "notallowed": "Lel, looks like you're not allowed to do that.",
    }
    return signal(html={errorid: editerrors[errorkey]})


@app.route("/page/<title>/submitedit/", methods=["POST"])
def submitedit(title):
    page = find_page(title, primary=True)
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    content = {
        "sections": sections,
        "summary": summary,
        "heading": sanitize_text(get_param("heading")),
        "nickname": sanitize_text(get_param("nickname")),
    }
    update = edit_user_page(page, content)
    if "error" in update:
        return failedit(update["error"], "editerror")
    return signal(redirect=url_for("page", title=update["currenttitle"]))


@app.route("/page/<title>/sectionedit/<int:idx>/", methods=["POST"])
def sectionedit(title, idx):
    page = find_page(title, primary=True)
    content = deepcopy(page["versions"][-1]["content"])
    if idx >= len(content["sections"]):
        return failedit("racecondition", "sectionerror-{}".format(idx))
    updated_body = sanitize_html(get_param("body"))
    content["sections"][idx]["body"] = updated_body
    update = edit_user_page(page, content, emptyallowed=True)
    if "error" in update:
        return failedit(update["error"], "sectionerror-{}".format(idx))
    for section in update["version"]["primarydiff"]["sections"]:
        if section["idx"] == idx:
            updated_diff = section["diff"]
    return signal(
        response={"done": True, "num": update["version"]["num"]},
        html={
            "sectionerror-{}".format(idx): "",
            "section-diff-{}".format(idx): updated_diff,
            "section-body-{}".format(idx): updated_body,
        },
    )


@app.route("/page/<title>/summaryedit/", methods=["POST"])
def summaryedit(title):
    pade = find_page(title, primary=True)
    content = deepcopy(page["versions"][-1]["content"])
    content["summary"] = sanitize_html(get_param("body"))
    update = edit_user_page(page, content, emptyallowed=True)
    if "error" in update:
        return failedit(update["error"], "summaryerror")
    return signal(
        response={"done": True, "num": update["version"]["num"]},
        html={
            "summaryerror": "",
            "summary-diff": update["version"]["primarydiff"]["summary"],
            "summary-body": update["version"]["content"]["summary"],
        },
    )


@app.route("/page/<title>/headingedit/", methods=["POST"])
def headingedit(title):
    pade = find_page(title, primary=True)
    content = deepcopy(page["versions"][-1]["content"])
    content["heading"] = sanitize_text(get_param("heading"))
    content["nickname"] = sanitize_text(get_param("nickname"))
    update = edit_user_page(page, content, emptyallowed=True)
    if "error" in update:
        return failedit(update["error"], "headingerror")
    return signal(
        response={"done": True, "num": update["version"]["num"]},
        html={
            "headingerror": "",
            "heading": render_template(
                "heading.html", version=update["version"], page=page
            ),
        },
    )


@app.route("/page/<title>/restore/<int:num>/", methods=["POST"])
def restore(title, num):
    page = find_page(title, primary=True)
    newpage = find_page(title, version=num)
    update = edit_user_page(page, newpage["versions"][0]["content"])
    if "error" in update:
        return failedit(update["error"], "versionerror-{}".format(num))
    return signal(redirect=get_param("href"))


@app.route("/page/<title>/flag/<int:num>/", methods=["POST"])
def flag(title, num):
    page = find_page(title, version=num)
    update = flag_version(page)
    if "error" in update:
        return failedit(update["error"], "versionerror-{}".format(num))
    return signal(redirect=get_param("href"))


@app.route("/page/<title>/unflag/<int:num>/", methods=["POST"])
def unflag(title, num):
    page = find_page(title, version=num)
    update = unflag_version(page)
    if "error" in update:
        return failedit(update["error"], "versionerror-{}".format(num))
    return signal(redirect=get_param("href"))


@app.route("/page/<title>/version/<int:num>/")
def version(title, num):
    page = find_page(title, version=num)
    return render_template(
        "user-page-version.html", version=page["versions"][0], title=title, page=page
    )


@app.route("/page/<title>/history/")
def history(title):
    page = db.pages.find_one({"titles": title})
    if not can_edit(page):
        abort(401)
    return render_template(
        "user-page-history.html",
        currentversion=page["versions"][-1],
        oldversions=reversed(page["versions"][1:-1]),
        initialversion=page["versions"][0],
        title=title,
        page=page,
    )


@app.route("/page/<title>/freeze/", methods=["POST"])
def freeze(title):
    page = db.pages.find_one({"titles": title}, {"owner": 1, "currenttitle": 1})
    freeze_page(page)
    return signal(redirect=url_for("page", title=title))


@app.route("/page/<title>/unfreeze/", methods=["POST"])
def unfreeze(title):
    page = db.pages.find_one({"titles": title}, {"owner": 1, "currenttitle": 1})
    unfreeze_page(page)
    return signal(redirect=url_for("page", title=title))


@app.route("/authenticate/", methods=["POST"])
def authenticate():
    verified = verify_password(get_param("email"), get_param("password"))
    g.user = verified.get("user")
    g.reissue_token = True
    if g.user is None:
        return signal(html={"loginerror": verified["error"]})
    return signal(redirect=get_param("href"))


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    g.rerender = True
    return signal(redirect=get_param("href"))
