import json

from app.scrapers.platforms import greenhouse, lever, workday
from app.scrapers.generic import GenericScraper, _JOB_KEYWORDS


class Resp:
    def __init__(self, payload=None, text=""):
        self._p, self.text = payload, text
    def raise_for_status(self): pass
    def json(self): return self._p


def test_greenhouse_board_token_variants():
    t = greenhouse.board_token
    assert t("https://boards.greenhouse.io/acme") == "acme"
    assert t("https://boards.greenhouse.io/acme/") == "acme"
    assert t("https://job-boards.greenhouse.io/acme/jobs/12345") == "acme"
    assert t("https://boards.greenhouse.io/embed/job_board?for=acme") == "acme"


def test_greenhouse_cleans_html_and_skips_rows_that_would_violate_not_null(monkeypatch):
    payload = {"jobs": [
        {"title": "Dev", "absolute_url": "https://x/1#frag", "id": 1,
         "location": {"name": "Remote"}, "content": "&lt;p&gt;Python&lt;/p&gt;"},
        {"title": "No URL", "absolute_url": None, "id": 2},
        {"title": "", "absolute_url": "https://x/3", "id": 3},
    ]}
    monkeypatch.setattr(greenhouse.requests, "get", lambda *a, **k: Resp(payload))
    jobs = greenhouse.GreenhouseScraper().scrape("https://boards.greenhouse.io/acme")
    assert len(jobs) == 1
    assert jobs[0]["description"] == "Python" and jobs[0]["original_url"] == "https://x/1"


def test_lever_includes_requirement_lists_not_just_the_intro(monkeypatch):
    payload = [{
        "text": "Engineer", "hostedUrl": "https://jobs.lever.co/acme/abc", "id": "abc",
        "categories": {"location": "NYC", "commitment": "Full-time"},
        "descriptionPlain": "About the role.",
        "lists": [{"text": "Requirements", "content": "<li>Python</li><li>Docker</li>"}],
        "additionalPlain": "Benefits apply.",
    }]
    seen = {}
    def fake_get(url, **k):
        seen["url"] = url
        return Resp(payload)
    monkeypatch.setattr(lever.requests, "get", fake_get)

    jobs = lever.LeverScraper().scrape("https://jobs.lever.co/acme/")
    d = jobs[0]["description"]
    assert "About the role." in d and "Requirements" in d and "• Python" in d and "Benefits apply." in d
    assert seen["url"] == "https://api.lever.co/v0/postings/acme"


def test_lever_company_is_first_path_segment_and_eu_host():
    assert lever.lever_target("https://jobs.lever.co/acme/some-uuid") == ("api.lever.co", "acme")
    assert lever.lever_target("https://jobs.eu.lever.co/acme") == ("api.eu.lever.co", "acme")


def test_workday_target_parsing():
    f = workday.workday_target
    assert f("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite") == (
        "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite")
    assert f("https://acme.wd1.myworkdayjobs.com/Careers/")[2] == "Careers"


def test_workday_uses_the_json_api_and_real_titles(monkeypatch):
    pages = [
        {"jobPostings": [{"title": "Data Engineer", "externalPath": "/job/US/Data-Engineer_R1", "locationsText": "US"}]},
        {"jobPostings": []},
    ]
    posted = []
    def fake_post(url, json=None, **k):
        posted.append((url, json["offset"]))
        return Resp(pages.pop(0))
    monkeypatch.setattr(workday.requests, "post", fake_post)

    jobs = workday.WorkdayScraper().scrape("https://acme.wd5.myworkdayjobs.com/en-US/Careers")
    assert jobs[0]["title"] == "Data Engineer"            # not the "Workday Job" placeholder
    assert jobs[0]["original_url"] == "https://acme.wd5.myworkdayjobs.com/Careers/job/US/Data-Engineer_R1"
    assert posted[0][0] == "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"


def test_generic_keywords_use_word_boundaries():
    # "ai" used to match as a substring of these.
    for title in ["Maintenance Technician", "Retail Assistant", "Chair of Facilities", "Email Marketing"]:
        assert not _JOB_KEYWORDS.search(title), title
    for title in ["AI Engineer", "Senior Python Developer", "Full-Stack Engineer", "Software Intern"]:
        assert _JOB_KEYWORDS.search(title), title


def test_generic_scraper_extracts_unique_relevant_links(monkeypatch):
    html = """<a href="/jobs/1">Backend Engineer</a><a href="/jobs/1#x">Backend Engineer</a>
              <a href="mailto:a@b.c">Software Engineer</a><a href="/about">About us</a>
              <a href="/jobs/2">Maintenance Tech</a>"""
    from app.scrapers import generic
    monkeypatch.setattr(generic.requests, "get", lambda *a, **k: Resp(text=html))
    jobs = GenericScraper().scrape("https://acme.com/careers")
    assert [j["original_url"] for j in jobs] == ["https://acme.com/jobs/1"]


# ── generic scraper: the 10Pearls / Wamo Labs regression ────────────────

from app.scrapers import generic as generic_mod


def _page(monkeypatch, html):
    monkeypatch.setattr(generic_mod.requests, "get", lambda *a, **k: Resp(text=html))


