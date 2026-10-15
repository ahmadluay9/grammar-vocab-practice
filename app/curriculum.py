"""Curriculum loader that discovers Levels, Units, and Lessons from the Level/ directory."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from app.config import LEVEL_DIR


@dataclass
class LessonData:
    lesson_id: str
    lesson_number: int
    title: str
    folder_name: str
    content_md: str
    has_markdown_file: bool
    file_paths: list[str] = field(default_factory=list)


@dataclass
class UnitData:
    unit_id: str
    unit_number: int
    level: str
    title: str
    folder_name: str
    lessons: list[LessonData] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if self.unit_number == 0:
            return self.title
        return f"Unit {self.unit_number}: {self.title}"

    @property
    def has_markdown_files(self) -> bool:
        return any(lesson.has_markdown_file for lesson in self.lessons)

    def combined_curriculum_text(self) -> str:
        parts = [f"# Level {self.level} - {self.display_name}"]
        for lesson in self.lessons:
            parts.append(f"\n## Lesson {lesson.lesson_number}: {lesson.title}\n{lesson.content_md.strip()}")
        return "\n".join(parts)

    def to_dict(self, include_content: bool = False) -> dict[str, Any]:
        data = {
            "unit_id": self.unit_id,
            "unit_number": self.unit_number,
            "level": self.level,
            "title": self.title,
            "display_name": self.display_name,
            "folder_name": self.folder_name,
            "has_markdown_files": self.has_markdown_files,
            "lesson_count": len(self.lessons),
            "lessons": [
                {
                    "lesson_id": l.lesson_id,
                    "lesson_number": l.lesson_number,
                    "title": l.title,
                    "folder_name": l.folder_name,
                    "has_markdown_file": l.has_markdown_file,
                    "file_paths": l.file_paths,
                    **({"content_md": l.content_md} if include_content else {}),
                }
                for l in self.lessons
            ],
        }
        return data


# Supplementary study guides for lesson folders that do not yet have a .md file on disk
FALLBACK_LESSON_NOTES: dict[str, str] = {
    "Explaining office technology": """### Grammar - Relative Clauses & Passive Voice for Systems
- Use **which / that** to explain what a device or software system does:
  1. Our cloud platform, **which** syncs automatically, backs up every document in real time.
  2. This is the badge reader **that** grants access to the server room.
- Use the **present simple passive** (*is configured*, *are stored*, *is encrypted*) to describe standard technical processes.

### Vocabulary - Office Systems & Hardware
- **intuitive** (adj): easy to understand and operate without special training
- **seamless** (adj) / **seamlessly** (adv): smooth and continuous, with no interruptions
- **integrate** (v) / **integration** (n): combine two systems so they work together
- **automate** (v) / **automated** (adj): make a process operate automatically
- **authenticate** (v) / **authentication** (n): verify a user's identity before granting access

### Expressions - Walking a colleague through a tool
- **walk you through**: "Let me **walk you through** how the new conferencing system works."
- **get the hang of**: "It looks complex at first, but you'll **get the hang of** it quickly."
- **set up**: "Have IT **set up** your dual-monitor workstation yet?"
- **log in with**: "You can **log in with** your single sign-on credentials."
""",
    "Solving a technical problem": """### Grammar - Modals of Deduction & Causative Structures
- Use **must have / might have / could have + past participle** to diagnose past causes:
  1. The update **must have overwritten** your local configuration file.
  2. A firewall rule **might have blocked** the incoming connection.
- Use **try + -ing** to suggest troubleshooting steps:
  1. Have you **tried clearing** your browser cache and restarting the client?

### Vocabulary - Troubleshooting & Diagnostics
- **glitch** (n): a minor, temporary malfunction in a system
- **outage** (n): a period when a service or network is unavailable
- **workaround** (n): a temporary method for bypassing a problem
- **replicate** (v): reproduce a bug consistently to find its root cause
- **intermittent** (adj): occurring at irregular intervals; not continuous
- **resolve** (v) / **resolution** (n): permanently fix an issue

### Expressions - Reporting and Fixing Issues
- **acting up**: "The printer on the third floor has been **acting up** all morning."
- **narrow down**: "We managed to **narrow down** the issue to a faulty router."
- **back up and running**: "The database server should be **back up and running** within ten minutes."
""",
    "Summarizing a tech presentation": """### Grammar - Reporting Verbs & Nominalization
