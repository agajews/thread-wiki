from .action import UserPageAction, can_edit, redirect


class View(UserPageAction):
    def respond(self):
        return render_template(
            "user-page.html", version=self.page.versions[-1], page=self.page
        )


class ViewVersion(UserPageAction):
    def setup(self, num):
        self.num = num

    def respond(self):
        return render_template(
            "user-page-version.html",
            version=self.page.versions[self.num],
            page=self.page,
        )


class ViewHistory(UserPageAction):
    authorizers = [can_edit]

    def respond(self):
        return render_template("user-page-history.html", page=self.page)


class ViewEdit(UserPageAction):
    authorizers = [can_edit]

    def respond(self):
        return render_template(
            "edit-user-page.html", version=self.page.versions[-1], page=self.page
        )


class SubmitEdit(UserPageAction):
    authorizers = [can_edit, check_race]

    def execute(self):
        summary, sections = separate_sections(sanitize_html(request["body"]))
        name = sanitize_text(self.require("name"))
        aka = sanitize_text(self.require("aka"))
        content = UserPageContent(UserPageHeading(name, aka), summary, sections)
        self.page.edit(content)

    respond = redirect(url_for("page", title=self.page.current_title))


class SubmitUpdate(UserPageAction):
    authorizers = [can_edit, check_race]

    def setup(self):
        self.update_heading = False
        self.update_summary = False
        self.update_sections = []

    def execute(self):
        content = self.page.versions[-1].content.copy()
        if "name" in self.params and "aka" in self.params:
            self.update_heading = True
            content.heading = UserPageHeading(self.params["name"], self.params["aka"])
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
                "user-page-heading.html", heading=self.page.primary_diff.heading
            )
        if self.update_summary:
            html["summary"] = render_template(
                "user-page-summary.html", summary=self.page.primary_diff.summary
            )
        for idx in self.update_sections:
            html["section-{}".format(idx)] = render_template(
                "user-page-section.html",
                section=self.page.primary_diff.sections_dict[idx],
            )
        return jsonify({"html": html})
