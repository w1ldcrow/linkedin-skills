import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.jobscout import (
    PAGE_SIZE,
    Client,
    FetchError,
    classify,
    collect,
    load_profile,
    parse_age,
    parse_posting,
    parse_search,
    review_sheet,
    score,
    search_url,
)

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
TEMPLATE = Path(__file__).resolve().parent.parent / "context" / "jobs.template.json"


def card_html(job_id, title="Full Stack Developer", company="Acme", location="Brazil", listed="2026-10-28"):
    return f"""
    <li>
      <div class="base-card relative base-search-card job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
        <a class="base-card__full-link" href="https://br.linkedin.com/jobs/view/x-at-acme-{job_id}?position=1"></a>
        <div class="base-search-card__info">
          <h3 class="base-search-card__title">
            {title}
          </h3>
          <h4 class="base-search-card__subtitle">
            <a class="hidden-nested-link" href="https://www.linkedin.com/company/acme?trk=public">{company}</a>
          </h4>
          <div class="base-search-card__metadata">
            <span class="job-search-card__location">{location}</span>
            <time class="job-search-card__listdate" datetime="{listed}">1 day ago</time>
          </div>
        </div>
      </div>
    </li>
    """


POSTING = """
<section class="top-card-layout">
  <h2 class="top-card-layout__title topcard__title">Full Stack Developer</h2>
  <span class="posted-time-ago__text topcard__flavor--metadata">
    5 hours ago
  </span>
  <figcaption class="num-applicants__caption">Be among the first 25 applicants</figcaption>
  <icon data-svg-class-name="apply-button__offsite-apply-icon-svg"></icon>
</section>
<div class="description__text description__text--rich">
  <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5">
    <strong>About us</strong><br><br>We build payments.
    <ul><li>TypeScript and React</li><li>Node.js &amp; PostgreSQL</li></ul>
  </div>
</div>
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Seniority level</h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">Mid-Senior level</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Employment type</h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">Full-time</span>
  </li>
</ul>
"""


@pytest.fixture
def profile():
    return load_profile(str(TEMPLATE))


def make_job(job_id="1", title="Senior Full Stack Engineer", location="Brazil", hours=5.0,
             description="TypeScript, React, Next.js and Node.js on AWS.", workplace=("remote",)):
    posted = datetime.fromtimestamp(NOW.timestamp() - hours * 3600, timezone.utc)
    return {
        "id": job_id,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
        "title": title,
        "company": "Acme",
        "location": location,
        "listed": posted.date().isoformat(),
        "workplace_filter": list(workplace),
        "found_by": ["full stack @ Brazil"],
        "detail": {
            "posted_at": posted.isoformat().replace("+00:00", "Z"),
            "seniority": "Mid-Senior level",
            "description": description,
        },
    }


class TestParseSearch:
    def test_reads_every_card_field(self):
        [card] = parse_search(card_html("4483891327"))
        assert card == {
            "id": "4483891327",
            "url": "https://www.linkedin.com/jobs/view/4483891327/",
            "title": "Full Stack Developer",
            "company": "Acme",
            "company_url": "https://www.linkedin.com/company/acme",
            "location": "Brazil",
            "listed": "2026-10-28",
            "salary": "",
        }

    def test_falls_back_to_the_link_when_the_urn_is_missing(self):
        html = card_html("4483891327").replace('data-entity-urn="urn:li:jobPosting:4483891327"', "")
        assert parse_search(html)[0]["id"] == "4483891327"

    def test_empty_page_has_no_cards(self):
        assert parse_search("<!DOCTYPE html>") == []


class TestParsePosting:
    def test_reads_criteria_applicants_and_apply_kind(self):
        detail = parse_posting(POSTING, NOW)
        assert detail["seniority"] == "Mid-Senior level"
        assert detail["employment_type"] == "Full-time"
        assert detail["applicants"] == "Be among the first 25 applicants"
        assert detail["apply"] == "external"

    def test_turns_relative_age_into_an_absolute_time(self):
        assert parse_posting(POSTING, NOW)["posted_at"] == "2026-10-29T07:00:00Z"

    def test_keeps_list_items_on_their_own_lines(self):
        description = parse_posting(POSTING, NOW)["description"]
        assert description.splitlines() == [
            "About us",
            "We build payments.",
            "- TypeScript and React",
            "- Node.js & PostgreSQL",
        ]


class TestParseAge:
    @pytest.mark.parametrize(
        "text, hours",
        [
            ("2 hours ago", 2),
            ("1 day ago", 24),
            ("3 weeks ago", 504),
            ("Reposted 1 week ago", 168),
            ("há 2 dias", 48),
            ("30 minutes ago", 0.5),
            ("Just now", 0),
        ],
    )
    def test_reads_english_and_portuguese(self, text, hours):
        assert parse_age(text) == pytest.approx(hours)

    def test_unknown_text_is_none(self):
        assert parse_age("") is None


