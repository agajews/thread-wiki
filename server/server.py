from flask import render_template, abort, request, jsonify, g
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


def cast_param(val, cls):
    try:
        val = cls(val)
    except Exception:
        raise Malformed()
    return val


def get_param(param, cls=None):
    params = request.get_json(silent=True)
    if params is None or param not in params:
        raise Malformed()
    if cls is not None:
        return cast_param(params[param], cls)
    return params[param]


def error_handling(fun):
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Malformed:
            abort(400)
        except NotAllowed:
            abort(401)
        except (PageNotFound, VersionNotFound):
            abort(404)

    return wrapped_fun


def page_errors(fun):
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except RaceCondition:
            return error(
                "Lel, someone else submitted an edit while you were working on this one. Try merging your edits into that version instead (e.g. by opening the edit page in a new tab)."
            )
        except EmptyEdit:
            return error("Lel, doesn't look like you changed anything.")
        except FlagYourself:
            return error("Lel, can't flag yourself.")
        except AlreadyFlagged:
            return error("Lel, someone else flagged this already.")
        except NotAllowed:
            return error("Lel, looks like you're not allowed to do that.")

    return wrapped_fun


def user_page_errors(fun):
    @page_errors
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except DuplicateKey:
            return error("Lel, someone with the same name already has that nickname!")

    return wrapped_fun


def topic_page_errors(fun):
    @page_errors
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except DuplicateKey:
            return error("Lel, a page with that name already exists!")

    return wrapped_fun


def can_edit(fun):
    def wrapped_fun(*args, **kwargs):
        if g.user is None or not g.user.can_edit(g.page):
            raise NotAllowed()
        return fun(*args, **kwargs)

    return wrapped_fun


def is_owner(fun):
    def wrapped_fun(*args, **kwargs):
        if g.user is None or not g.user.is_owner(g.page):
            raise NotAllowed()
        return fun(*args, **kwargs)

    return wrapped_fun


def catch_race(fun):
    def wrapped_fun(*args, **kwargs):
        if len(g.page.versions) != get_param("num_versions", int):
            raise RaceCondition()
        return fun(*args, **kwargs)

    return wrapped_fun


def reload():
    return jsonify({"href": get_param("href")})


def rerender(html, **kwargs):
    return jsonify({"html": html, "response": kwargs})


def error(message):
    return jsonify({"html": {get_param("errorid"): message}})


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
        g.page = Page.find(title)
    except PageNotFound as e:
        if g.user is None:
            raise e
        if is_valid_email(title):
            g.page = create_user_page(title)
        else:
            g.page = create_topic_page(title)
    if isinstance(g.page, UserPage):
        return render_template("user-page.html", version=g.page.versions[-1])
    elif isinstance(g.page, TopicPage):
        return render_template("topic-page.html", version=g.page.versions[-1])

    return wrapped_fun


@can_edit
def view_user_edit():
    return render_template("user-page.html", version=g.page.versions[-1])


@can_edit
def view_topic_edit():
    return render_template("topic-page.html", version=g.page.versions[-1])


