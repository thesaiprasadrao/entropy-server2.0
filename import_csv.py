#!/usr/bin/env python3
"""
Bulk import teams and users to CTFd using API token.

Usage:
    python3 import_csv.py <input_csv_file> <output_csv_file>

Input CSV format:
    Reg No,Name,Email,Team Name
    1,John Doe,john@example.com,Team A
    2,Jane Doe,jane@example.com,Team A

Output CSV format:
    Team Name,Team Password,Username,User Password,Email
"""

import csv
import random
import string
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import requests

# ================================
# CONFIGURATION
# ================================
BASE_URL = "http://localhost:80"  # Your CTFd URL
TOKEN = "ctfd_248f6e5ba71849e04b735587b9ff214f06c12ecdd08b9ff236f8874fabdc7ed7"
HEADERS = {"Authorization": f"Token {TOKEN}", "Content-Type": "application/json"}
# ================================


def gen_password(length: int = 8) -> str:
    """Generate a random password with letters and digits."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def gen_username(name: str, existing_usernames: set) -> str:
    """Generate a unique username from a name."""
    parts = name.strip().split()
    if len(parts) == 1:
        username = parts[0].lower()
    else:
        username = f"{parts[0]}_{parts[-1]}".lower()  # first_last

    # Remove special characters
    username = "".join(c for c in username if c.isalnum() or c == "_")

    # Ensure uniqueness
    original = username
    counter = 1
    while username in existing_usernames:
        username = f"{original}{counter}"
        counter += 1
    return username


def read_csv(filename: str) -> dict:
    """Read CSV and group by Reg No."""
    teams = defaultdict(list)
    try:
        with open(filename, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                reg_no = row.get("Reg No", "").strip()
                if not reg_no:
                    print(f"⚠️  Skipping row with missing Reg No: {row}")
                    continue
                teams[reg_no].append(row)
        print(f"✅ Read {sum(len(v) for v in teams.values())} users from CSV")
        return teams
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        sys.exit(1)


def create_team(team_name: str, team_pass: str) -> Optional[dict]:
    """Create or get team in CTFd."""
    try:
        # Try to create team
        res = requests.post(
            f"{BASE_URL}/api/v1/teams",
            json={"name": team_name, "password": team_pass},
            headers=HEADERS,
            timeout=10,
        )
        res.raise_for_status()
        team_json = res.json()

        if team_json.get("success"):
            team_id = team_json["data"]["id"]
            print(f"✅ Team created: {team_name} (ID: {team_id})")
            return {"id": team_id, "password": team_pass}
        else:
            # Team might already exist, try to find it
            existing_teams = requests.get(
                f"{BASE_URL}/api/v1/teams", headers=HEADERS, timeout=10
            ).json()

            if existing_teams.get("success"):
                for t in existing_teams.get("data", []):
                    if t["name"].lower() == team_name.lower():
                        print(f"ℹ️  Team already exists: {team_name} (ID: {t['id']})")
                        return {"id": t["id"], "password": team_pass}

            print(f"❌ Failed to create team {team_name}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error creating team {team_name}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating team {team_name}: {e}")
        return None


def create_user(
    username: str, email: str, password: str, team_id: int
) -> Optional[dict]:
    """Create user in CTFd and add to team."""
    try:
        # Create user
        res = requests.post(
            f"{BASE_URL}/api/v1/users",
            json={
                "name": username,
                "email": email,
                "password": password,
                "type": "user",
            },
            headers=HEADERS,
            timeout=10,
        )
        res.raise_for_status()
        user_json = res.json()

        if not user_json.get("success"):
            print(f"❌ Failed to create user {username}: {user_json}")
            return None

        user_id = user_json["data"]["id"]

        # Add user to team
        team_res = requests.post(
            f"{BASE_URL}/api/v1/teams/{team_id}/members",
            json={"user_id": user_id},
            headers=HEADERS,
            timeout=10,
        )
        team_res.raise_for_status()
        team_json = team_res.json()

        if team_json.get("success"):
            print(f"   👤 User created: {username} (ID: {user_id})")
            return {"id": user_id}
        else:
            print(
                f"⚠️  User created but failed to add to team: {username} - {team_json}"
            )
            return {"id": user_id}

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error creating user {username}: {e}")
        return None
    except Exception as e:
        print(f"❌ Error creating user {username}: {e}")
        return None


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("Usage: python3 import_csv.py <input.csv> <output.csv>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"📥 Reading: {input_file}")
    teams_data = read_csv(input_file)

    if not teams_data:
        print("❌ No data found in CSV")
        sys.exit(1)

    print(f"\n🔧 Processing {len(teams_data)} teams...\n")

    # Step 1: Create teams
    team_map = {}  # team_name -> {id, password}

    for reg_no, members in sorted(teams_data.items()):
        # Find team name (first non-empty team name from members)
        team_name = None
        for m in members:
            if m.get("Team Name", "").strip():
                team_name = m.get("Team Name", "").strip()
                break

        if not team_name:
            team_name = f"Team_{reg_no}"

        # Skip if team already processed
        if team_name in team_map:
            print(f"ℹ️  Team already processed: {team_name}")
            continue

        team_pass = gen_password()
        team_info = create_team(team_name, team_pass)

        if team_info:
            team_map[team_name] = team_info

    print()

    # Step 2: Create users and assign to teams
    existing_usernames = set()
    output_credentials = []

    for reg_no, members in sorted(teams_data.items()):
        # Find team name
        team_name = None
        for m in members:
            if m.get("Team Name", "").strip():
                team_name = m.get("Team Name", "").strip()
                break
        if not team_name:
            team_name = f"Team_{reg_no}"

        if team_name not in team_map:
            print(f"⚠️  Skipping users from {team_name} (team creation failed)")
            continue

        team_info = team_map[team_name]
        team_id = team_info["id"]

        print(f"📋 Processing team: {team_name}")

        for m in members:
            name = m.get("Name", "").strip()
            email = m.get("Email", "").strip()

            if not name or not email:
                print(f"   ⚠️  Skipping user with missing name or email: {m}")
                continue

            username = gen_username(name, existing_usernames)
            existing_usernames.add(username)
            user_pass = gen_password()

            # Create user
            user_info = create_user(username, email, user_pass, team_id)

            if user_info:
                output_credentials.append(
                    {
                        "Team Name": team_name,
                        "Team Password": team_info["password"],
                        "Username": username,
                        "User Password": user_pass,
                        "Email": email,
                    }
                )

        print()

    # Step 3: Save credentials to CSV
    print(f"💾 Saving credentials to: {output_file}")
    try:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "Team Name",
                "Team Password",
                "Username",
                "User Password",
                "Email",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_credentials)
        print(f"✅ Saved {len(output_credentials)} credentials to {output_file}")
    except Exception as e:
        print(f"❌ Error writing output CSV: {e}")
        sys.exit(1)

    print(f"\n🎉 Done! Import complete.")
    print(f"   Teams created: {len(team_map)}")
    print(f"   Users created: {len(output_credentials)}")


if __name__ == "__main__":
    main()
