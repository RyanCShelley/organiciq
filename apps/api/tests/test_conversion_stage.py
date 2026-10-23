from types import SimpleNamespace as Row
from datetime import datetime, timezone

from app.services.conversion_stage import resolve
from app.models.config import ClientConversionPage, ClientPageStage
from tests.conftest import client_header


def test_confirmed_stage_is_reused_across_url_variants():
    page=Row(normalized_url='https://www.example.com/contact-us/',stage=None)
    assert resolve(page,{'http://example.com/contact-us':'bofu'})==('bofu','confirmed_page')
    assert page.stage is None


def test_explicit_conversion_override_wins_and_ambiguity_stays_unknown():
    page=Row(normalized_url='https://example.com/contact-us',stage='mofu')
    confirmed={'https://example.com/contact-us':'bofu'}
    assert resolve(page,confirmed)==('mofu','explicit')
    page.stage=None
    assert resolve(page,{'https://example.com/other':'bofu'})==(None,'unknown')
    assert resolve(page,{**confirmed,'http://example.com/contact-us':'tofu'})==(None,'unknown')


def test_settings_and_engine_use_same_confirmed_destination_without_writing_override(db,client,client_a,client_b,admin_user):
    from app.services.page_stage import confirmed_stages
    from app.services.page_signals import rank_offers
    url='https://example.com/contact-us'
    offer=ClientConversionPage(client_id=client_a.id,normalized_url=url+'/',label='Contact',stage=None,is_primary=True)
    db.add(offer)
    stage=ClientPageStage(client_id=client_a.id,normalized_url=url,stage='bofu',confirmed_at=None)
    db.add(stage);db.commit()
    headers=client_header(client_a.id,admin_user.email)
    path='/admin/conversion-pages'
    first=client.get(path,headers=headers).json()[0]
    assert first['effective_stage'] is None
    # A different client's confirmation cannot qualify this client's offer.
    db.add(ClientPageStage(client_id=client_b.id,normalized_url=url,stage='bofu',confirmed_at=datetime.now(timezone.utc)))
    db.commit()
    assert client.get(path,headers=headers).json()[0]['effective_stage'] is None
    stage.confirmed_at=datetime.now(timezone.utc);db.commit()
    result=client.get(path,headers=headers).json()[0]
    assert result['stage'] is None and result['effective_stage']=='bofu'
    assert result['stage_source']=='confirmed_page'
    assert rank_offers('https://example.com/','mofu',[offer],{},confirmed_stages(db,client_a.id))==(url+'/',)
    db.refresh(offer)
    assert offer.stage is None


def test_loader_reuses_confirmation_for_both_destination_and_existing_route(db,client_a):
    from datetime import date
    from app.models.config import OrganicChannel
    from app.models.ga4 import FactGa4Traffic
    from app.models.crawl import FactCrawlPageSnapshot, FactCrawlInternalLink, CRAWL_SOURCE_FIRST_PARTY
    from app.services.page_signals import load_page_candidates
    from app.decisions.catalog import l1_route_to_the_next_step
    today=date(2026,9,30);source='https://example.com/service';target='https://example.com/contact-us'
    for url,stage in [(source,'mofu'),(target,'bofu')]:
        db.add(ClientPageStage(client_id=client_a.id,normalized_url=url,stage=stage,confirmed_at=datetime.now(timezone.utc)))
    db.add(ClientConversionPage(client_id=client_a.id,normalized_url=target,label='Contact',stage=None,is_primary=True))
    db.add(FactGa4Traffic(client_id=client_a.id,date=today,raw_url=source,normalized_url=source,channel=OrganicChannel.ORGANIC_SEARCH,sessions=200))
    db.add(FactCrawlPageSnapshot(client_id=client_a.id,source=CRAWL_SOURCE_FIRST_PARTY,snapshot_date=today,raw_url=source,normalized_url=source,status_code=200,sections=[]))
    db.commit()
    page=next(p for p in load_page_candidates(db,client_a,today=today) if p.url==source)
    assert page.matched_offers==(target,)
    assert target in l1_route_to_the_next_step(page).done_when
    db.add(FactCrawlInternalLink(client_id=client_a.id,source=CRAWL_SOURCE_FIRST_PARTY,snapshot_date=today,from_url=source,to_url=target,in_content=True,is_template=False))
    db.commit()
    page=next(p for p in load_page_candidates(db,client_a,today=today) if p.url==source)
    assert page.linked_offer_stages==frozenset({'bofu'})
    assert l1_route_to_the_next_step(page) is None
