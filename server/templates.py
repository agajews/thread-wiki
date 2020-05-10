import random
import csv
import os
from flask import render_template

from .app import app


def open_file(name):
    data = []
    with open(os.path.join(os.path.dirname(__file__), name)) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=",")
        for row in csv_reader:
            data.append(row[0])
    return data


def get_email_name(email):
    name = ""
    for char in email:
        if char == "@":
            break
        name += char
    return name


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


def generate_user_template(email):
    name = get_email_name(email)
    quote = random.choice(quotes).format(
        noun=random.choice(nouns), verb=random.choice(verbs), email=name
    )
    # possible injection attack here? probably not if emails are legitimate,
    # but there might be places that let you make arbitrary aliases...
    return render_template("user-template.html", email=name, quote=quote)


def generate_aka():
    return " ".join([random_adjective(), random_noun(), random_title()])


def generate_topic_template(name):
    return render_template("topic-template.html", name=name)
