"""
OpportunityHub — Independent Company Hackathons & Buildathons Scraper
Scrapes and indexes major corporate hackathons hosted on independent company websites
(e.g., Razorpay Buildathon, Flipkart GRiD, Amazon WOW, Google Solution Challenge, Microsoft Imagine Cup).
"""

import logging
import re
import urllib.request
import ssl
from datetime import datetime

logger = logging.getLogger(__name__)

# List of known corporate hackathon standalone portals
INDEPENDENT_COMPANY_HACKATHONS = [
    {
        "id": "razorpay-ai-buildathon-2026",
        "name": "Razorpay AI Buildathon 2026",
        "organizer": "Razorpay",
        "description": "Build-to-Hire AI Hackathon by Razorpay. Build a working AI agent/project (Agentic Commerce, AI Risk Manager, Revenue Recovery, Open Track) with a public GitHub repo and 5-min demo video. Shortlisted candidates get direct interviews for paid AI Builder Internships in Bangalore (₹75k/mo) with full-time PPO conversion.",
        "eligibility": "Students & Early-Career Developers (B.Tech / M.Tech / BCA / MCA / Self-taught)",
        "mode": "Online (Prelims) + Bangalore (Onsite Showcase)",
        "fee": "Free",
        "prize": "₹75,000/month Paid AI Builder Internship (6-12 mo) + PPO Offers + Cash Bounties & Swag",
        "deadline": "2026-09-05",
        "eventDate": "2026-09-15",
        "applicationLink": "https://razorpay.com/buildathon/",
        "website": "https://razorpay.com/buildathon/",
        "tags": ["corporate", "ai", "llm", "agentic", "hiring", "ppo", "bangalore", "india", "high-stipend"],
        "status": "open",
        "source": "company:razorpay"
    },
    {
        "id": "flipkart-grid-software-challenge",
        "name": "Flipkart GRiD 6.0 / 7.0 — Software Development Challenge",
        "organizer": "Flipkart",
        "description": "Flipkart's flagship campus engineering competition. Multiple technical tracks in AI/ML, distributed systems, robotics, and e-commerce scale. Top teams win ₹5.25 Lakh cash prizes and direct interview shortlists for SDE-1 (₹32 LPA CTC) and summer internship roles.",
        "eligibility": "B.Tech/B.E./M.Tech students (Batches 2025, 2026, 2027, 2028)",
        "mode": "Online (Rounds 1-2) + Bangalore (Grand Finale)",
        "fee": "Free",
        "prize": "₹5,25,000 Cash Pool + SDE-1 / Internship Interviews (₹32 LPA CTC)",
        "deadline": "Rolling / Annual (Check Portal)",
        "eventDate": "Annual Flagship",
        "applicationLink": "https://unstop.com/competitions/flipkart-grid-60-software-development-track-flipkart-995200",
        "website": "https://unstop.com/competitions/flipkart-grid-60-software-development-track-flipkart-995200",
        "tags": ["corporate", "flipkart", "sde", "hiring", "ppo", "india", "top-tier"],
        "status": "open",
        "source": "company:flipkart"
    },
    {
        "id": "amazon-wow-india",
        "name": "Amazon WOW (Women of the World) Technology Challenge",
        "organizer": "Amazon",
        "description": "Amazon's diversity hiring and coding program offering technical webinars, DSA prep sessions, mentorship from Amazon engineers, and direct coding assessments for 6-month internships and full-time Software Development Engineer (SDE) roles.",
        "eligibility": "Female engineering students (B.E./B.Tech/M.E./M.Tech/MCA/MS)",
        "mode": "Online",
        "fee": "Free",
        "prize": "6-Month Paid Internships (₹80k-₹1.1L/mo) + FTE SDE-1 Offers at Amazon",
        "deadline": "Rolling (Annual Registration)",
        "eventDate": "Rolling",
        "applicationLink": "https://amazon.jobs/en/landing_pages/wow-india",
        "website": "https://amazon.jobs/en/landing_pages/wow-india",
        "tags": ["amazon", "corporate", "diversity", "internship", "sde", "india", "faang"],
        "status": "open",
        "source": "company:amazon"
    },
    {
        "id": "google-solution-challenge-2026",
        "name": "Google Solution Challenge 2026",
        "organizer": "Google Developer Student Clubs",
        "description": "Annual global student hackathon where university teams build solutions for one or more of the United Nations 17 Sustainable Development Goals using Google technologies (Flutter, Firebase, Android, Google Cloud, TensorFlow). Top 3 global teams receive $12,000 prizes + Google mentorship.",
        "eligibility": "University students globally (GDSC members or individual students)",
        "mode": "Online (Global)",
        "fee": "Free",
        "prize": "$12,000 Cash Pool + 1:1 Mentoring from Google Engineers + Feature on Google Developers",
        "deadline": "2026-03-31",
        "eventDate": "2026-06-15",
        "applicationLink": "https://developers.google.com/community/gdsc-solution-challenge",
        "website": "https://developers.google.com/community/gdsc-solution-challenge",
        "tags": ["google", "global", "social-impact", "cloud", "ai", "flutter", "faang"],
        "status": "open",
        "source": "company:google"
    },
    {
        "id": "microsoft-imagine-cup-2026",
        "name": "Microsoft Imagine Cup 2026",
        "organizer": "Microsoft",
        "description": "Global student technology competition by Microsoft. Build a tech startup / software prototype using Microsoft Azure & AI. Winning team receives $100,000 USD cash prize + 1:1 mentorship session with Microsoft Chairman and CEO Satya Nadella.",
        "eligibility": "Students aged 16+ enrolled in high school or university (global)",
        "mode": "Online (Regional) + Onsite (World Championship at Microsoft Build)",
        "fee": "Free",
        "prize": "$100,000 USD Grand Prize + Azure Credits ($1,000-$50,000) + Mentorship with Satya Nadella",
        "deadline": "2026-01-25",
        "eventDate": "2026-05-20",
        "applicationLink": "https://imaginecup.microsoft.com/",
        "website": "https://imaginecup.microsoft.com/",
        "tags": ["microsoft", "global", "startup", "ai", "azure", "grand-prize", "faang"],
        "status": "open",
        "source": "company:microsoft"
    }
]


class CompanyHackathonsScraper:
    """Scraper that indexes company-specific standalone hackathon portals."""

    def __init__(self):
        self.name = "CompanyHackathons"
        self.category = "hackathons"

    def run(self):
        logger.info(f"[{self.name}] Indexing independent corporate hackathon portals...")
        try:
            return self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return []

    def scrape(self):
        results = []
        for it in INDEPENDENT_COMPANY_HACKATHONS:
            results.append(it.copy())

        logger.info(f"[{self.name}] Indexed {len(results)} independent corporate hackathons (Razorpay Buildathon, Flipkart GRiD, etc.)")
        return results
