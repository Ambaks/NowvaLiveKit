#!/usr/bin/env python3
"""
Nowva AI Discord Server Setup

Creates all categories, channels, roles, topics, and pinned messages
for the Nowva AI team Discord server.

Usage:
    python setup.py                # Run full setup
    python setup.py --dry-run      # Print plan without making changes
    python setup.py --teardown     # Remove everything this script created
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

import discord
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# ── Server Structure Definition ─────────────────────────────────────────────

ROLES = [
    {"name": "Admin", "color": 0x00E5FF, "hoist": True, "permissions": discord.Permissions.all()},
    {"name": "Software", "color": 0xFFB800, "hoist": True, "permissions": discord.Permissions.general()},
    {"name": "Hardware", "color": 0xFF6B35, "hoist": True, "permissions": discord.Permissions.general()},
    {"name": "Advisor", "color": 0x8E8E93, "hoist": True, "permissions": discord.Permissions(
        view_channel=True, read_message_history=True, send_messages=True,
        connect=True, speak=True, add_reactions=True, attach_files=True,
        embed_links=True, use_external_emojis=True,
    )},
    {"name": "Investor", "color": 0x10B981, "hoist": True, "permissions": discord.Permissions(
        view_channel=True, read_message_history=True, send_messages=True,
        connect=True, speak=True, add_reactions=True, attach_files=True,
        embed_links=True, use_external_emojis=True,
    )},
    {"name": "Bot", "color": 0x48484A, "hoist": False, "permissions": discord.Permissions(
        view_channel=True, read_message_history=True, send_messages=True,
        manage_messages=True, embed_links=True, attach_files=True,
        add_reactions=True, use_external_emojis=True,
    )},
]

CATEGORIES = [
    {
        "name": "GENERAL",
        "channels": [
            {"name": "welcome", "topic": "Welcome to Nowva AI — real-time AI fitness coaching"},
            {"name": "announcements", "topic": "Company-wide updates, milestones, launches"},
            {"name": "standups", "topic": "Daily async standups — what you did, what’s next, blockers"},
            {"name": "random", "topic": "Non-work chat, memes, gym PRs"},
        ],
    },
    {
        "name": "ENGINEERING",
        "channels": [
            {"name": "dev-general", "topic": "Cross-cutting eng discussion — architecture, refactors, deps"},
            {"name": "biomechanics", "topic": "CV pipeline, pose estimation, IK solver, fault rules, rep counting"},
            {"name": "voice-and-llm", "topic": "Voice agents, LLM integration, program generator, coaching"},
            {"name": "frontend", "topic": "React SPA, website, UI/UX, Tailwind, LiveKit client"},
            {"name": "hardware", "topic": "Squat rack hardware, CAD, enclosures, camera mounts, manufacturing"},
            {"name": "infra", "topic": "Server (Host-002), deployments, Cloudflare, nginx, systemd, CI/CD"},
        ],
    },
    {
        "name": "PRODUCT",
        "channels": [
            {"name": "product", "topic": "Roadmap, feature specs, user feedback, prioritization"},
            {"name": "bugs", "topic": "Bug reports, triage, tracking"},
        ],
    },
    {
        "name": "INTEGRATIONS",
        "channels": [
            {"name": "github", "topic": "PR notifications, deploy webhooks, CI status"},
            {"name": "bot-logs", "topic": "Bot command output, automation logs"},
        ],
    },
]

VOICE_CHANNELS = [
    {"name": "General Voice"},
    {"name": "Pair Programming"},
]

WELCOME_PIN = """**Welcome to Nowva AI**
Real-time AI fitness coach through voice interaction, computer vision, and biomechanics analysis.

**Quick links:**
• Product: nowvasports.com
• Docs: `docs/` folder in the repo

**Team:**
• @Software — Software Engineering (CV, LLMs, frontend, infra)
• @Hardware — Mechanical Engineering
"""

STANDUPS_PIN = """**Daily Standup Template**
Post by end of day. Keep it short.

