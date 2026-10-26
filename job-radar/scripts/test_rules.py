import unittest

import collect
import rules


class ExpandedSearchTest(unittest.TestCase):
    def test_plain_pd_hiring_uses_existing_industry_filter(self):
        self.assertTrue(rules.title_could_match("콘텐츠 PD"))
        self.assertEqual(collect.judge("saramin", {"title": "콘텐츠 PD", "company": "방송사"}), (True, None))
        self.assertEqual(collect.judge("saramin", {"title": "콘텐츠 PD", "company": "광고대행사"})[0], False)

    def test_freelance_other_roles_are_included(self):
        card = {"title": "프리랜서 번역가", "company": "출판사", "employment": "프리랜서"}
        self.assertTrue(rules.title_could_match(card["title"], "saramin", card["employment"]))
        self.assertEqual(collect.judge("saramin", card), (True, None))
        self.assertEqual(rules.job_kind("saramin", card["title"], card["employment"]), "gig")
        self.assertEqual(collect.judge("saramin", {**card, "company": "광고회사"})[0], False)

    def test_gig_search_opens_candidate_but_does_not_accept_full_time_job(self):
        self.assertTrue(rules.title_could_match("번역가", "saramin", gig_search=True))
        self.assertEqual(collect.judge("saramin", {"title": "번역가", "employment": "정규직"})[0], False)
        self.assertEqual(collect.judge("saramin", {"title": "번역가", "body": "근무형태: 프리랜서"}), (True, None))

    def test_gig_search_marks_cards_for_detail_lookup(self):
        class Fetcher:
            errors = []

        cards = collect._run_terms(Fetcher(), ["프리랜서"], lambda _: [{"url": "example", "title": "번역가"}])
        self.assertTrue(cards[0]["_gig_search"])

    def test_outsourcing_manager_is_not_a_freelance_job(self):
        self.assertEqual(rules.job_kind("saramin", "외주관리 생산관리 사원", "정규직"), "job")
        self.assertEqual(collect.judge("saramin", {"title": "외주관리 생산관리 사원", "employment": "정규직"})[0], False)
        self.assertEqual(rules.job_kind("saramin", "영상 편집 외주 모집", ""), "gig")


if __name__ == "__main__":
    unittest.main()
