"""The subtasks of a content item, each with a prompt to paste into the client's Claude project.

A writer works through a page in pieces: the title and meta description, the headings, the body. Each piece is a subtask holding the brief
and a prompt for the client's Claude project, which already knows the brand's voice and sources. The prompts say what to produce and what to
check; they do not name the brand or restate its voice, because the project holds those.
"""

from __future__ import annotations

from app.models.client import Client
from app.models.schema_tools import ContentItem
from app.services.teamwork_subtasks import Sub

#: Teamwork's descriptions are generous, but a brief pasted in whole should not crowd out the prompt.
MAX_BRIEF = 5000


def _wrap(project: str, prompt: str, brief: str, done: str) -> str:
    parts = [f"Paste this into the {project} Claude project.", "", "PROMPT", prompt.strip()]
    if brief:
        parts += ["", "BRIEF", brief]
    parts += ["", "Done when", done]
    return "\n".join(parts)


def subtasks(item: ContentItem, client: Client) -> list[Sub]:
    project = client.client_name
    new = item.kind == "new_page"
    brief = (item.notes or "").strip()[:MAX_BRIEF]
    about = f"“{item.target}”" if new else f"the page {item.target}"

    if new:
        title = (
            f"Write 5 title tag options and 3 meta descriptions for a new page about {about}.\n"
            "Titles: 60 characters or fewer, the subject near the front, plain words, no clickbait. "
            "Meta descriptions: 155 characters or fewer, say what the reader gets, and end on a reason to click. "
            "For each, one line on why it works. Recommend one title and one meta description."
        )
        headings = (
            f"Draft the heading outline for a new page about {about}: one H1, an H2 for each section, and H3s where a section has parts.\n"
            "Write each heading as a question people ask or a plain statement of the subject, in the words people search. "
            "Each H2 must make sense when quoted on its own. Put the sections in the order a reader needs them, and note under each H2 "
            "the one point it must make. Use the sections and questions in the brief."
        )
        body = (
            f"Write the page about {about}, following the approved outline: [paste the outline from the headings subtask].\n"
            "Answer each question directly in the first sentence under its heading, then support it. Use only claims you can source, "
            "and mark anything that needs a fact check or a link. Cover the subjects and avoid what the brief lists. "
            "Match the target length in the brief. End with one clear next step for the reader."
        )
        finish = "The page is published, linked from the pages that should point to it, and its schema is in place."
        titles_done = "One title and one meta description are chosen and entered in the page."
        headings_done = "The outline is approved: one H1, H2s that stand alone, every question in the brief placed under a heading."
        body_done = "The draft follows the outline, every claim is sourced or marked, and an editor has read it."
    else:
        title = (
            f"Review the title tag and meta description of {about}. Here are the current ones: [paste them].\n"
            "Say whether they still match what the page now covers and what people search for. If not, write 3 title options "
            "(60 characters or fewer) and 2 meta descriptions (155 or fewer) that fix it, and say what you changed and why. "
            "If they are fine, say so and leave them."
        )
        headings = (
            f"Review the headings of {about}. Here is the current outline: [paste the H1 to H3 headings].\n"
            "Using the refresh plan in the brief, list which headings to keep, reword, add, move or remove, and why. "
            "Write each new or reworded heading as a question people ask or a plain statement of the subject, so it makes sense when quoted on its own."
        )
        body = (
            f"Rewrite the parts of {about} named in the refresh plan. Here is the current text: [paste the sections to change].\n"
            "Keep what the plan says to keep. Add and change only what it lists, with sourced claims, and mark anything that needs a fact check. "
            "Return each changed section whole, ready to paste, and list what you cut."
        )
        finish = "The changes are made, the page is republished with its updated date, and the links in and out still work."
        titles_done = "The title and meta description are kept or replaced, and entered in the page."
        headings_done = "The headings match the plan and the page reads in order."
        body_done = "Every section in the plan is changed, sourced and read by an editor."

    return [
        Sub("title", "Title and meta description", _wrap(project, title, brief, titles_done)),
        Sub("headings", "Headings (H1 to H3)", _wrap(project, headings, brief, headings_done)),
        Sub("body", "Write the page" if new else "Update the content", _wrap(project, body, brief, body_done)),
        Sub("publish", "Publish and link" if new else "Republish", "Publish the page, add the links the brief lists, and check the visible page matches its markup.\n\nDone when\n" + finish),
    ]
