from types import SimpleNamespace as Row

from app.services.page_signals import rank_offers


def offer(url, *, primary=False, stage='bofu', label='Contact'):
    return Row(normalized_url=url, is_primary=primary, stage=stage, label=label)


def page(url, heading='', status=200):
    return Row(normalized_url=url, title=heading, sections=[{'level': 1, 'heading': heading}], status_code=status)


def test_aquaman_broad_homepage_uses_primary_contact_not_regional_campaign():
    home='https://aquamanleakdetection.com/'
    contact=offer(home+'contact/', primary=True)
    regional=offer('https://offers.aquamanleakdetection.com/pool-leak-emergency', label='Pool leak help in Brevard County')
    crawl={home:page(home,'Florida pool leak detection'), regional.normalized_url:page(regional.normalized_url,'Pool leak help in Brevard County')}
    assert rank_offers(home,'mofu',[regional,contact],crawl)==(contact.normalized_url,)
    assert rank_offers(home,'tofu',[contact],crawl)==()


def test_location_and_industry_mismatch_cannot_be_overridden_by_primary_flag():
    home='https://example.com/'
    regional=offer('https://example.com/locations/tampa',primary=True)
    industry=offer('https://example.com/industries/healthcare/contact',primary=True)
    crawl={home:page(home,'Managed IT services')}
    assert rank_offers(home,'mofu',[regional,industry],crawl)==()


def test_matching_local_page_can_use_local_offer():
    source='https://example.com/locations/tampa/service'
    local=offer('https://example.com/locations/tampa/contact')
    generic=offer('https://example.com/contact',primary=True)
    crawl={source:page(source,'Services in Tampa'),local.normalized_url:page(local.normalized_url,'Contact Tampa')}
    assert rank_offers(source,'mofu',[generic,local],crawl)==(local.normalized_url,)


def test_ambiguous_nonprimary_destinations_do_not_pick_alphabetically():
    source='https://example.com/service'
    offers=[offer('https://example.com/a'),offer('https://example.com/z')]
    crawl={o.normalized_url:page(o.normalized_url) for o in offers}
    assert rank_offers(source,'mofu',offers,crawl)==()
    assert rank_offers(source,'mofu',list(reversed(offers)),crawl)==()


def test_unknown_intent_self_links_and_unverified_nonprimary_offers_are_excluded():
    source='https://example.com/service'
    assert rank_offers(source,'mofu',[offer(source,primary=True),offer('https://example.com/quote'),offer('https://example.com/contact',primary=True,stage=None)],{})==()


def test_a_known_failed_destination_is_not_recommended_even_if_primary():
    source='https://example.com/service'
    contact=offer('https://example.com/contact',primary=True)
    assert rank_offers(source,'mofu',[contact],{contact.normalized_url:page(contact.normalized_url,status=404)})==()
