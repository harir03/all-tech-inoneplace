# Contributing to OpportunityHub

Thank you for helping keep this resource up-to-date! Here's how you can contribute.

---

## 🚀 Quick Ways to Contribute

### 1. Add a New Opportunity (Easiest)

**Option A: Use the Issue Form (recommended for non-technical contributors)**
1. Go to [**New Issue → Add Opportunity**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=add-opportunity.yml)
2. Fill in the fields (Name, Category, Organizer, Deadline, Mode, Fee, Application Link, etc.)
3. Submit! A maintainer will review and merge it.

### Option 2: Edit JSON directly (PR)

1. Fork the repository
2. Edit the relevant JSON file in the `data/` directory:
   - `data/hackathons.json`
   - `data/internships.json`
   - `data/competitions.json`
   - `data/open-source-programs.json`
   - `data/fellowships.json`
3. Follow the schema (see below)
4. Open a Pull Request!

---

## 🐛 Reporting Dead Links or Outdated Info

Use the [**Report Issue**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=report-issue.yml) template to flag:
- Broken application links
- Wrong deadlines or eligibility info
- Opportunities that should be marked as closed

### 3. Improve the Website or Documentation
- Fix bugs, improve design, add features to the website in `website/`
- Improve documentation, fix typos, etc.

---

## 📐 JSON Schemas

### Hackathons (`data/hackathons.json`)
```json
{
  "name": "Hackathon Name",
  "organizer": "Organization Name",
  "description": "Brief description of the hackathon",
  "eligibility": "Who can participate",
  "mode": "Online / Offline / Hybrid",
  "fee": "Free / ₹500 / etc.",
  "prize": "Prize details",
  "deadline": "YYYY-MM-DD",
  "eventDate": "YYYY-MM-DD or description",
  "applicationLink": "https://...",
  "website": "https://...",
  "tags": ["tag1", "tag2"],
  "status": "open / closed / coming-soon"
}
```

### Internships (`data/internships.json`)
```json
{
  "name": "Internship Name",
  "organizer": "Company / Organization",
  "description": "Brief description",
  "eligibility": "Who can apply",
  "stipend": "Amount or 'Unpaid'",
  "duration": "Duration (e.g., '10-12 weeks')",
  "location": "City / Remote",
  "mode": "Onsite / Remote / Hybrid",
  "deadline": "YYYY-MM-DD or 'Rolling'",
  "internshipDates": "When it takes place",
  "applicationLink": "https://...",
  "website": "https://...",
  "tags": ["tag1", "tag2"],
  "status": "open / closed / coming-soon"
}
```

### Competitions (`data/competitions.json`)
```json
{
  "name": "Competition Name",
  "organizer": "Organization",
  "description": "Brief description",
  "eligibility": "Who can participate",
  "mode": "Online / Offline",
  "fee": "Free / Amount",
  "prize": "Prize details",
  "deadline": "YYYY-MM-DD or 'Rolling'",
  "eventDate": "Date or description",
  "applicationLink": "https://...",
  "website": "https://...",
  "tags": ["tag1", "tag2"],
  "status": "open / closed / coming-soon"
}
```

### Open Source Programs (`data/open-source-programs.json`)
```json
{
  "name": "Program Name",
  "organizer": "Organization",
  "description": "Brief description",
  "eligibility": "Who can apply",
  "stipend": "Amount or 'Certificate only'",
  "duration": "Duration",
  "mentorship": true,
  "deadline": "YYYY-MM-DD or 'Rolling'",
  "programDates": "When it runs",
  "applicationLink": "https://...",
  "website": "https://...",
  "tags": ["tag1", "tag2"],
  "status": "open / closed / coming-soon"
}
```

### Fellowships (`data/fellowships.json`)
```json
{
  "name": "Fellowship Name",
  "organizer": "Organization",
  "description": "Brief description",
  "eligibility": "Who can apply",
  "stipend": "Amount",
  "duration": "Duration",
  "mentorship": true,
  "deadline": "YYYY-MM-DD or 'Rolling'",
  "programDates": "When it runs",
  "applicationLink": "https://...",
  "website": "https://...",
  "tags": ["tag1", "tag2"],
  "status": "open / closed / coming-soon"
}
```

---

## ✅ Pull Request Checklist

Before submitting a PR, ensure:
- [ ] JSON is valid (use [jsonlint.com](https://jsonlint.com) to validate)
- [ ] All required fields are filled
- [ ] `status` is one of: `open`, `closed`, `coming-soon`
- [ ] Application link is working
- [ ] README.md table is updated with the new entry
- [ ] Dates are in `YYYY-MM-DD` format where applicable

---

## 🎯 Guidelines

- **Accuracy first**: Only add verified, real opportunities. No spam.
- **Keep it current**: If you notice an opportunity has closed, update its `status` to `"closed"`.
- **India focus**: This repo primarily targets Indian college students, but global programs (GSoC, MLH, etc.) that are accessible to Indian students are welcome.
- **Be respectful**: Follow our [Code of Conduct](CODE_OF_CONDUCT.md).

---

Thank you for contributing! 🙏
