from server.html_utils import markup_changes, merge_html

original = """
<h1>This is my HTML!</h1>
Test summary woot
<h2>Just a heading</h2>
<div>This <b>is a</b> bold section.</div>
<h2>Another heading!</h2>
<div>This is <i><b>a double</b></i> boldsection</div>
"""

diff_a = """
<h1>This is my HTML! Yay.</h1>
Test summary woot
<h2>Just a heading</h2>
<div>This is a bold section.</div>
<h2>Another heading!</h2>
<div>This is <i><b>a double</b></i> boldsection</div>
<h2>I have also added a section</h2>
"""

diff_b = """
<h1>I have two h1's hahahaaaa</h1>
<h1>This is my HTML!</h1>
Test summary woot yoop
<h2>Just a heading</h2>
<div>This is a bold section.</div>
<h2>Another heading!</h2>
<div>This is <i><b>a double</b></i> boldsection</div>
<h2>I have added a section</h2>
"""

# print(markup_changes(original, diff_a))
# print()
# print(markup_changes(original, diff_b))
print(merge_html(original, [diff_a, diff_b]))
