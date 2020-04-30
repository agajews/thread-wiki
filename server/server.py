from flask import render_template, abort, request, jsonify, g, redirect
import re
from copy import deepcopy
from .app import app, db, timestamp, url_for
from .auth import verify_password, generate_auth_token
from .html_utils import sanitize_html, sanitize_text, separate_sections
from .database import (
    find_page,
    create_user_page,
    edit_user_page,
    flag_version,
    unflag_version,
    freeze_page,
    unfreeze_page,
    can_edit,
)


def is_valid_email(email):
    if re.match("^[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+.)+edu$", email):
        return True
    return False


def create_user_page(email):
    summary, sections = separate_sections(generate_user_template(email))
    owner = User.create_or_return(email)
    heading = UserPageHeading(email, generate_aka(email))
    content = UserPageContent(heading, summary, sections)
    return UserPage.create_or_return(
        title=email,
        owner=owner._id,
        content=content,
        editor=g.user._id,
        timestamp=timestamp(),
    )


@app.route("/")
@error_handling
def index():
    pages = db.pages.find(
        {}, {"titles": {"$slice": -1}, "versions.heading": {"$slice": -1}}
    )
    return render_template("index.html", pages=pages)


@app.route("/page/<title>/")
@error_handling
def page(title):
    try:
        page = Page.find(title)
    except PageNotFound as e:
        if g.user is None:
            raise e
        if is_valid_email(title):
            page = create_user_page(title)
        else:
            page = create_topic_page(title)
    return page.View(page).run()


def error_handling(fun):
    def wrapped_fun(*args, **kwargs):
        try:
            fun(*args, **kwargs)
        except Malformed:
            abort(400)
        except NotAllowed:
            abort(401)
        except (PageNotFound, VersionNotFound):
            abort(404)

    return wrapped_fun


@app.route("/page/<title>/edit/")
@error_handling
def edit(title):
    page = Page.find(title)
    return page.ViewEdit(page).run()


@app.route("/page/<title>/submitedit/", methods=["POST"])
@error_handling
def submitedit(title):
    page = Page.find(title, preload_primary=True)
    return page.SubmitEdit(page).run()


@app.route("/page/<title>/update/", methods=["POST"])
@error_handling
def update(title):
    page = Page.find(title, preload_primary=True)
    return page.SubmitUpdate(page).run()


@app.route("/page/<title>/restore/<int:num>/", methods=["POST"])
@error_handling
def restore(title, num):
    page = Page.find(title, preload_primary=True)
    return page.Restore(page, num).run()


@app.route("/page/<title>/flag/<int:num>/", methods=["POST"])
@error_handling
def flag(title, num):
    page = Page.find(title, preload_version=num)
    return page.Flag(page, num).run()


@app.route("/page/<title>/unflag/<int:num>/", methods=["POST"])
@error_handling
def unflag(title, num):
    page = Page.find(title, preload_version=num)
    return page.Unflag(page, num).run()


@app.route("/page/<title>/version/<int:num>/")
@error_handling
def version(title, num):
    page = Page.find(title, preload_version=num)
    return page.ViewVersion(page, num).run()


@app.route("/page/<title>/history/")
@error_handling
def history(title):
    page = Page.find(title, preload_all_versions=True)
    return page.ViewHistory(page).run()


@app.route("/page/<title>/freeze/", methods=["POST"])
@error_handling
def freeze(title):
    page = Page.find(title, preload_version=None)
    return page.Freeze(page).run()


@app.route("/page/<title>/unfreeze/", methods=["POST"])
@error_handling
def unfreeze(title):
    page = Page.find(title, preload_version=None)
    return page.Unfreeze(page).run()


def get_param(param):
    params = request.get_json(silent=True)
    if params is None or param not in params:
        raise Malformed()
    return params[param]


@app.route("/authenticate/", methods=["POST"])
@error_handling
def authenticate():
    try:
        user = User.find(email=get_param("email"))
        user.login(get_param("password"))
    except UserNotFound:
        return jsonify({"html": {get_param("errorid"): "Can't find that account"}})
    except IncorrectPassword:
        return jsonify({"html": {get_param("errorid"): "Incorrect password"}})
    except PasswordNotSet:
        return jsonify({"html": {get_param("errorid"): "Password not set"}})
    return signal(redirect=get_param("href"))


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    return signal(redirect=get_param("href"))