SERVICES_SITE = """
<html><body class="nav-open">
<header><nav>
  <a href="/services/ai-integration">AI &amp; Machine Learning</a>
  <a href="/services/custom-web">Full-Stack Web Development</a>
  <a href="/industries/healthcare">Healthcare &amp; Pharma Clinical AI</a>
  <a href="/podcast">Podcast Operators on AI in production</a>
</nav></header>
<main>
  <h1>We're hiring</h1><p>No role that fits yet? Send us the strongest thing you shipped.</p>
  <a href="/careers">Early careers Graduate engineering program</a>
  <a href="/contact">Start an AI project</a>
</main>
<footer><a href="/services/ai-integration">AI Software Development</a></footer>
<div id="cookie-banner"><a href="/privacy">Machine learning cookies</a></div>
</body></html>
"""


def test_menus_footers_and_cookie_banners_are_not_jobs(monkeypatch):
    _page(monkeypatch, SERVICES_SITE)
    assert GenericScraper().scrape("https://www.wamolabs.com/careers") == []


def test_real_postings_are_found_and_decoys_are_ignored(monkeypatch):
    html = """<body>
      <nav><a href="/services/ai">AI Software Development</a></nav>
      <main>
        <a href="/careers/senior-backend-engineer">Senior Backend Engineer</a>
        <a href="/jobs/123-data-scientist">Data Scientist</a>
        <a href="/jobs/55">Maintenance Technician</a>
        <a href="/careers">Careers home - software engineering</a>
        <a href="https://apply.workable.com/acme/j/ABC123/">Python Developer</a>
        <a href="/blog/how-we-build-ai">How we build AI software</a>
      </main></body>"""
    _page(monkeypatch, html)
    urls = sorted(j["original_url"] for j in GenericScraper().scrape("https://acme.com/careers"))
    assert urls == [
        "https://acme.com/careers/senior-backend-engineer",
        "https://acme.com/jobs/123-data-scientist",
        "https://apply.workable.com/acme/j/ABC123/",
    ]


def test_a_wrapper_class_like_nav_open_does_not_wipe_the_page(monkeypatch):
    html = '<body class="nav-open"><div class="site menu-open"><main><a href="/jobs/9">Backend Engineer</a></main></div></body>'
    _page(monkeypatch, html)
    assert len(GenericScraper().scrape("https://acme.com/careers")) == 1


def test_json_ld_jobposting_is_used_when_present(monkeypatch):
    ld = '''{"@context":"https://schema.org","@graph":[{"@type":"JobPosting","title":"ML Engineer",
      "url":"https://acme.com/jobs/ml-engineer","employmentType":"FULL_TIME",
      "description":"&lt;p&gt;Build models. 5+ years of experience required.&lt;/p&gt;",
      "jobLocation":{"address":{"addressLocality":"Karachi","addressCountry":"PK"}}}]}'''
    _page(monkeypatch, f'<html><head><script type="application/ld+json">{ld}</script></head><body><nav><a href="/x">AI Services</a></nav></body></html>')
    jobs = GenericScraper().scrape("https://acme.com/careers")
    assert len(jobs) == 1
    assert jobs[0]["title"] == "ML Engineer" and jobs[0]["location"] == "Karachi, PK"
    assert jobs[0]["description"].startswith("Build models.")


def test_embedded_greenhouse_board_is_delegated_to_the_greenhouse_scraper(monkeypatch):
    seen = {}
    def fake_scrape(self, url):
        seen["url"] = url
        return [{"title": "Dev", "original_url": "https://boards.greenhouse.io/acme/jobs/1", "platform": "greenhouse"}]
    monkeypatch.setattr(greenhouse.GreenhouseScraper, "scrape", fake_scrape)
    _page(monkeypatch, '<html><body><iframe src="https://boards.greenhouse.io/embed/job_board?for=acme"></iframe></body></html>')
    jobs = GenericScraper().scrape("https://acme.com/careers")
    assert jobs[0]["platform"] == "greenhouse" and "for=acme" in seen["url"]


def test_failed_ats_delegation_falls_back_to_links(monkeypatch):
    def boom(self, url): raise RuntimeError("404")
    monkeypatch.setattr(lever.LeverScraper, "scrape", boom)
    _page(monkeypatch, '<main><a href="https://jobs.lever.co/acme">Our jobs</a><a href="/jobs/7">Backend Engineer</a></main>')
    assert [j["title"] for j in GenericScraper().scrape("https://acme.com/careers")] == ["Backend Engineer"]


def test_fetch_description_rejects_marketing_pages_and_strips_cookie_text(monkeypatch):
    marketing = "<main>" + "<p>We deliver scalable AI solutions for enterprises worldwide.</p>" * 12 + "</main>"
    _page(monkeypatch, marketing)
    assert GenericScraper().fetch_description({"original_url": "https://acme.com/jobs/1"}) is None

    posting = ('<main><h1>Backend Engineer</h1><p>About the role: you will build APIs.</p>'
               + '<p>Responsibilities include designing services and reviewing code every day.</p>' * 4
               + '<div class="cookie-banner">Enable or Disable Cookies Save Changes</div></main>')
    _page(monkeypatch, posting)
    text = GenericScraper().fetch_description({"original_url": "https://acme.com/jobs/1"})
    assert "build APIs" in text and "Cookies" not in text
