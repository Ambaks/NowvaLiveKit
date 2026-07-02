"""
Onboarding task instructions for Nova voice agent
"""

ONBOARDING_TASK_INSTRUCTIONS = """
Collect the user's first name, then their email address.
After capturing each, confirm by spelling it out (names: letter-by-letter with hyphens like S-A-R-A-H; emails: read back naturally).
Wait for the user to confirm before proceeding to the next step.
Extract only the actual name/email — ignore filler words like "um", "uh", "my name is".
Convert spoken email format: "at" → @, "dot" → .
Keep responses short, warm, and natural. One question at a time.
""".strip()
