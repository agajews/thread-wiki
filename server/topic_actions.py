from .action import TopicPageAction, can_edit, redirect


class View(TopicPageAction):
    def respond(self):
        return render_template(
            "topic-page.html", version=self.page.versions[-1], page=self.page
        )


class ViewVersion(TopicPageAction):
    def setup(self, num):
        self.num = num

    def respond(self):
        return render_template(
            "topic-page-version.html",
            version=self.page.versions[self.num],
            page=self.page,
        )


class ViewHistory(TopicPageAction):
    authorizers = [can_edit]

    def respond(self):
        return render_template("topic-page-history.html", page=self.page)


class ViewEdit(TopicPageAction):
    authorizers = [can_edit]

    def respond(self):
        return render_template(
            "edit-topic-page.html", version=self.page.versions[-1], page=self.page
        )


class SubmitEdit(TopicPageAction):
    authorizers = [can_edit, check_race]

    def execute(self):
        summary, sections = separate_sections(sanitize_html(request["body"]))
        name = sanitize_text(self.require("name"))
        content = TopicPageContent(TopicPageHeading(name), summary, sections)
        self.page.edit(content)

    respond = redirect(url_for("page", title=self.page.title))


class SubmitUpdate(TopicPageAction):
    authorizers = [can_edit, check_race]

    def setup(self):
        self.update_heading = False
        self.update_summary = False
        self.update_sections = []

    def execute(self):
        content = self.page.versions[-1].content.copy()
        if "name" in self.params:
            self.update_heading = True
            content.heading = TopicPageHeading(self.params["name"])
        if "summary" in self.params:
            self.update_summary = True
            content.summary = sanitize_html(self.params["summary"])
        if "sections" in self.params:
            sections = self.require("sections", dict)
            for key, body in sections.keys():
                idx = self.cast(key, int)
                self.update_sections.append(idx)
                content.sections[idx].body = sanitize_html(body)
        self.page.edit(content)

    def respond(self):
        html = {}
        if self.update_heading:
            html["heading"] = render_template(
                "topic-page-heading.html", heading=self.page.content.heading
            )
        if self.update_summary:
            html["summary"] = render_template(
                "topic-page-summary.html", summary=self.page.content.summary
            )
        for idx in self.update_sections:
            html["section-{}".format(idx)] = render_template(
                "topic-page-section.html", section=self.page.content.sections_dict[idx]
            )
        return jsonify({"html": html})