- Use precise reporting verbs (**highlight**, **demonstrate**, **emphasize**, **project**, **outline**) instead of *say*:
  1. The CTO **highlighted** the need for stronger endpoint security.
  2. The keynote speaker **demonstrated** how AI reduces manual data entry.

### Vocabulary - Innovation & Key Takeaways
- **takeaway** (n): a key fact, point, or idea to be remembered from a presentation
- **scalable** (adj) / **scalability** (n): able to grow and handle increased workload
- **cutting-edge** (adj): at the latest or most advanced stage of development
- **rollout** (n) / **roll out** (phr v): the official launch or deployment of a new product
- **streamline** (v): make an organization or system more efficient by simplifying processes

### Expressions - Recapping a Presentation
- **in a nutshell**: "**In a nutshell**, the presentation focused on migrating our legacy servers."
- **the main takeaway**: "**The main takeaway** was that automation will save 20 hours a week."
- **touch on**: "She also **touched on** the timeline for the Q4 software rollout."
""",
    "Discussing technology in your life": """### Grammar - Used to / Be used to / Get used to & Concession
- **used to + base verb** (past habit) vs. **be/get used to + noun/-ing** (familiarity):
  1. I **used to write** everything in a paper planner, but now I **am used to managing** my schedule on my phone.
- Use **although / even though / despite / in spite of** to contrast pros and cons of technology.

### Vocabulary - Digital Habits & Well-being
- **indispensable** (adj): absolutely necessary; impossible to do without
- **ubiquitous** (adj): present, appearing, or found everywhere
- **obsolete** (adj): outdated; no longer produced or used
- **intrusive** (adj): causing disruption or annoyance through being unwelcome
- **rely on** (phr v) / **reliant on** (adj): dependent on someone or something

### Expressions - Evaluating Personal Tech Use
- **unplug from**: "I try to **unplug from** all screens for at least an hour before bed."
- **keep up with**: "It's exhausting trying to **keep up with** every new software update."
- **second nature**: "Using voice commands while driving has become **second nature** to me."
""",
    "Planning a trip": """### Grammar - Future Continuous & Future Perfect for Itineraries
- Use **will be + -ing** for actions in progress at a specific future time:
  1. This time tomorrow, we **will be flying** over the Atlantic.
- Use **will have + past participle** for actions completed before a future point:
  1. By Friday evening, we **will have visited** three regional offices.

### Vocabulary - Itineraries & Destinations
- **itinerary** (n): a planned route or detailed schedule of a journey
- **stopover** (n) / **layover** (n): a short stay in a place between parts of a journey
- **accommodations** (n): lodging or rooms for travelers
- **off-peak** (adj): during a time of lesser demand or lower prices
- **visa** (n) / **customs** (n): official travel authorization and border inspection

### Expressions - Organizing Travel Plans
- **map out**: "Let's **map out** our schedule before we book the domestic trains."
- **play it by ear**: "For our last afternoon in Lisbon, let's just **play it by ear**."
- **pack light**: "Since we're taking high-speed trains, we should definitely **pack light**."
""",
    "Making travel arrangements": """### Grammar - Indirect Questions & Polite Requests
- Use indirect questions for formal travel bookings:
  1. Could you tell me **whether breakfast is included** in the corporate rate?
  2. I was wondering **if it would be possible** to request a late checkout.

### Vocabulary - Bookings & Reservations
- **complimentary** (adj): provided free of charge (e.g., shuttle, breakfast, upgrade)
- **non-refundable** (adj): unable to be returned or reimbursed if canceled
- **aisle seat** / **window seat** (n): seating preferences on an aircraft or train
- **shuttle** (n): regular transport between an airport and a hotel
- **confirm** (v) / **confirmation** (n): verify a booking officially

### Expressions - Booking Flights and Hotels
- **book in advance**: "If you **book in advance**, you can secure a much lower fare."
- **upgrade to**: "I used my frequent-flyer miles to **upgrade to** business class."
- **check in** / **check out**: "You can **check in** online 24 hours prior to departure."
""",
    "Dealing with flight problems": """### Grammar - Past Perfect & Third Conditional for Travel Disruptions
- Use the **past perfect** (*had already boarded*, *had been canceled*) to show what happened first.
- Use the **third conditional** (*If + past perfect, would have + past participle*) for hypothetical past outcomes:
  1. If the first flight **hadn't been delayed**, I **would have made** my connection in Frankfurt.

