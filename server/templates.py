def generate_user_template(email):
    return "<p>The homo sapiens {0} is simply the best.</p><h2>Best Quotes</h2><p>Yoyoyo, it's my boy {0}.</p><h2>Early life</h2><p>One day, our protagonist {0} was born. Later, they went to college.</p>".format(
        email
    )


def generate_aka():
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


def generate_topic_template(name):
    return "<p>{0} is a subject.</p><h2>The beginning</h2><p>The beginning of something is always the end of something else.</p><h2>Sticky</h2><p>This page exists for the advancement of human civilization.</p>".format(
        name
    )
