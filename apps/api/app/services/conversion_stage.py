"""One effective destination stage for settings and recommendation inputs."""
from app.decisions.planning import page_identity

STAGES = {'tofu', 'mofu', 'bofu'}


def resolve(offer, confirmed: dict[str, str]) -> tuple[str | None, str]:
    explicit = (offer.stage or '').strip().lower()
    if explicit in STAGES:
        return explicit, 'explicit'
    identity = page_identity(offer.normalized_url)
    matches = {stage for url, stage in confirmed.items()
               if stage in STAGES and page_identity(url) == identity}
    if len(matches) == 1:
        return next(iter(matches)), 'confirmed_page'
    return None, 'unknown'
