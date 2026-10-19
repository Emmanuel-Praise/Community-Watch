"""Add a few sample rows so the dashboard is not empty during a demo.

Run from the backend folder:
    python seed_demo.py
"""

import db


def seed() -> None:
    db.init_db()
    current = db.stats()
    if current["total_reports"] > 0:
        print("Database already has reports, so nothing was added.")
        return

    samples = [
        {
            "type": "fire",
            "severity": "high",
            "description": "Smoke rising from stalls behind Mokolo market.",
            "location_name": "Mokolo market",
            "source": "whatsapp",
            "ai_summary": "Smoke reported behind Mokolo market.",
            "ai_processed": True,
            "details": {"injuries": None, "notes": "Near the main entrance"},
        },
        {
            "type": "theft",
            "severity": "medium",
            "description": "Phone snatched near the bus stop on Oxford Street.",
            "location_name": "Oxford Street",
            "source": "whatsapp_voice",
            "ai_summary": "A phone was snatched near a bus stop.",
            "ai_processed": True,
            "details": {"people": 2, "notes": "Two suspects on a motorcycle"},
        },
        {
            "type": "flood",
            "severity": "high",
            "description": "Road blocked by flooding at Kaneshie market.",
            "location_name": "Kaneshie market",
            "source": "whatsapp",
            "ai_summary": "Flooding is blocking the road near Kaneshie market.",
            "ai_processed": True,
            "details": {},
        },
        {
            "type": "suspicious_activity",
            "severity": "medium",
            "description": "Unknown people checking parked cars on the street.",
            "location_name": "Bastos",
            "source": "manual",
            "ai_summary": "Suspicious people were seen checking parked cars.",
            "ai_processed": True,
            "details": {"people": 3},
        },
    ]
    for sample in samples:
        db.create_report(sample)

    first_head = db.create_head(
        {
            "name": "Joseph Moko",
            "wa_number": "+237600000001",
            "quarter_name": "Mokolo",
            "city": "Yaounde",
            "status": "pending",
        }
    )
    db.set_head_status(first_head["id"], "verified")

    db.create_head(
        {
            "name": "Amina Njoya",
            "wa_number": "+237600000002",
            "quarter_name": "Bastos",
            "city": "Yaounde",
            "status": "pending",
        }
    )
    print("Sample reports and quarter heads added.")


if __name__ == "__main__":
    seed()