### Vocabulary - Delays, Cancellations & Baggage
- **stranded** (adj): left without the means to move from somewhere
- **turbulence** (n): violent or unsteady movement of air during a flight
- **overbooked** (adj): having sold more tickets than there are available seats
- **reimburse** (v) / **reimbursement** (n): repay a traveler for expenses incurred
- **voucher** (n): a coupon redeemable for meals or hotel stays during a delay

### Expressions - Resolving Travel Disruptions
- **miss a connection**: "Due to the snowstorm, dozens of passengers **missed their connection**."
- **rebook on**: "The gate agent managed to **rebook me on** the first flight out tomorrow morning."
- **track down**: "Baggage services promised to **track down** my missing suitcase by tonight."
""",
    "Writing a blog post about a trip": """### Grammar - Descriptive Participle Clauses & Vivid Adjectives
- Use **present participle clauses** (*Walking through the old quarter...*, *Overlooking the harbor...*) to create engaging travel narratives:
  1. **Strolling through** the night market, we sampled dozens of local delicacies.

### Vocabulary - Travel Writing & Experiences
- **breathtaking** (adj): astonishing or awe-inspiring in quality, so as to take one's breath away
- **vibrant** (adj): full of energy, color, and life
- **hidden gem** (n): an outstanding place or thing that is not widely known
- **immerse** (v) / **immersive** (adj): involve oneself deeply in a culture or environment
- **picturesque** (adj): visually attractive, especially in a quaint or charming way

### Expressions - Sharing Travel Recommendations
- **off the beaten path**: "We found a quiet coastal village completely **off the beaten path**."
- **live up to the hype**: "The sunrise over the temple truly **lived up to the hype**."
- **soak in**: "We spent the final evening at a rooftop café just **soaking in** the atmosphere."
""",
    "Networking at an event": """### Grammar - Question Tags & Conversation Starters