class TestSearchUrl:
    def test_sets_remote_recency_and_date_sort(self):
        url = search_url({"keywords": "full stack", "location": "Brazil", "workplace": ["remote"], "hours": 168}, 20)
        assert "keywords=full+stack" in url
        assert "f_WT=2" in url
        assert "f_TPR=r604800" in url
        assert "sortBy=DD" in url
        assert "start=20" in url


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


def fake_client(responses):
    queue = list(responses)
    slept = []

    def urlopen(request, timeout):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item.encode())

    client = Client(delay=0, retries=2, backoff=1, urlopen=urlopen, sleep=slept.append)
    return client, slept


class TestClient:
    def test_backs_off_on_429_then_succeeds(self):
        client, slept = fake_client([http_error(429), "ok"])
        assert client.get("https://x") == "ok"
        assert 1 in slept

    def test_gives_up_after_every_retry(self):
        client, _ = fake_client([http_error(999)] * 3)
        with pytest.raises(FetchError, match="HTTP 999"):
            client.get("https://x")

    def test_missing_page_is_none(self):
        client, _ = fake_client([http_error(404)])
        assert client.get("https://x") is None


class TestCollect:
    def test_dedupes_across_searches_and_stops_on_a_short_page(self):
        full = "".join(card_html(str(1000 + i)) for i in range(PAGE_SIZE))
        short = card_html("1000") + card_html("2000")
        client, _ = fake_client([full, short, short])
        searches = [
            {"keywords": "react", "location": "Brazil", "workplace": ["remote"], "max_pages": 3},
            {"keywords": "node", "location": "Brazil", "workplace": ["remote"], "max_pages": 3},
        ]
        jobs = {}
        collect(client, searches, jobs, log=lambda line: None)
        assert client.requests == 3
        assert len(jobs) == PAGE_SIZE + 1
        assert jobs["1000"]["found_by"] == ["react @ Brazil", "node @ Brazil"]
        assert jobs["1000"]["workplace_filter"] == ["remote"]


class TestClassify:
    def test_match_remote_and_recent_is_high(self, profile):
        job = classify(make_job(), profile, NOW)
        assert job["priority"] == "high"
        assert job["checks"] == {"match": True, "remote": True, "recent": True}
        assert job["matched_skills"] == ["TypeScript", "React", "Next.js", "Node.js", "AWS"]

    def test_old_posting_drops_to_medium(self, profile):
        job = classify(make_job(hours=24 * 6), profile, NOW)
        assert job["priority"] == "medium"
        assert job["checks"]["recent"] is False

    def test_no_stack_overlap_is_low(self, profile):
        job = classify(make_job(title="Developer", description="Excel and Power BI dashboards."), profile, NOW)
        assert job["priority"] == "low"

    def test_off_stack_title_sinks_the_match(self, profile):
        job = classify(make_job(title="Senior Java Developer"), profile, NOW)
        assert job["priority"] == "low"
        assert "java" in job["off_stack"]

    def test_avoided_title_is_discarded(self, profile):
        job = classify(make_job(title="Engineering Manager"), profile, NOW)
        assert job["priority"] == "discard"

    def test_remote_restricted_to_the_us_is_discarded(self, profile):
        job = classify(make_job(description="TypeScript, React. Must be located in the US."), profile, NOW)
        assert job["priority"] == "discard"
        assert job["scope"] == "restricted"

    def test_restriction_is_lifted_when_latam_is_open(self, profile):
        description = "TypeScript, React, Node.js. US only for W2; contractors in LATAM welcome."
        assert classify(make_job(description=description), profile, NOW)["scope"] == "home"

    def test_remote_in_another_country_is_not_remote_ok(self, profile):
        job = classify(make_job(location="Mexico City, Mexico"), profile, NOW)
        assert job["scope"] == "abroad"
        assert job["priority"] == "medium"

    def test_latam_location_is_remote_ok(self, profile):
        assert classify(make_job(location="Latin America"), profile, NOW)["checks"]["remote"] is True

    def test_metro_area_without_country_is_home(self, profile):
        assert classify(make_job(location="Greater São Paulo Area"), profile, NOW)["scope"] == "home"

    def test_state_name_abroad_is_not_home(self, profile):
        job = classify(make_job(location="Santa Catarina, Nuevo León, Mexico"), profile, NOW)
        assert job["scope"] == "abroad"

    def test_skill_named_in_the_title_weighs_double(self, profile):
        plain = classify(make_job(title="Desenvolvedor Sênior", description="Node.js"), profile, NOW)
        named = classify(make_job(title="Desenvolvedor Node Sênior", description="Node.js"), profile, NOW)
        assert named["scores"]["match"] > plain["scores"]["match"]

    def test_hybrid_in_the_title_beats_the_remote_filter(self, profile):
        job = classify(make_job(title="Full Stack Developer (Híbrido)", location="São Paulo, Brazil"), profile, NOW)
        assert job["workplace"] == "hybrid"
        assert job["priority"] == "discard"

    def test_onsite_description_beats_the_remote_tag(self, profile):
        job = classify(make_job(description="React, Next.js e TypeScript. 100% PRESENCIAL RECIFE/PE"), profile, NOW)
        assert job["workplace"] == "onsite"
        assert job["priority"] == "discard"

    def test_hybrid_description_beats_the_remote_tag(self, profile):
        description = "React e TypeScript. Híbrido de 3 dias presenciais na Faria Lima."
        assert classify(make_job(description=description), profile, NOW)["workplace"] == "hybrid"

    def test_description_that_also_says_remote_keeps_the_tag(self, profile):
        description = "React. Remote first, with an optional hybrid hub in São Paulo."
        assert classify(make_job(description=description), profile, NOW)["workplace"] == "remote"

    def test_hybrid_in_the_home_city_is_kept(self, profile):
        profile["candidate"]["cities"] = ["sorocaba"]
        job = classify(make_job(title="Full Stack (Híbrido)", location="Sorocaba, São Paulo, Brazil"), profile, NOW)
        assert job["priority"] == "medium"

    def test_junior_title_flags_seniority(self, profile):
        job = classify(make_job(title="Desenvolvedor Full Stack Júnior"), profile, NOW)
        assert job["scores"]["match"] < classify(make_job(), profile, NOW)["scores"]["match"]

    def test_required_language_not_spoken_is_flagged(self, profile):
        job = classify(make_job(description="TypeScript, React. Fluent in German is required."), profile, NOW)
        assert "pede fluência em german" in job["red_flags"]

    def test_review_overrides_match_and_scope(self, profile):
        review = {"match": 0.9, "scope": "abroad", "why": "stack igual, mas só contrata no México"}
        job = classify(make_job(), profile, NOW, review)
        assert job["scores"]["match"] == 0.9
        assert job["scores"]["match_source"] == "review"
        assert job["priority"] == "medium"
        assert job["review"] == review["why"]

    def test_review_can_discard(self, profile):
        job = classify(make_job(), profile, NOW, {"discard": "vaga de consultoria body shop"})
        assert job["priority"] == "discard"


