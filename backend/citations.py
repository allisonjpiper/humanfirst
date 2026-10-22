"""
citations.py

Articles shown when a user asks a redirected question a second time.
These are fixed, hand-checked citations. The AI never writes or edits them,
so the app cannot invent a source.
"""

CITATIONS = [
    {
        "title": "The water footprint of artificial intelligence: Emerging solutions and governance imperatives",
        "source": "Zohar Barnett-Itzhaki, Water Research, vol. 299 (2026)",
        "url": "https://www.sciencedirect.com/science/article/abs/pii/S0043135426005488",
        "takeaway": "AI's global water footprint could reach 4.2 to 6.6 billion cubic meters a year by 2027, "
        "and about two-thirds of data centers built since 2022 sit in water-stressed regions.",
        "topics": ["environment"],
    },
    {
        "title": "We did the math on AI's energy footprint. Here's the story you haven't heard.",
        "source": "James O'Donnell & Casey Crownhart, MIT Technology Review (May 20, 2025)",
        "url": "https://www.technologyreview.com/2025/05/20/1116327/ai-energy-usage-climate-footprint-big-tech/",
        "takeaway": "A single answer from a large model can take about 6,700 joules, about 8 seconds of running a microwave, "
        "and billions of daily queries add up to a real share of the grid.",
        "topics": ["environment"],
    },
    {
        "title": "The Last Human Job: The Work of Connecting in a Disconnected World",
        "source": "Allison Pugh, Princeton University Press (2024)",
        "url": "https://www.allisonpugh.com/the-last-human-job",
        "takeaway": "Being truly seen by another person is skilled, valuable work. Handing it to machines "
        "erodes the human connection that people need.",
        "topics": ["personal", "connection"],
    },
]


def citations_for(category: str) -> list[dict]:
    """All citations, with the ones that best match the category first."""
    if category == "personal":
        order = ["connection", "environment"]
    else:
        order = ["environment", "connection"]

    def rank(c: dict) -> int:
        return min(order.index(t) if t in order else 99 for t in c["topics"])

    return sorted(CITATIONS, key=rank)
