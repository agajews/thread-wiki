import re
from flask import render_template, abort, request, jsonify, g
from flask import redirect as flask_redirect
from functools import wraps
from pymongo import DESCENDING

from .app import app, url_for
from .html_utils import (
    sanitize_html,
    sanitize_paragraph,
    sanitize_text,
    title_to_name,
    name_to_title,
)
from .sections import separate_sections, Section
from .templates import try_create_page, is_edu_email, is_email
from .page import Page
from .user import User
from .user_page import UserPage, UserVersionDiff
from .topic_page import TopicPage
from .bookmarks import BookmarksPage
from .mail import send_email
from .errors import *
from . import auth  # just to load handlers into the app


@app.context_processor
def inject_models():
    return dict(UserPage=UserPage, TopicPage=TopicPage)


def cast_param(val, cls):
    try:
        val = cls(val)
    except Exception:
        raise Malformed()
    return val


def get_param(param, cls=None):
    params = request.get_json(silent=True)
    if params is None or param not in params:
        print("Missing param {}".format(param))
        raise Malformed()
    if cls is not None:
        return cast_param(params[param], cls)
    return params[param]


def error_handling(fun):
    @wraps(fun)
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except Malformed as e:
            abort(400)
        except NotAllowed:
            # abort(401)
            return flask_redirect(url_for("recent"))
        except PageNotFound:
            abort(404)

    return wrapped_fun


def page_errors(fun):
    @wraps(fun)
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
        except EmptyString:
            return error("Lel, that shouldn't be empty.")

    return wrapped_fun


def user_page_errors(fun):
    @wraps(fun)
    @page_errors
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except DuplicatePage:
            return error("Lel, someone with the same name already has that aka!")

    return wrapped_fun


def topic_page_errors(fun):
    @wraps(fun)
    @page_errors
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except DuplicatePage:
            return error("Lel, a page with that name already exists!")

    return wrapped_fun


def bookmarks_page_errors(fun):
    @wraps(fun)
    @page_errors
    def wrapped_fun(*args, **kwargs):
        return fun(*args, **kwargs)

    return wrapped_fun


def can_edit(fun):
    @wraps(fun)
    def wrapped_fun(*args, **kwargs):
        if not g.page.can_edit:
            raise NotAllowed()
        return fun(*args, **kwargs)

    return wrapped_fun


def is_owner(fun):
    @wraps(fun)
    def wrapped_fun(*args, **kwargs):
        if g.user != g.page.owner:
            raise NotAllowed()
        return fun(*args, **kwargs)

    return wrapped_fun


def catch_race(fun):
    @wraps(fun)
    def wrapped_fun(*args, **kwargs):
        if g.page.freshness != get_param("freshness", int):
            raise RaceCondition()
        return fun(*args, **kwargs)

    return wrapped_fun


def reload():
    return jsonify({"redirect": get_param("href")})


def redirect(href):
    return jsonify({"redirect": href})


def rerender(html, **kwargs):
    return jsonify({"html": html, "response": kwargs})


def error(message):
    return jsonify({"html": {get_param("errorid"): message}})


@app.route("/")
@error_handling
def index():
    if g.user is None:
        return flask_redirect(url_for("recent"))
    return flask_redirect(url_for("bookmarks"))


@app.route("/recent/")
@error_handling
def recent():
    pages = list(
        Page.objects.raw({"versions.1": {"$exists": True}})
        .order_by([("last_edited", DESCENDING)])
        .limit(20)
    )
    return render_template("recent.html", pages=pages)


def find_user_display():
    if g.user is None:
        return g.page.primary_diffs[-1]
    elif g.page.can_accept:
        return g.page.merged_diff
    elif g.page.is_owner:
        return g.page.primary_diffs[-1]
    return g.page.user_primary_diff


@app.route("/page/<title>/")
@error_handling
def page(title):
    try:
        g.page = Page.find(title)
    except PageNotFound as e:
        if g.user is None or not g.user.can_create:
            raise e
        g.page = try_create_page(title)
        if g.page is None:
            raise e
    if isinstance(g.page, UserPage):
        display = find_user_display()
        if title == g.page.titles[0]:
            display_email = title
        else:
            display_email = None
        return render_template(
            "user-page.html",
            display=display,
            is_owner=g.user == g.page.owner,
            display_email=display_email,
        )
    elif isinstance(g.page, TopicPage):
        return render_template("topic-page.html", display=g.page.versions[-1])


