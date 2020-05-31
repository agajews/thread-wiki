import random
import csv
import os
import re
from flask import render_template, g

from .app import app
from .sections import separate_sections
from .user import User
from .page import Page
from .user_page import UserPage
from .topic_page import TopicPage
from .errors import *
from .html_utils import (
    title_to_name,
    name_to_title,
)


def open_file(name):
    data = []
    with open(os.path.join(os.path.dirname(__file__), name)) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=",")
        for row in csv_reader:
            data.append(row[0])
    return data


def split_email(email):
    match = re.fullmatch("^([a-zA-Z0-9.\\-_]+)@([a-zA-Z0-9\\-_\\.]+)\\.edu$", email)
    return match.groups()


nouns = open_file("random-words/Nouns.csv")
verbs = open_file("random-words/Verbs.csv")
adjectives = open_file("random-words/Adjectives.csv")
titles = open_file("random-words/Titles.csv")
quotes = open_file("random-words/Quotes.csv")


def random_noun():
    return random.choice(nouns)


def random_verb():
    return random.choice(verbs)


def random_adjective():
    return random.choice(adjectives)


def random_title():
    return random.choice(titles)


@app.context_processor
def inject_generators():
    return dict(
        random_noun=random_noun,
        random_verb=random_verb,
        random_adjective=random_adjective,
        random_title=random_title,
    )


def generate_user_template(name, domain):
    quote = random.choice(quotes).format(
        noun=random.choice(nouns), verb=random.choice(verbs), email=name
    )
    # possible injection attack here? probably not if emails are legitimate,
    # but there might be places that let you make arbitrary aliases...
    return render_template("user-template.html", name=name, domain=domain, quote=quote)


def generate_aka():
    return " ".join(s.capitalize() for s in [random_noun(), random_title()])


def generate_topic_template(name):
    return render_template("topic-template.html", name=name)


def generate_university_template(name):
    return render_template("university-template.html", name=name)


def is_email(email):
    if re.fullmatch(
        "^[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+\\.)+[a-zA-Z0-9\\-_]+$", email
    ):
        return True
    return False


def is_valid_email(email):
    if re.fullmatch("^[a-zA-Z0-9.\\-_]+@([a-zA-Z0-9\\-_]+\\.)+edu$", email):
        return True
    return False


def create_user_page(email):
    name, domain = split_email(email)
    summary, sections = separate_sections(generate_user_template(name, domain))
    owner = User.create_or_return(email)
    try:
        Page.find(domain)
    except PageNotFound:
        create_university_page(domain)
    return UserPage.create_or_return(sections, summary, email, generate_aka(), owner)


def create_university_page(title):
    name = title_to_name(title)
    summary, sections = separate_sections(generate_university_template(name))
    try:
        Page.find("Universities")
    except PageNotFound:
        create_topic_page("Universities")
    return TopicPage.create_or_return(sections, summary, name)


def create_topic_page(title):
    name = title_to_name(title)
    summary, sections = separate_sections(generate_topic_template(name))
    return TopicPage.create_or_return(sections, summary, name)


def try_create_page(title):
    assert g.user is not None and g.user.can_create
    if is_valid_email(title):
        return create_user_page(title)
    elif is_email(title):
        return None
    return create_topic_page(title)
