"""Structured-data types that describe a site rather than a page.
"""

from __future__ import annotations




#: Types an SEO plugin emits on every page regardless of content. Their presence
#: says a plugin is installed, not that the page is described. `Person` is here
#: too: author markup describes the author, not the page.
BOILERPLATE_SCHEMA_TYPES: frozenset[str] = frozenset(
    {
        "WebPage",
        "WebSite",
        "Organization",
        "Corporation",
        "BreadcrumbList",
        "ListItem",
        "ImageObject",
        "SiteNavigationElement",
        "WPHeader",
        "WPFooter",
        "WPSideBar",
        "CollectionPage",
        "SearchAction",
        "ReadAction",
        "Person",
    }
)
