import itertools
from pymodm import fields, MongoModel, EmbeddedMongoModel
from difflib import SequenceMatcher

from .html_utils import (
    get_sequence,
    markup_changes,
    generate_html,
    Token,
    header_tags,
    DataToken,
)


class Section(EmbeddedMongoModel):
    heading = fields.CharField()
    level = fields.IntegerField()
    body = fields.CharField()


class SectionDiff(EmbeddedMongoModel):
    heading = fields.CharField()
    level = fields.IntegerField()
    body = fields.CharField()
    body_diff = fields.CharField()
    inserted = fields.BooleanField(default=False)
    deleted = fields.BooleanField(default=False)
    edited = fields.BooleanField(default=False)
    idx = fields.IntegerField(default=None)

    @property
    def is_empty(self):
        return not (self.inserted or self.deleted or self.edited)


def get_header_level(tag):
    for (tag, attr) in tag.context:
        if tag in header_tags:
            return int(tag[1])
    return None


def extract_text(tokens):
    text = ""
    for token in tokens:
        if isinstance(token, DataToken):
            text += token.data
    return text


def separate_sections(data):
    sequence = get_sequence(data)
    keys = []
    groups = []
    for key, group in itertools.groupby(sequence, key=get_header_level):
        keys.append(key)
        groups.append(list(group))
    i = 0
    if keys[0] is None:
        summary = generate_html(groups[0])
        i += 1
    else:
        summary = ""
    sections = []
    while i < len(groups):
        hasbody = i + 1 < len(groups) and keys[i + 1] is None
        body = generate_html(groups[i + 1]) if hasbody else ""
        sections.append(
            Section(
                heading=extract_text(groups[i]),
                body=body,
                level=get_header_level(groups[i][0]),
            )
        )
        i += 2 if hasbody else 1
    return summary, sections


class SectionToken(Token):
    def __init__(self, section):
        self.heading = section.heading
        self.body = section.body
        self.level = section.level
        super().__init__((self.heading, self.level))


def diff_sections(sections_a, sections_b, concise=False):
    sequence_a = [SectionToken(section) for section in sections_a]
    sequence_b = [SectionToken(section) for section in sections_b]
    matcher = SequenceMatcher(isjunk=None, a=sequence_a, b=sequence_b, autojunk=False)
    merged_sequence = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                section_a = sequence_a[i]
                section_b = sequence_b[j]
                edited = section_a.body != section_b.body
                body_diff = markup_changes(
                    section_a.body, section_b.body, concise=concise
                )
                merged_sequence.append(
                    SectionDiff(
                        heading=section_b.heading,
                        level=section_b.level,
                        body_diff=body_diff,
                        body=section_b.body,
                        idx=j,
                        edited=edited,
                    )
                )
        if tag == "replace" or tag == "delete":
            for section in sequence_a[i1:i2]:
                body_diff = markup_changes(section.body, "", concise=concise)
                merged_sequence.append(
                    SectionDiff(
                        heading=section.heading,
                        level=section.level,
                        body_diff=body_diff,
                        body=section.body,
                        deleted=True,
                    )
                )
        if tag == "replace" or tag == "insert":
            for j in range(j1, j2):
                section = sequence_b[j]
                body_diff = markup_changes("", section.body, concise=concise)
                merged_sequence.append(
                    SectionDiff(
                        heading=section.heading,
                        level=section.level,
                        body_diff=body_diff,
                        body=section.body,
                        idx=j,
                        inserted=True,
                    )
                )
    return merged_sequence