- Use **question tags** (*isn't it?*, *haven't you?*, *don't they?*) to initiate natural networking conversations:
  1. The keynote panel was really insightful, **wasn't it**?
  2. You work in the renewable energy sector, **don't you**?

### Vocabulary - Professional Networking
- **rapport** (n): a close and harmonious relationship in which people understand each other
- **keynote** (n): the main speech at a conference that sets the central theme
- **prospect** (n): a potential client, partner, or customer
- **affiliation** (n): a person's official connection to an organization
- **follow up** (phr v) / **follow-up** (n): make further contact after an initial meeting

### Expressions - Working the Room
- **strike up a conversation**: "It's easy to **strike up a conversation** by asking how someone liked the keynote."
- **what brings you to**: "So, **what brings you to** the annual FinTech summit?"
- **keep in touch**: "Here's my card—let's definitely **keep in touch** after the conference."
""",
    "Meeting a client in a social setting": """### Grammar - Polite Offers, Invitations & diplomatic phrasing
- Use **Would you care for... / Allow me to... / I insist on + -ing** in business hospitality:
  1. **Allow me to** get the bill—you're our guest in Tokyo.
  2. **Would you care to** join us for dinner at a traditional restaurant tonight?

### Vocabulary - Business Hospitality & Dining
- **hospitality** (n): friendly and generous reception and entertainment of guests
- **ambiance** / **ambience** (n): the character and atmosphere of a place
- **cuisine** (n): a style or method of cooking, especially as characteristic of a region
- **etiquette** (n): the customary code of polite behavior in business or society
- **toast** (n/v): an expression of good wishes before drinking

### Expressions - Hosting Clients Socially
- **on me / on the company**: "Please put your wallet away—tonight's dinner is **on us**."
- **break the ice**: "Sharing stories about our first jobs really helped **break the ice**."
- **talk shop**: "Let's not **talk shop** all evening; tell me about your photography hobby."
""",
    "Summarizing an evening with a client": """### Grammar - Reported Speech & Evaluative Adverbs
- Use **reported speech** (*mentioned that*, *expressed interest in*, *assured us that*) to brief your team after a client dinner:
  1. Ms. Chen **mentioned that** her firm is expanding its European logistics hub.
  2. She **expressed strong interest in** renewing our service agreement early.

### Vocabulary - Client Relations & Outcomes
- **productive** (adj): achieving a significant amount of positive results
- **receptive** (adj): willing to consider or accept new suggestions and ideas
- **rapport** (n): mutual trust and friendliness built with a client
- **tentative** (adj): not yet fully worked out or agreed upon; provisional
- **endorse** (v) / **endorsement** (n): declare one's support or approval of a proposal

### Expressions - Debriefing the Team
- **hit it off**: "Our engineering lead and their VP of Operations really **hit it off**."
- **on the same page**: "By the end of dinner, both sides were **on the same page** regarding Q2 pricing."
- **pave the way for**: "Last night's meeting should **pave the way for** a multi-year partnership."
""",
    "Discussing a legal case in the news": """### Grammar - Passive Reporting Structures (*It is alleged that... / is said to have...*)
- Use passive reporting verbs (**allege**, **accuse**, **rule**, **settle**, **acquit**) to maintain objectivity when discussing legal news:
  1. The corporation **is alleged to have violated** antitrust regulations.
  2. It **was reported that** both parties reached an out-of-court settlement.

### Vocabulary - Court Cases & Litigation
- **lawsuit** (n) / **litigation** (n): the process of taking legal action in court
- **plaintiff** (n): a person or company who brings a case against another in a court of law
- **defendant** (n): an individual or company sued or accused in a court of law
- **verdict** (n): a formal decision made by a jury or judge
- **allege** (v) / **allegation** (n): claim that someone has done something illegal, typically without proof yet

### Expressions - Talking About Legal News
- **file a lawsuit against**: "Three small competitors **filed a lawsuit against** the tech giant."
- **settle out of court**: "To avoid bad publicity, the company chose to **settle out of court**."
- **set a precedent**: "The Supreme Court's ruling will **set a precedent** for data privacy cases."
""",
    "Explaining a company's legal situation": """### Grammar - Modals of Obligation, Prohibition & Necessity
- Use **be required to**, **be prohibited from + -ing**, **must comply with**, **need not**:
  1. All financial institutions **are required to disclose** material risks to shareholders.
  2. Employees **are strictly prohibited from sharing** proprietary source code.

### Vocabulary - Corporate Compliance & Liability
- **compliance** (n) / **comply with** (v): conformity in fulfilling official legal requirements
- **liability** (n) / **liable** (adj): legal responsibility for one's acts or omissions
- **intellectual property (IP)** (n): creations of the mind such as patents, trademarks, and copyrights
- **infringe** (v) / **infringement** (n): actively break the terms of a law, patent, or agreement
- **audit** (n/v): an official inspection of an organization's accounts or compliance

### Expressions - Assessing Legal Risk
- **in full compliance with**: "Our legal counsel confirmed that we are **in full compliance with** the new regulations."
- **expose the company to**: "Failing to renew the license could **expose the company to** heavy fines."
- **seek legal counsel**: "Before responding to the notice, we should **seek legal counsel**."
""",
    "Finalizing an employment contract": """### Grammar - Conditional Clauses with *Provided that / Unless / As long as / In the event of*
- Formal contracts use precise conditional conjunctions:
  1. The bonus will be paid in December, **provided that** performance targets are met.
  2. Either party may terminate this agreement **in the event of** a material breach.

### Vocabulary - Contract Terms & Clauses
- **clause** (n): a specific article, proviso, or stipulation in a contract
- **confidentiality** (n) / **non-disclosure** (n): obligation to keep company secrets private
- **remuneration** (n): money paid for work or a service (salary, incentives, benefits)
- **probationary period** (n): a trial period at the beginning of employment
- **binding** (adj): involving an obligation that cannot be broken legally

### Expressions - Negotiating & Signing Contracts
- **iron out**: "We just need to **iron out** a few minor details in the relocation clause."
- **draw up a contract**: "HR will **draw up the contract** and send it over for your signature today."
- **sign on the dotted line**: "Once they agreed to the flexible remote policy, I was ready to **sign on the dotted line**."
""",
    "Explaining a law in your country": """### Grammar - Passive Voice with Prepositions & Purpose Clauses (*in order to / so as to*)
- Use **was enacted to / is designed to / is enforced by**:
  1. The Clean Air Act **was enacted in order to** curb industrial emissions.
  2. Strict penalties **are imposed on** businesses that violate labor standards.

### Vocabulary - Legislation & Public Policy
- **enact** (v) / **legislation** (n): make a bill into an official law
- **enforce** (v) / **enforcement** (n): compel observance of or compliance with a law
- **amend** (v) / **amendment** (n): make minor changes to a law to make it fairer or more up-to-date
- **mandatory** (adj): required by law or mandate; compulsory
- **exempt** (adj/v) / **exemption** (n): free from an obligation or liability imposed on others

### Expressions - Describing How Laws Work
- **come into effect**: "The new data protection law will **come into effect** on January 1st."
- **abide by**: "All foreign subsidiaries must **abide by** local employment laws."
- **carry a penalty of**: "Driving without commercial insurance **carries a penalty of** up to $5,000."
""",
    "Talking about a book you've read": """### Grammar - Present Simple for Plot Summaries & Present Perfect for Impact
- Use the **historic present (present simple)** when describing the plot or arguments of a book:
  1. In the opening chapter, the author **traces** the history of global trade and **argues** that geography shapes economics.
- Use the **present perfect** to describe how a book has influenced you.

### Vocabulary - Literature & Book Reviews
- **compelling** (adj): evoking interest, attention, or admiration in a powerfully irresistible way
- **thought-provoking** (adj): stimulating careful consideration or attention
- **protagonist** (n): the leading character in a novel, play, or film
- **narrative** (n): a spoken or written account of connected events; a story
- **insightful** (adj): having or showing an accurate and deep understanding

### Expressions - Discussing Books
- **couldn't put it down**: "The pacing was so tense that I **couldn't put it down** all weekend."
- **shed light on**: "The biography really **sheds light on** how the founder built the company."
- **live up to expectations**: "Although the sequel was popular, it didn't quite **live up to my expectations**."
""",
    "Explaining what you read and why": """### Grammar - Expressing Purpose & Cause (*so that / with a view to + -ing / due to*)
- Explain reading habits using formal purpose structures:
  1. I subscribe to three trade journals **so that** I can stay ahead of market trends.
  2. She reads financial reports daily **with a view to identifying** emerging risks.

### Vocabulary - Reading Habits & Information Sources
- **periodical** (n) / **publication** (n): a magazine, journal, or newspaper published at regular intervals
- **curate** (v) / **curated** (adj): select, organize, and present content carefully
- **credibility** (n) / **credible** (adj): the quality of being trusted and believed in
- **in-depth** (adj): comprehensive and thorough
- **skim** (v) vs. **scrutinize** (v): read quickly for main ideas vs. examine closely and thoroughly

### Expressions - Describing Reading Preferences
- **stay informed about**: "Reading international news helps me **stay informed about** global supply chains."
- **keep abreast of**: "As a lawyer, I have to **keep abreast of** recent regulatory rulings."
- **take it with a grain of salt**: "When reading unverified blogs, you should **take their claims with a grain of salt**."
""",
    "Recommending something to read": """### Grammar - Emphatic Structures (*What I liked most was... / It was the... that...*)
- Use **wh-cleft sentences** and **it-cleft sentences** to make strong, persuasive recommendations:
  1. **What makes this article worth reading is** its practical framework for negotiation.
  2. **It was the final chapter on leadership that** really changed my perspective.

### Vocabulary - Making Recommendations
- **must-read** (n/adj): a piece of writing that is considered essential to read
- **accessible** (adj): easy to understand or appreciate, even for non-specialists
- **concise** (adj): giving a lot of information clearly and in a few words
- **eye-opening** (adj): unexpectedly enlightening or revealing
- **resonated with** (v): evoked a strong feeling of shared emotion or belief

### Expressions - Pitching a Book or Article
- **right up your alley**: "Since you manage product launches, this case study is **right up your alley**."
- **worth a read**: "Even if you're busy, the executive summary is definitely **worth a read**."
- **food for thought**: "The author's critique of remote management gives plenty of **food for thought**."
""",
    "Writing about how media has changed": """### Grammar - Present Perfect Continuous & Contrast Connectors (*Whereas / While / By contrast*)
- Use **present perfect continuous** (*has been shifting*, *have been replacing*) for ongoing media trends.
- Use **whereas / while / by contrast** to compare traditional print media with digital platforms:
  1. **Whereas** print newspapers relied on daily editions, digital outlets publish breaking updates continuously.

### Vocabulary - Media Evolution & Journalism
- **proliferation** (n): rapid increase in the number or amount of something (e.g., digital channels)
- **circulation** (n): the number of copies of a newspaper or magazine distributed
- **sensationalism** (n): the presentation of news in a way that provokes excitement at the expense of accuracy
- **algorithm** (n): automated rules that determine which content appears in a user's feed
- **echo chamber** (n): an environment where a person only encounters opinions that reflect their own

### Expressions - Analyzing Media Trends
- **a shift away from**: "There has been **a dramatic shift away from** traditional cable television."
- **on demand**: "Consumers now expect news and entertainment to be available **on demand**."
- **blur the line between**: "Social platforms have **blurred the line between** professional journalism and opinion."
""",
}


def _parse_number_and_title(folder_name: str, prefix: str = "") -> tuple[int, str]:
    """Parse folders like '1 - Job interviews' or 'Lesson 1 - Writing a cover letter'."""
    pattern = rf"^(?:{prefix}\s*)?(\d+)\s*-\s*(.+)$"
    match = re.match(pattern, folder_name.strip(), re.IGNORECASE)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return 0, folder_name.strip()


def load_units(level_dir: Path = LEVEL_DIR) -> list[UnitData]:
    """Scan the Level/ directory and return all units sorted by level and unit number."""
    units: list[UnitData] = []
    if not level_dir.exists():
        return units

    for level_folder in sorted(level_dir.iterdir(), key=lambda p: p.name):
        if not level_folder.is_dir():
            continue
        level_name = level_folder.name
        for unit_folder in sorted(level_folder.iterdir(), key=lambda p: p.name):
            if not unit_folder.is_dir():
                continue
            unit_num, unit_title = _parse_number_and_title(unit_folder.name)
            unit_id = f"{level_name}_{unit_num}" if level_name != "11" else str(unit_num)

            lessons_by_num: dict[int, LessonData] = {}
            for lesson_folder in sorted(unit_folder.iterdir(), key=lambda p: p.name):
                if not lesson_folder.is_dir():
                    continue
                lesson_num, lesson_title = _parse_number_and_title(lesson_folder.name, prefix="Lesson")
                md_files = sorted(lesson_folder.glob("*.md"))
                has_md = len(md_files) > 0
                if has_md:
                    md_contents = []
                    for md_file in md_files:
                        md_contents.append(md_file.read_text(encoding="utf-8").strip())
                    content_md = "\n\n".join(md_contents)
                else:
                    fallback = FALLBACK_LESSON_NOTES.get(lesson_title, "")
                    content_md = (
                        f"# Unit {unit_num}, Lesson {lesson_num}\n## {lesson_title}\n\n{fallback}"
                        if fallback
                        else f"# Unit {unit_num}, Lesson {lesson_num}\n## {lesson_title}\n"
                    )

                lesson_obj = LessonData(
                    lesson_id=f"u{unit_num}_l{lesson_num}",
                    lesson_number=lesson_num,
                    title=lesson_title,
                    folder_name=lesson_folder.name,
                    content_md=content_md,
                    has_markdown_file=has_md,
                    file_paths=[str(f.relative_to(level_dir.parent)) for f in md_files],
                )
                # Deduplicate or prefer folders with markdown files
                if lesson_num not in lessons_by_num or has_md:
                    lessons_by_num[lesson_num] = lesson_obj

            lessons = [lessons_by_num[k] for k in sorted(lessons_by_num.keys())]
            units.append(
                UnitData(
                    unit_id=unit_id,
                    unit_number=unit_num,
                    level=level_name,
                    title=unit_title,
                    folder_name=unit_folder.name,
                    lessons=lessons,
                )
            )

    units.sort(key=lambda u: (int(u.level) if u.level.isdigit() else 999, u.unit_number))
    return units


def get_unit_by_id(unit_id: str) -> UnitData | None:
    """Find a specific unit by its ID or unit number."""
    if str(unit_id).startswith("general"):
        return build_general_unit_data(str(unit_id))
    for unit in load_units():
        if unit.unit_id == str(unit_id) or str(unit.unit_number) == str(unit_id):
            return unit
    return None


GENERAL_TOPICS: list[dict[str, str]] = [
    {
        "topic_id": "general_science",
        "title": "Science, Nature & Environment",
        "focus": "Mixed conditionals, cause-and-effect transitions (consequently, stem from, give rise to), passive reporting structures, and B2-C2 vocabulary for ecosystems, climate innovation, and scientific discovery.",
        "notes": """### Grammar Focus - Cause, Effect & Mixed Conditionals
- Use **mixed conditionals** (*If + past perfect, would + base verb*) to connect past actions with present consequences:
  1. If researchers **hadn't discovered** penicillin in 1928, modern medicine **would look** completely different today.
- Use precise cause-and-effect verbs: **stem from**, **give rise to**, **trigger**, **attribute to**, **result in**.

### Vocabulary & Expressions - Science & Nature
- **mitigate** (v) / **mitigation** (n): make something less severe, harmful, or painful
- **biodiversity** (n): the variety of plant and animal life in a particular habitat
- **sustainable** (adj) / **sustainability** (n): able to be maintained at a certain rate or level without depleting resources
- **breakthrough** (n): a sudden, dramatic, and important discovery or development
- **feasible** (adj): possible to do easily or conveniently; viable
- **take a toll on** (expr): have a serious, bad effect on someone or something over time
- **tip of the iceberg** (expr): a small, noticeable part of a much larger problem
""",
    },
    {
        "topic_id": "general_psychology",
        "title": "Psychology, Habits & Well-Being",
        "focus": "Modals of deduction and regret, gerunds vs. infinitives after verbs/prepositions, negative inversion (Seldom do we..., Not only does...), and vocabulary for mindset, habits, cognitive biases, and health.",
        "notes": """### Grammar Focus - Negative Inversion & Gerund/Infinitive Patterns
- Use **negative inversion** (*Seldom / Rarely / Not only... but also / Little did...*) for emphasis:
  1. **Rarely do people realize** how strongly sleep deprivation affects decision-making.
- Distinguish verbs followed by **gerunds (-ing)** (*avoid*, *postpone*, *contemplate*, *wind up*) vs. **infinitives (to + verb)** (*tend*, *strive*, *manage*, *hesitate*).

### Vocabulary & Expressions - Psychology & Habits
- **detrimental** (adj): tending to cause harm (usually followed by **to**)
- **ingrained** (adj): firmly fixed or established; difficult to change (e.g., *deeply ingrained habits*)
- **procrastinate** (v) / **procrastination** (n): delay or postpone action; put off doing something
- **mindful** (adj) / **mindfulness** (n): conscious or aware of something in the present moment
- **burnout** (n): physical or mental collapse caused by overwork or stress
- **kick the habit** (expr): stop doing something harmful that you have done for a long time
- **second nature** (expr): a habit or skill that has become automatic and effortless
""",
    },
    {
        "topic_id": "general_culture",
        "title": "Culture, Arts & Everyday Life",
        "focus": "Emphatic cleft sentences (What stood out was..., It was... that...), participle clauses, phrasal verbs in daily conversation, vivid descriptive adjectives, and natural idioms.",
        "notes": """### Grammar Focus - Participle Clauses & Emphatic Cleft Sentences
- Use **participle clauses** (*Having lived abroad..., Surrounded by historic architecture...*) to combine ideas concisely:
  1. **Having grown up** in a bilingual household, she switched between languages effortlessly.
- Use **wh-clefts** (*What captivates audiences is...*) to highlight key points.

### Vocabulary & Expressions - Culture & Everyday Life
- **eclectic** (adj): deriving ideas, style, or taste from a broad and diverse range of sources
- **nostalgic** (adj) / **nostalgia** (n): a sentimental longing for the past
- **authentic** (adj) / **authenticity** (n): genuine, real, and true to its origins
- **captivating** (adj): capable of attracting and holding interest; charming
- **come across** (phr v): find or meet by chance; or give a particular impression
- **brush up on** (phr v): improve one's existing knowledge or skill in a particular area
- **off the top of my head** (expr): without preparation or checking exact facts
""",
    },
    {
        "topic_id": "general_society",
        "title": "Global Society, Urban Life & Economics",
        "focus": "Concession clauses (albeit, notwithstanding, much as, despite the fact that), future perfect & future continuous, relative clauses with prepositions (in which, by which, to whom), and high-utility academic/general vocabulary.",
        "notes": """### Grammar Focus - Advanced Concession & Relative Clauses with Prepositions
- Use **albeit**, **notwithstanding**, **whereas**, and **despite + noun/-ing** to express contrast:
  1. Affordable housing remains scarce, **despite recent efforts** to expand suburban transit.
- Use formal **preposition + relative pronoun** (*the framework **within which** we operate*, *the demographic **to which** this applies*).

### Vocabulary & Expressions - Society & Urban Life
- **infrastructure** (n): the basic physical and organizational structures (transport, power, housing) needed for society
- **disparity** (n): a great difference or inequality (e.g., *economic disparity*)
- **thriving** (adj): prosperous, growing, and flourishing
- **affordable** (adj) / **affordability** (n): reasonably priced; within people's financial means
- **pace of life** (n phr): the speed at which changes and events occur in a community
- **make ends meet** (expr): earn just enough money to pay for basic living expenses
- **pros and cons** (expr): advantages and disadvantages considered carefully
""",
    },
    {
        "topic_id": "general_history",
        "title": "History, Innovation & Human Stories",
        "focus": "Narrative tenses (past simple, past continuous, past perfect, past perfect continuous), third conditionals, dependent prepositions, and vocabulary for turning points, perseverance, and legacy.",
        "notes": """### Grammar Focus - Narrative Tenses & Past Perfect Continuous
- Combine **past perfect** (*had already begun*) and **past perfect continuous** (*had been experimenting for years*) to sequence historical or personal narratives:
  1. The Wright brothers **had been testing** gliders for years before they finally achieved powered flight.

### Vocabulary & Expressions - Innovation & Human Stories
- **unprecedented** (adj): never done or known before
- **pivotal** (adj): of crucial importance in relation to the development or success of something
- **adversity** (n): difficulties or misfortune
- **perseverance** (n) / **persevere** (v): persistence in doing something despite difficulty or delay
- **legacy** (n): the long-lasting impact of particular events or actions that took place in the past
- **against all odds** (expr): despite very low probability of success
- **turning point** (n phr): a time at which a decisive change in a situation occurs
""",
    },
]


def get_general_topics() -> list[dict[str, str]]:
    """Return the catalog of General English vocabulary & grammar topics."""
    return GENERAL_TOPICS


def build_general_unit_data(scope_str: str = "general") -> UnitData:
    """Construct a virtual UnitData object for General Topics (Vocab & Grammar) generation."""
    custom_topic = ""
    if ":" in scope_str:
        _, custom_topic = scope_str.split(":", 1)
        custom_topic = custom_topic.strip()
    elif scope_str != "general":
        custom_topic = scope_str.strip()

    sub_focuses = [
        "High-Utility Collocations & Phrasal Verbs",
        "Word Formation (Noun / Verb / Adjective / Adverb) & Precision Vocabulary",
        "Idiomatic Expressions & Conversational Nuance",
        "Complex Grammar: Conditionals, Modals & Narrative Tenses",
        "Advanced Connectors, Relative Clauses & Dependent Prepositions",
    ]

    if custom_topic:
        matched = next((t for t in GENERAL_TOPICS if t["topic_id"] == custom_topic), None)
        if matched:
            lessons = [
                LessonData(
                    lesson_id=f"{matched['topic_id']}_l{idx+1}",
                    lesson_number=idx + 1,
                    title=f"{matched['title']} — {sub_focuses[idx]}",
                    folder_name=matched["title"],
                    content_md=f"# {matched['title']} ({sub_focuses[idx]})\n\n**Focus:** {matched['focus']}\n\n{matched['notes']}",
                    has_markdown_file=True,
                )
                for idx in range(5)
            ]
            return UnitData(
                unit_id=f"general:{matched['topic_id']}",
                unit_number=0,
                level="General",
                title=f"General: {matched['title']}",
                folder_name="General Topics",
                lessons=lessons,
            )

        # Custom user-specified general topic
        lessons = [
            LessonData(
                lesson_id=f"general_custom_l{idx+1}",
                lesson_number=idx + 1,
                title=f"{custom_topic} — {sub_focuses[idx]}",
                folder_name=custom_topic,
                content_md=(
                    f"# General Topic: {custom_topic} ({sub_focuses[idx]})\n\n"
                    f"**Primary Focus:** {sub_focuses[idx]} in the context of **{custom_topic}**.\n\n"
                    "- Test practical B2–C2 vocabulary: collocations, phrasal verbs, idioms, and exact word forms (noun, verb, adjective, adverb).\n"
                    "- Test essential grammar structures in context: conditionals, modals of deduction, narrative and perfect tenses, passive constructions, relative clauses, and dependent prepositions."
                ),
                has_markdown_file=True,
            )
            for idx in range(5)
        ]
        return UnitData(
            unit_id=f"general:{custom_topic}",
            unit_number=0,
            level="General",
            title=f"General Topic: {custom_topic}",
            folder_name="General Topics",
            lessons=lessons,
        )

    # Default "general" mix across all 5 general topic areas
    lessons = [
        LessonData(
            lesson_id=t["topic_id"],
            lesson_number=idx + 1,
            title=t["title"],
            folder_name=t["title"],
            content_md=f"# General Topic {idx+1}: {t['title']}\n\n**Focus:** {t['focus']}\n\n{t['notes']}",
            has_markdown_file=True,
        )
        for idx, t in enumerate(GENERAL_TOPICS)
    ]
    return UnitData(
        unit_id="general",
        unit_number=0,
        level="General",
        title="General Topics (Vocabulary & Grammar)",
        folder_name="General Topics",
        lessons=lessons,
    )


