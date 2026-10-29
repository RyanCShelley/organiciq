from datetime import date, timedelta
from types import SimpleNamespace as NS
from app.services.page_ownership import PageIndex, choose

DAY = date(2026, 10, 19)


def page(path, heading):
    return NS(normalized_url='https://example.com'+path, snapshot_date=DAY, title=heading,
        sections=[{'level':1,'heading':heading}], canonical_url=None, redirect_url=None,
        indexable=True, soft_404=False, blocked_by_robots=False, status_code=200, inbound_editorial_links=0)


def index(*pages):
    return PageIndex(pages, 'example.com', today=DAY)


def rank(path, days=(0,4,8), market='us'):
    return [{'url':'https://example.com'+path,'position':4,'date':DAY-timedelta(days=d),'site_engine_id':market} for d in days]


def test_broad_pool_service_owns_home_despite_location_subject_match():
    home=page('/', 'Swimming Pool Leak Detection & Repair')
    local=page('/tampa-bay-leak-detection', 'Leak Detection in Hillsborough, Pasco & Pinellas County')
    local.sections.append({'level':2,'heading':'Pool Leak Detection and Repair Throughout the Tampa Bay Area'})
    subject=NS(page_url=local.normalized_url,computed_on=DAY,margin=.4)
    for term in ('pool leak detection company','swimming pool leak detection services'):
        result=choose(term,index(home,local),subject=subject,rankings=rank('/'),today=DAY)
        assert result.url==home.normalized_url


def test_location_query_uses_local_service_page_not_home():
    home=page('/','Swimming Pool Leak Detection & Repair')
    local=page('/locations/orlando','Pool Leak Detection in Orlando')
    assert choose('pool leak detection Orlando',index(home,local),rankings=rank('/locations/orlando'),today=DAY).url==local.normalized_url


def test_acctek_service_intent_does_not_follow_ranking_article():
    service=page('/managed-it','Managed IT Services')
    article=page('/what-are-managed-it-services','What Are Managed IT Services?')
    result=choose('managed it services',index(service,article),rankings=rank('/what-are-managed-it-services'),today=DAY)
    assert result.url==service.normalized_url
    assert not next(c for c in result.candidates if c['url']==article.normalized_url)['eligible']
    assert choose('what are managed it services',index(service,article),rankings=rank('/what-are-managed-it-services'),today=DAY).url==article.normalized_url


def test_sma_service_owner_is_not_a_location_or_listicle():
    service=page('/capabilities/seo','SEO agency for Google and AI search')
    local=page('/locations/tampa-florida','Tampa SEO agency')
    article=page('/blog/best-seo-agencies','Best SEO Agencies')
    subject=NS(page_url=service.normalized_url,computed_on=DAY,margin=.3)
    assert choose('seo agency',index(service,local,article),subject=subject,today=DAY).url==service.normalized_url


def test_competing_markets_or_single_observation_cannot_resolve_tie():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    for ranks in [rank('/a',market='us')+rank('/b',market='uk'),rank('/a',days=(0,))]:
        result=choose('managed cloud services',index(a,b),rankings=ranks,today=DAY)
        assert result.url is None and result.status=='conflict'
    assert choose('managed cloud services',index(a,b),rankings=rank('/a'),today=DAY).url==a.normalized_url


def test_multiday_gsc_can_resolve_tie_but_single_day_cannot():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    evidence={'url':a.normalized_url,'days':1,'impressions':10000,'last_date':DAY}
    assert choose('managed cloud services',index(a,b),gsc=[evidence],today=DAY).url is None
    evidence['days']=5
    assert choose('managed cloud services',index(a,b),gsc=[evidence],today=DAY).url==a.normalized_url


def test_stale_or_future_search_readings_do_not_break_ties():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    for days in [(40,44,48),(-1,-4,-8)]:
        assert choose('managed cloud services',index(a,b),rankings=rank('/a',days),today=DAY).url is None


def test_canonical_evidence_is_one_page_not_two_competitors():
    owner,alias=page('/service','Managed cloud services'),page('/old','Managed cloud services')
    alias.canonical_url=owner.normalized_url
    result=choose('managed cloud services',index(owner,alias),rankings=rank('/old'),today=DAY)
    assert result.url==owner.normalized_url and len(result.candidates)==1


def test_scope_blocked_stale_and_cross_client_canonicals_are_rejected():
    good,bad=page('/scope/service','Managed cloud services'),page('/other','Managed cloud services')
    assert PageIndex([good,bad],'example.com','/scope',DAY).resolve(bad.normalized_url) is None
    for field,value in [('soft_404',True),('blocked_by_robots',True),('indexable',False),('status_code',403),('snapshot_date',DAY-timedelta(days=46))]:
        broken=page('/service','Managed cloud services');setattr(broken,field,value)
        assert not index(broken).eligible
    bad.canonical_url='https://different-client.com/'
    assert index(bad).resolve(bad.normalized_url) is None


def test_body_mentions_are_not_primary_subject_evidence():
    p=page('/cloud','Managed cloud services')
    p.sections.append({'level':2,'heading':'Industrial pump repair'})
    assert choose('industrial pump repair',index(p),rankings=rank('/cloud'),today=DAY).url is None


def test_sma_primary_service_beats_glossary_and_industry_without_search_history():
    main=page('/capabilities/seo','SEO agency for Google and AI search')
    main.title='SEO Agency That Understands AI Search | SMA Marketing'
    glossary=page('/glossary/what-is-an-seo-agency','What is an SEO agency?')
    industry=page('/industries/saas','SEO agency for SaaS')
    local=page('/capabilities/local-seo','Local SEO agency')
    for term in ('seo agency','seo services'):
        assert choose(term,index(main,glossary,industry,local),today=DAY).url==main.normalized_url


def test_most_impressions_do_not_override_recent_persistent_competing_owner():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    ranks=rank('/b',days=(0,2,4))
    gsc=[{'url':a.normalized_url,'days':40,'impressions':10000,'last_date':DAY}]
    assert choose('managed cloud services',index(a,b),gsc=gsc,rankings=ranks,today=DAY).url is None


def test_future_or_tiny_gsc_cannot_break_tie():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    for last,impressions in [(DAY+timedelta(days=1),10000),(DAY,2)]:
        assert choose('managed cloud services',index(a,b),gsc=[{'url':a.normalized_url,'days':5,'impressions':impressions,'last_date':last}],today=DAY).url is None


def test_alias_cycles_do_not_create_owners():
    a,b=page('/a','Managed cloud services'),page('/b','Managed cloud services')
    a.canonical_url=b.normalized_url;b.canonical_url=a.normalized_url
    assert not index(a,b).eligible


def test_complete_title_topic_is_not_hidden_by_narrower_h1():
    p=page('/b2b-content-marketing','Content Marketing')
    p.title='B2B Content Marketing Services for Growing Businesses'
    assert choose('b2b content marketing services',index(p),today=DAY).url==p.normalized_url