class TestScore:
    def test_sorts_by_priority_and_marks_new(self, profile):
        raw = {
            "fetched_at": "2026-10-29T12:00:00Z",
            "jobs": [
                make_job("1", hours=24 * 6),
                make_job("2", title="Full Stack Engineer"),
                make_job("3", title="Recruiter"),
            ],
        }
        seen = {"1": "2026-10-20T12:00:00Z"}
        result = score(raw, profile, NOW, seen=seen)
        assert [job["id"] for job in result["jobs"]] == ["2", "1", "3"]
        assert result["counts"] == {"high": 1, "medium": 1, "low": 0, "discard": 1, "new": 2}
        assert [job["new"] for job in result["jobs"]] == [True, False, True]
        assert seen["2"] == "2026-10-29T12:00:00Z"

    def test_same_opening_in_several_cities_is_listed_once(self, profile):
        raw = {
            "fetched_at": "2026-10-29T12:00:00Z",
            "jobs": [make_job("1", location="Recife, Pernambuco, Brazil"), make_job("2", location="Brazil")],
        }
        [job] = score(raw, profile, NOW)["jobs"]
        assert job["also"] == [
            {"id": "2", "url": "https://www.linkedin.com/jobs/view/2/", "location": "Brazil"}
        ]

    def test_posting_reference_numbers_do_not_split_an_opening(self, profile):
        raw = {
            "fetched_at": "2026-10-29T12:00:00Z",
            "jobs": [
                make_job("1", title="Senior Frontend Engineer - Remote Work | REF#306573"),
                make_job("2", title="Senior Frontend Engineer - Remote Work | REF#306572"),
            ],
        }
        assert len(score(raw, profile, NOW)["jobs"]) == 1

    def test_a_review_covers_the_copies_of_the_same_opening(self, profile):
        raw = {
            "fetched_at": "2026-10-29T12:00:00Z",
            "jobs": [make_job("1", location="Recife, Pernambuco, Brazil"), make_job("2", location="Brazil")],
        }
        reviews = {"1": {"match": 0.3, "scope": "home", "why": "stack só no título"}}
        [job] = score(raw, profile, NOW, reviews)["jobs"]
        assert job["scores"]["match"] == 0.3
        assert job["review"] == "stack só no título"

    def test_rescoring_the_same_fetch_keeps_jobs_new(self, profile):
        raw = {"fetched_at": "2026-10-29T12:00:00Z", "jobs": [make_job("2")]}
        seen = {}
        score(raw, profile, NOW, seen=seen)
        assert score(raw, profile, NOW, seen=seen)["jobs"][0]["new"] is True

    def test_output_is_json_serializable(self, profile):
        raw = {"fetched_at": "2026-10-29T12:00:00Z", "jobs": [make_job()]}
        json.dumps(score(raw, profile, NOW))


class TestReviewSheet:
    def test_lists_candidates_with_description_and_skips_discards(self, profile):
        raw = {"fetched_at": "2026-10-29T12:00:00Z", "jobs": [make_job("1"), make_job("2", title="Recruiter")]}
        sheet = review_sheet(raw, profile, NOW, limit=10, chars=3000)
        assert sheet.startswith("1 candidatos")
        assert "## 1 · Senior Full Stack Engineer — Acme" in sheet
        assert "TypeScript, React, Next.js" in sheet