@app.route("/page/<title>/edit/")
@error_handling
def edit(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return view_user_edit()
    elif isinstance(g.page, TopicPage):
        return view_topic_edit()


@user_page_errors
@can_edit
@check_race
def edit_user_page():
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    name = sanitize_text(get_param("name"))
    aka = sanitize_text(get_param("aka"))
    content = UserPageContent(UserPageHeading(name, aka), summary, sections)
    g.page.edit(content)
    return redirect(url_for("page", title=g.page.title))


@topic_page_errors
@can_edit
@check_race
def edit_topic_page():
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    name = sanitize_text(get_param("name"))
    content = UserPageContent(TopicPageHeading(name), summary, sections)
    g.page.edit(content)
    return redirect(url_for("page", title=g.page.title))


@app.route("/page/<title>/submitedit/", methods=["POST"])
@error_handling
def submitedit(title):
    g.page = Page.find(title, preload_primary=True)
    if isinstance(g.page, UserPage):
        return edit_user_page()
    elif isinstance(g.page, TopicPage):
        return edit_topic_page()


@user_page_errors
@can_edit
@check_race
def update_user_page():
    update_heading = False
    update_summary = False
    update_sections = []

    content = g.page.versions[-1].content.copy()
    if "name" in get_params() and "aka" in get_params():
        update_heading = True
        content.heading = UserPageHeading(
            sanitize_text(get_param("name")), sanitize_text(get_param("aka"))
        )
    if "summary" in get_params():
        update_summary = True
        content.summary = sanitize_html(get_param("summary"))
    if "sections" in get_params():
        for key, body in get_param("sections", dict).keys():
            idx = cast_param(key, int)
            update_sections.append(idx)
            content.sections[idx].body = sanitize_html(body)

    try:
        g.page.edit(content)
    except EmptyEdit:
        pass

    html = {}
    if update_heading:
        html["heading"] = render_template(
            "user-page-heading.html", heading=g.page.primary_diff.heading
        )
    if update_summary:
        html["summary"] = render_template(
            "user-page-summary.html", summary=g.page.primary_diff.summary
        )
    for idx in update_sections:
        html["section-{}".format(idx)] = render_template(
            "user-page-section.html", section=g.page.primary_diff.sections_dict[idx]
        )
    return rerender(html, num_versions=len(g.page.versions))


@topic_page_errors
@can_edit
@check_race
def update_topic_page():
    update_heading = False
    update_summary = False
    update_sections = []

    content = g.page.versions[-1].content.copy()
    if "name" in get_params():
        update_heading = True
        content.heading = UserPageHeading(sanitize_text(get_param("name")))
    if "summary" in get_params():
        update_summary = True
        content.summary = sanitize_html(get_param("summary"))
    if "sections" in get_params():
        for key, body in get_param("sections", dict).keys():
            idx = cast_param(key, int)
            update_sections.append(idx)
            content.sections[idx].body = sanitize_html(body)

    try:
        g.page.edit(content)
    except EmptyEdit:
        pass

    html = {}
    if update_heading:
        html["heading"] = render_template(
            "topic-page-heading.html", heading=g.page.content.heading
        )
    if update_summary:
        html["summary"] = render_template(
            "topic-page-summary.html", summary=g.page.content.summary
        )
    for idx in update_sections:
        html["section-{}".format(idx)] = render_template(
            "topic-page-section.html", section=g.page.content.sections_dict[idx]
        )
    return rerender(html, num_versions=len(g.page.versions))


@app.route("/page/<title>/update/", methods=["POST"])
@error_handling
def update(title):
    g.page = Page.find(title, preload_primary=True)
    if isinstance(g.page, UserPage):
        return update_user_page()
    elif isinstance(g.page, TopicPage):
        return update_topic_page()


@page_errors
@can_edit
@check_race
def restore_version(num):
    g.page.restore_version(num)
    return reload()


@app.route("/page/<title>/restore/<int:num>/", methods=["POST"])
@error_handling
def restore(title, num):
    g.page = Page.find(title, preload_primary=True)
    return restore_version(num)


@page_errors
@can_edit
def flag_version(num):
    g.page.flag_version(num)
    return reload()


@app.route("/page/<title>/flag/<int:num>/", methods=["POST"])
@error_handling
def flag(title, num):
    g.page = Page.find(title, preload_version=num)
    return flag_version(num)


@page_errors
@can_edit
def unflag_version(num):
    g.page.unflag_version(num)
    return reload()


@app.route("/page/<title>/unflag/<int:num>/", methods=["POST"])
@error_handling
def unflag(title, num):
    g.page = Page.find(title, preload_version=num)
    return unflag_version(num)


@app.route("/page/<title>/version/<int:num>/")
@error_handling
def version(title, num):
    g.page = Page.find(title, preload_version=num)
    if isinstance(g.page, UserPage):
        return render_template("user-page-version.html", version=g.page.versions[num])
    elif isinstance(g.page, TopicPage):
        return render_template("topic-page-version.html", version=g.page.versions[num])


@can_edit
def view_user_history():
    return render_template("user-page-history.html")


@can_edit
def view_topic_history():
    return render_template("topic-page-history.html")


@app.route("/page/<title>/history/")
@error_handling
def history(title):
    g.page = Page.find(title, preload_all_versions=True)
    if isinstance(page, UserPage):
        return view_user_history()
    elif isinstance(page, TopicPage):
        return view_topic_history()


@user_page_errors
@is_owner
def freeze_user_page():
    g.page.freeze()
    return reload()


@app.route("/page/<title>/freeze/", methods=["POST"])
@error_handling
def freeze(title):
    g.page = Page.find(title, preload_version=None)
    if isinstance(g.page, UserPage):
        return freeze_user_page()
    else:
        raise Malformed()


@user_page_errors
@is_owner
def unfreeze_user_page():
    g.page.unfreeze()
    return reload()


@app.route("/page/<title>/unfreeze/", methods=["POST"])
@error_handling
def unfreeze(title):
    g.page = Page.find(title, preload_version=None)
    if isinstance(g.page, UserPage):
        return unfreeze_user_page()
    else:
        raise Malformed()


def auth_errors(fun):
    def wrapped_fun(*args, **kwargs):
        try:
            fun(*args, **kwargs)
        except UserNotFound:
            return error("Can't find that account")
        except IncorrectPassword:
            return error("Incorrect password")
        except PasswordNotSet:
            return error("Password not set")

    return wrapped_fun


@app.route("/authenticate/", methods=["POST"])
@error_handling
@auth_errors
def authenticate():
    user = User.find(email=get_param("email"))
    user.login(get_param("password"))
    return reload()


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    return reload()