@app.route("/bookmarks/")
@error_handling
def bookmarks():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    links = g.page.latest.links
    pages = list(
        Page.objects.raw({"titles": {"$in": links}})
        .order_by([("last_edited", DESCENDING)])
        .limit(10)
    )
    return render_template(
        "bookmarks-page.html", display=g.page.versions[-1], pages=pages
    )


@app.route("/pageorbookmarks/")
def pageorbookmarks():
    if g.user is None:
        return flask_redirect(url_for("recent"))
    elif g.user.passhash is None:
        return flask_redirect(url_for("bookmarks"))
    return flask_redirect(url_for("page", title=g.user.email))


@can_edit
def view_user_edit():
    if g.page.can_accept:
        version = g.page.merged_version
    elif g.page.is_owner:
        version = g.page.versions[-1]
    else:
        version = g.page.user_version
    return render_template("edit-user-page.html", version=version)


@can_edit
def view_topic_edit():
    return render_template("edit-topic-page.html", version=g.page.versions[-1])


@app.route("/page/<title>/edit/")
@error_handling
def edit(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return view_user_edit()
    elif isinstance(g.page, TopicPage):
        return view_topic_edit()


@app.route("/bookmarks/edit/")
@error_handling
def edit_bookmarks():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    return render_template("edit-bookmarks-page.html", version=g.page.versions[-1])


@user_page_errors
@can_edit
@catch_race
def edit_user_page():
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    name = sanitize_text(get_param("name"))
    aka = sanitize_text(get_param("aka"))
    g.page.edit(sections, summary, name, aka)
    return redirect(url_for("page", title=g.page.title))


@topic_page_errors
@can_edit
@catch_race
def edit_topic_page():
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    name = sanitize_text(get_param("name"))
    g.page.edit(sections, summary, name)
    return redirect(url_for("page", title=g.page.title))


@app.route("/page/<title>/submitedit/", methods=["POST"])
@error_handling
def submitedit(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return edit_user_page()
    elif isinstance(g.page, TopicPage):
        return edit_topic_page()


@app.route("/bookmarks/submitedit/", methods=["POST"])
@error_handling
@bookmarks_page_errors
def bookmarks_submitedit():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    summary, sections = separate_sections(sanitize_html(get_param("body")))
    g.page.edit(sections, summary)
    return redirect(url_for("bookmarks"))


@user_page_errors
@can_edit
@catch_race
def update_user_page():
    update_heading = False
    update_summary = False
    update_sections = []

    # TODO: maybe move the new section logic to page class
    old_version = g.page.user_version
    update = get_param("update", dict)
    name = old_version.name
    aka = old_version.aka
    summary = old_version.summary
    sections = old_version.sections[:]
    if "name" in update:
        name = sanitize_text(update["name"])
        update_heading = True
    if "aka" in update:
        aka = sanitize_text(update["aka"])
        update_heading = True
    if "summary" in update:
        summary = sanitize_paragraph(update["summary"])
        update_summary = True
    if "sections" in update:
        for key, body in cast_param(update["sections"], dict).items():
            idx = cast_param(key, int)
            if not 0 <= idx < len(sections):
                raise Malformed()
            sections[idx] = Section(
                heading=sections[idx].heading,
                level=sections[idx].level,
                body=sanitize_paragraph(body),
            )
            update_sections.append(idx)

    try:
        g.page.edit(sections, summary, name, aka)
    except EmptyEdit:
        pass

    html = {}
    display = find_user_display()
    if update_heading:
        html["heading"] = render_template("user-page-heading.html", display=display)
    if update_summary:
        html["summary"] = render_template("user-page-summary.html", display=display)
    for idx in update_sections:
        html["section-{}".format(idx)] = render_template(
            "user-page-section.html", section=display.sections_dict[idx]
        )
    return rerender(html, freshness=g.page.freshness)


@topic_page_errors
@can_edit
@catch_race
def update_topic_page():
    update_heading = False
    update_summary = False
    update_sections = []

    old_version = g.page.latest
    update = get_param("update", dict)
    name = old_version.name
    summary = old_version.summary
    sections = old_version.sections[:]
    if "name" in update:
        name = sanitize_text(update["name"])
        update_heading = True
    if "summary" in update:
        summary = sanitize_paragraph(update["summary"])
        update_summary = True
    if "sections" in update:
        for key, body in cast_param(update["sections"], dict).items():
            idx = cast_param(key, int)
            if not 0 <= idx < len(sections):
                raise Malformed()
            sections[idx] = Section(
                heading=sections[idx].heading,
                level=sections[idx].level,
                body=sanitize_paragraph(body),
            )
            update_sections.append(idx)

    try:
        g.page.edit(sections, summary, name)
    except EmptyEdit:
        pass

    html = {}
    display = g.page.versions[-1]
    if update_heading:
        html["heading"] = render_template("topic-page-heading.html", display=display)
    if update_summary:
        html["summary"] = render_template("topic-page-summary.html", display=display)
    for idx in update_sections:
        html["section-{}".format(idx)] = render_template(
            "topic-page-section.html", section=display.sections[idx], idx=idx
        )
    return rerender(html, freshness=g.page.freshness)


@app.route("/page/<title>/update/", methods=["POST"])
@error_handling
def update(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return update_user_page()
    elif isinstance(g.page, TopicPage):
        return update_topic_page()


@app.route("/bookmarks/update/", methods=["POST"])
@error_handling
@bookmarks_page_errors
def update_bookmarks():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()

    update_summary = False
    update_sections = []

    old_version = g.page.latest
    update = get_param("update", dict)
    summary = old_version.summary
    sections = old_version.sections[:]
    if "summary" in update:
        summary = sanitize_paragraph(update["summary"])
        update_summary = True
    if "sections" in update:
        for key, body in cast_param(update["sections"], dict).items():
            idx = cast_param(key, int)
            if not 0 <= idx < len(sections):
                raise Malformed()
            sections[idx] = Section(
                heading=sections[idx].heading,
                level=sections[idx].level,
                body=sanitize_paragraph(body),
            )
            update_sections.append(idx)

    try:
        g.page.edit(sections, summary)
    except EmptyEdit:
        pass

    html = {}
    display = g.page.versions[-1]
    if update_summary:
        html["summary"] = render_template(
            "bookmarks-page-summary.html", display=display
        )
    for idx in update_sections:
        html["section-{}".format(idx)] = render_template(
            "bookmarks-page-section.html", section=display.sections[idx], idx=idx
        )
    return rerender(html)


@page_errors
@can_edit
@catch_race
def restore_version(num):
    if not 0 <= num < len(g.page.versions):
        raise Malformed()
    g.page.restore(num)
    return reload()


@app.route("/page/<title>/restore/", methods=["POST"])
@error_handling
def restore(title):
    num = get_param("num", int)
    g.page = Page.find(title)
    return restore_version(num)


@app.route("/bookmarks/restore/", methods=["POST"])
@error_handling
@bookmarks_page_errors
def restore_bookmarks():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    num = get_param("num", int)
    if not 0 <= num < len(g.page.versions):
        raise Malformed()
    g.page.restore(num)
    return reload()


@app.route("/page/<title>/bookmark/", methods=["POST"])
@error_handling
@bookmarks_page_errors
def addbookmark(title):
    if g.user is None:
        raise NotAllowed()
    bookmarks = BookmarksPage.find()
    bookmarks.add_bookmark(title)
    # return rerender({"add-bookmark": "<span class='added-bookmark'>Added :)</span>"})
    return reload()


@user_page_errors
@is_owner
@catch_race
def accept_version():
    if not g.page.can_accept:
        raise NotAllowed()
    g.page.accept()
    return reload()


@app.route("/page/<title>/accept/", methods=["POST"])
@error_handling
def accept(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return accept_version()
    else:
        raise Malformed()


@page_errors
@can_edit
def flag_version(num):
    # TODO: partial rerendering
    if not 1 <= num < len(g.page.versions) - 1:
        raise Malformed()
    if g.page.versions[num].is_flagged:
        raise AlreadyFlagged()
    if g.page.versions[num].editor == g.user:
        raise FlagYourself
    g.page.versions[num].set_flag()
    return reload()


@app.route("/page/<title>/flag/", methods=["POST"])
@error_handling
def flag(title):
    num = get_param("num", int)
    g.page = Page.find(title)
    return flag_version(num)


@page_errors
@can_edit
def unflag_version(num):
    if not 1 <= num < len(g.page.versions) - 1:
        raise Malformed()
    if not g.page.versions[num].is_flagged:
        return reload()
    g.page.versions[num].set_unflag()
    return reload()


@app.route("/page/<title>/unflag/", methods=["POST"])
@error_handling
def unflag(title):
    num = get_param("num", int)
    g.page = Page.find(title)
    return unflag_version(num)


@app.route("/page/<title>/version/<int:num>/")
@error_handling
def version(title, num):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        if not 0 <= num < len(g.page.versions):
            raise Malformed()
        return render_template("user-page-version.html", version=g.page.versions[num])
    elif isinstance(g.page, TopicPage):
        if not 0 <= num < len(g.page.versions):
            raise Malformed()
        return render_template("topic-page-version.html", version=g.page.versions[num])


@app.route("/bookmarks/version/<int:num>/")
@error_handling
def bookmarks_version(num):
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    if not 0 <= num < len(g.page.versions):
        raise Malformed()
    return render_template("bookmarks-page-version.html", version=g.page.versions[num])


def view_user_history():
    return render_template("user-page-history.html")


def view_topic_history():
    return render_template("topic-page-history.html")


@app.route("/page/<title>/history/")
@error_handling
def history(title):
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return view_user_history()
    elif isinstance(g.page, TopicPage):
        return view_topic_history()


@app.route("/bookmarks/history/")
@error_handling
def bookmarks_history():
    if g.user is None:
        raise NotAllowed()
    g.page = BookmarksPage.find()
    return render_template("bookmarks-page-history.html")


@app.route("/search/?<query>")
@error_handling
def search(query):
    if g.user is not None and is_email(query):
        g.user.set_hide_search_hint()
        return flask_redirect(url_for("page", title=query))
    title = name_to_title(query)
    can_create = False
    try:
        Page.find(title)
    except PageNotFound:
        can_create = g.user is not None and g.user.can_create
    if g.user is not None:
        bookmarks_pages = BookmarksPage.search(query)
        search_pages = [
            page for page in Page.search(query) if page not in bookmarks_pages
        ]
        pages = bookmarks_pages + search_pages
    else:
        pages = Page.search(query)
    return render_template(
        "search.html",
        pages=pages,
        query=query,
        can_create=can_create,
        title_to_create=title,
    )


@app.route("/submitsearch/", methods=["POST"])
@error_handling
def submitsearch():
    return redirect(url_for("search", query=get_param("query")))


@user_page_errors
@is_owner
def freeze_user_page():
    g.page.freeze()
    return reload()


@app.route("/page/<title>/freeze/", methods=["POST"])
@error_handling
def freeze(title):
    g.page = Page.find(title)
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
    g.page = Page.find(title)
    if isinstance(g.page, UserPage):
        return unfreeze_user_page()
    else:
        raise Malformed()


def auth_errors(fun):
    @wraps(fun)
    def wrapped_fun(*args, **kwargs):
        try:
            return fun(*args, **kwargs)
        except UserNotFound:
            return error("Lel, can't find that account")
        except IncorrectPassword:
            return error("Lel, wrong password")

    return wrapped_fun


@app.route("/login/")
@error_handling
def login():
    if g.user is not None:
        return flask_redirect(url_for("bookmarks"))
    return render_template("login-page.html", hide_header_login=True)


@app.route("/authenticate/", methods=["POST"])
@error_handling
@auth_errors
def authenticate():
    user = User.find(email=get_param("email"))
    if not user.verify_password(get_param("password")):
        raise IncorrectPassword()
    g.user = user
    g.reissue_token = True
    return reload()


@app.route("/forgotpassword/", methods=["POST"])
@error_handling
@auth_errors
def forgotpassword():
    user = User.find(email=get_param("email"))
    send_email(
        user.email,
        "Thread sign-in link",
        render_template("forgot-password-email.html", user=user),
        render_template("forgot-password-email.txt", user=user),
    )
    return error("Check your email for a sign-in link.")


@app.route("/setpassword/", methods=["POST"])
@error_handling
@auth_errors
def setpassword():
    # TODO: make password reset, forgot password
    if g.user is None:
        return reload()
    g.user.set_password(get_param("password"))
    return reload()


@app.route("/resetpassword/", methods=["POST"])
@error_handling
@auth_errors
def resetpassword():
    if g.user is None:
        return reload()
    g.user.reset_password()
    return reload()


@app.route("/logout/", methods=["POST"])
def logout():
    g.user = None
    return reload()