```
Yesterday: what you shipped
Today: what you're working on
Blockers: anything stuck
```
"""

MANAGED_NAMES = (
    {r["name"] for r in ROLES}
    | {c["name"] for cat in CATEGORIES for c in cat["channels"]}
    | {cat["name"] for cat in CATEGORIES}
    | {vc["name"] for vc in VOICE_CHANNELS}
)


# ── Helpers ──────────────────────────────────────────────────────────────────

class SetupLog:
    def __init__(self):
        self.entries: list[str] = []
        self.start = datetime.now(timezone.utc)

    def log(self, action: str, name: str, detail: str = ""):
        line = f"- **{action}** `{name}`"
        if detail:
            line += f" — {detail}"
        self.entries.append(line)
        print(f"  {action}: {name}" + (f" ({detail})" if detail else ""))

    def write(self, path: str):
        duration = (datetime.now(timezone.utc) - self.start).total_seconds()
        with open(path, "w") as f:
            f.write(f"# Discord Setup Log\n\n")
            f.write(f"**Ran at:** {self.start.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            f.write(f"**Duration:** {duration:.1f}s\n")
            f.write(f"**Actions:** {len(self.entries)}\n\n")
            for entry in self.entries:
                f.write(entry + "\n")
        print(f"\nLog written to {path}")


def find_by_name(collection, name: str):
    return discord.utils.get(collection, name=name)


# ── Dry Run ──────────────────────────────────────────────────────────────────

def dry_run():
    print("\n=== DRY RUN: Nowva AI Discord Setup ===\n")

    print("ROLES to create:")
    for r in ROLES:
        color_hex = f"#{r['color']:06X}"
        print(f"  @{r['name']}  color={color_hex}  hoist={r['hoist']}")

    print("\nCATEGORIES & CHANNELS to create:")
    for cat in CATEGORIES:
        print(f"\n  ┌─ {cat['name']}")
        for ch in cat["channels"]:
            print(f"  ├─ #{ch['name']}  — {ch['topic']}")

    print("\nVOICE CHANNELS to create:")
    for vc in VOICE_CHANNELS:
        print(f"  \U0001f50a {vc['name']}")

    print("\nPINNED MESSAGES:")
    print(f"  #welcome  — team intro + quick links")
    print(f"  #standups — standup template")

    print(f"\nTotal: {len(ROLES)} roles, "
          f"{sum(len(c['channels']) for c in CATEGORIES)} text channels, "
          f"{len(CATEGORIES)} categories, "
          f"{len(VOICE_CHANNELS)} voice channels")
    print("\nNo changes made. Run without --dry-run to execute.\n")


# ── Setup ────────────────────────────────────────────────────────────────────

async def run_setup(guild: discord.Guild, log: SetupLog):
    # 1. Create roles (bottom-up, then reorder)
    print("\n--- Creating roles ---")
    created_roles: list[discord.Role] = []
    for role_def in ROLES:
        existing = find_by_name(guild.roles, role_def["name"])
        if existing:
            log.log("SKIP", f"@{role_def['name']}", "role already exists")
            created_roles.append(existing)
        else:
            role = await guild.create_role(
                name=role_def["name"],
                color=discord.Color(role_def["color"]),
                hoist=role_def["hoist"],
                permissions=role_def["permissions"],
            )
            log.log("CREATE", f"@{role_def['name']}", f"color=#{role_def['color']:06X}")
            created_roles.append(role)

    # Reorder roles so CEO is highest
    bot_member = guild.me
    bot_top_role = bot_member.top_role
    positions = {}
    for i, role in enumerate(reversed(created_roles)):
        target_pos = bot_top_role.position - 1 - i
        if target_pos < 1:
            target_pos = 1
        positions[role] = target_pos
    try:
        await guild.edit_role_positions(positions=positions)
        log.log("REORDER", "roles", "CEO > Cofounder > Hardware > Advisor > Investor > Bot")
    except discord.HTTPException as e:
        log.log("WARN", "role reorder", str(e))

    # 2. Create categories and text channels
    print("\n--- Creating categories & channels ---")
    for cat_def in CATEGORIES:
        existing_cat = find_by_name(guild.categories, cat_def["name"])
        if existing_cat:
            category = existing_cat
            log.log("SKIP", cat_def["name"], "category already exists")
        else:
            category = await guild.create_category(cat_def["name"])
            log.log("CREATE", cat_def["name"], "category")

        for ch_def in cat_def["channels"]:
            existing_ch = find_by_name(guild.text_channels, ch_def["name"])
            if existing_ch:
                if existing_ch.topic != ch_def["topic"]:
                    await existing_ch.edit(topic=ch_def["topic"])
                    log.log("UPDATE", f"#{ch_def['name']}", "topic updated")
                else:
                    log.log("SKIP", f"#{ch_def['name']}", "channel already exists")
            else:
                await guild.create_text_channel(
                    ch_def["name"],
                    category=category,
                    topic=ch_def["topic"],
                )
                log.log("CREATE", f"#{ch_def['name']}", ch_def["topic"])

    # 3. Create voice channels (under no category, top level)
    print("\n--- Creating voice channels ---")
    for vc_def in VOICE_CHANNELS:
        existing_vc = find_by_name(guild.voice_channels, vc_def["name"])
        if existing_vc:
            log.log("SKIP", vc_def["name"], "voice channel already exists")
        else:
            await guild.create_voice_channel(vc_def["name"])
            log.log("CREATE", vc_def["name"], "voice channel")

    # 4. Pin messages
    print("\n--- Pinning messages ---")
    welcome_ch = find_by_name(guild.text_channels, "welcome")
    if welcome_ch:
        pins = await welcome_ch.pins()
        if not any("Welcome to Nowva AI" in (p.content or "") for p in pins):
            msg = await welcome_ch.send(WELCOME_PIN)
            await msg.pin()
            log.log("PIN", "#welcome", "team intro + quick links")
        else:
            log.log("SKIP", "#welcome pin", "already pinned")

    standups_ch = find_by_name(guild.text_channels, "standups")
    if standups_ch:
        pins = await standups_ch.pins()
        if not any("Daily Standup Template" in (p.content or "") for p in pins):
            msg = await standups_ch.send(STANDUPS_PIN)
            await msg.pin()
            log.log("PIN", "#standups", "standup template")
        else:
            log.log("SKIP", "#standups pin", "already pinned")

    # 5. Delete default channels that Discord auto-creates
    print("\n--- Cleaning defaults ---")
    for ch in guild.text_channels:
        if ch.name == "general" and ch.name not in {
            c["name"] for cat in CATEGORIES for c in cat["channels"]
        }:
            await ch.delete(reason="Replaced by Nowva AI channel structure")
            log.log("DELETE", "#general", "replaced by custom channels")
            break


# ── Teardown ─────────────────────────────────────────────────────────────────

async def run_teardown(guild: discord.Guild, log: SetupLog):
    print("\n--- Teardown: removing managed channels ---")
    for ch in guild.text_channels:
        if ch.name in {c["name"] for cat in CATEGORIES for c in cat["channels"]}:
            await ch.delete(reason="discord_setup teardown")
            log.log("DELETE", f"#{ch.name}", "text channel")

    for vc in guild.voice_channels:
        if vc.name in {v["name"] for v in VOICE_CHANNELS}:
            await vc.delete(reason="discord_setup teardown")
            log.log("DELETE", vc.name, "voice channel")

    print("\n--- Teardown: removing managed categories ---")
    for cat in guild.categories:
        if cat.name in {c["name"] for c in CATEGORIES}:
            await cat.delete(reason="discord_setup teardown")
            log.log("DELETE", cat.name, "category")

    print("\n--- Teardown: removing managed roles ---")
    for role in guild.roles:
        if role.name in {r["name"] for r in ROLES}:
            try:
                await role.delete(reason="discord_setup teardown")
                log.log("DELETE", f"@{role.name}", "role")
            except discord.HTTPException as e:
                log.log("WARN", f"@{role.name}", f"could not delete: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nowva AI Discord server setup")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making changes")
    parser.add_argument("--teardown", action="store_true", help="Remove everything this script created")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found in .env")
        sys.exit(1)
    if not GUILD_ID:
        print("ERROR: GUILD_ID not found in .env")
        sys.exit(1)

    try:
        guild_id_int = int(GUILD_ID)
    except ValueError:
        print(f"ERROR: GUILD_ID must be an integer, got: {GUILD_ID}")
        sys.exit(1)

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.message_content = True

    client = discord.Client(intents=intents)
    log = SetupLog()
    teardown = args.teardown

    @client.event
    async def on_ready():
        guild = client.get_guild(guild_id_int)
        if not guild:
            print(f"ERROR: Could not find guild with ID {GUILD_ID}")
            print(f"  Bot is in: {[g.name for g in client.guilds]}")
            await client.close()
            return

        print(f"Connected to: {guild.name} (ID: {guild.id})")
        print(f"Members: {guild.member_count}")

        try:
            if teardown:
                await run_teardown(guild, log)
            else:
                await run_setup(guild, log)
        except discord.Forbidden as e:
            print(f"\nERROR: Missing permissions — {e}")
            print("Make sure the bot has Administrator permissions.")
        except Exception as e:
            print(f"\nERROR: {e}")
            raise
        finally:
            log_path = os.path.join(os.path.dirname(__file__), "setup_log.md")
            log.write(log_path)
            await client.close()

    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
