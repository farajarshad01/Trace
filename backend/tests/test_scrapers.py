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
