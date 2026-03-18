# entropy-server2.0

Entropy is an AI Jailbreak Sprint CTF platform. Participants chat with an LLM that has a secret flag injected into its system prompt, and try to trick the LLM into revealing it. The platform integrates with CTFd for authentication and scoreboard tracking.

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.9+ (for local scripts like `import_csv.py`)

### Starting the Platform

```bash
# Start all services (backend, database, frontend, CTFd)
docker compose up --build -d

# View logs
docker compose logs -f backend
```

Services will be available at:
- CTFd / Platform: http://localhost/
- Chat Interface: http://localhost/chat/
- API: http://localhost/api/

## Bulk User & Team Import

### Overview

The `import_csv.py` script allows you to bulk import teams and users into CTFd. It:
- Creates teams from CSV data
- Creates user accounts with generated passwords
- Automatically assigns users to teams
- Generates credentials output for distribution

### Prerequisites for Import

1. Ensure Docker services are running: `docker compose up -d`
2. Ensure you have the CTFd API token (stored in environment or hardcoded in script)

### Input CSV Format

Create an input CSV file with the following columns:
- `Reg No`: Registration number (groups users into teams)
- `Name`: Full name of the user
- `Email`: Email address
- `Team Name`: Name of the team (users with same Reg No form a team)

**Example:** `sample_input.csv`
```csv
Reg No,Name,Email,Team Name
1,John Doe,john@example.com,Alpha Team
1,Jane Doe,jane@example.com,Alpha Team
2,Bob Smith,bob@example.com,Beta Team
2,Alice Green,alice@example.com,Beta Team
```

### Running the Import

```bash
python3 import_csv.py <input_file.csv> <output_credentials.csv>
```

**Example:**
```bash
python3 import_csv.py sample_input.csv credentials_output.csv
```

### Output

The script generates a CSV file with credentials:
- `Team Name`: The team name
- `Team Password`: Auto-generated team password
- `Username`: Generated from user's name (first_last format)
- `User Password`: Auto-generated user password
- `Email`: User's email address

**Output Example:** `credentials_output.csv`
```csv
Team Name,Team Password,Username,User Password,Email
Alpha Team,Alw57rmX,john_doe,VCVmSrv8,john@example.com
Alpha Team,Alw57rmX,jane_doe,d1UY9Twa,jane@example.com
Beta Team,mBGhI1HG,bob_smith,eakGjPnP,bob@example.com
Beta Team,mBGhI1HG,alice_green,StHogAQC,alice@example.com
```

### Process Details

1. **Team Creation**: Teams are created once per unique team name in the CSV. Duplicate team names reuse the same team.
2. **User Creation**: Users are created with `username` format: `first_last` (lowercase, alphanumeric + underscores)
3. **Team Assignment**: Each user is automatically added to their team
4. **Unique Usernames**: If a username already exists, a counter is appended (e.g., `john_doe1`)
5. **Error Handling**: The script gracefully skips rows with missing data and continues processing

### Script Features

- ✅ Bulk team creation
- ✅ Bulk user creation
- ✅ Automatic user-to-team assignment
- ✅ Random password generation (8 chars, mixed alphanumeric)
- ✅ Duplicate username handling
- ✅ Error resilience (skips invalid rows, continues processing)
- ✅ Progress indicators (✅, ℹ️, ⚠️, ❌)
- ✅ Credentials output for easy distribution

### Troubleshooting

**Q: Script fails with "Token authentication failed" errors**
- Ensure the CTFd API token in `import_csv.py` is correct
- Verify CTFd container is running: `docker ps | grep ctfd`
- Check the .env file has valid `CTFD_SECRET_KEY`

**Q: Users created but not added to teams**
- Check the import script output for `⚠️` warnings
- These indicate users were created but team assignment failed
- Manually add users to teams via CTFd admin interface

**Q: Duplicate email/username errors**
- The script skips rows with missing data
- To re-import with new passwords, delete users first from CTFd admin panel

**Q: "Cannot find curl" or "python3 not found"**
- Ensure you're running the script from the project root
- For macOS: `brew install curl python3`
- For Ubuntu: `sudo apt-get install curl python3`

## Email Credentials Distribution

### Quick Start

```bash
# Preview emails (no sending)
python3 send_credentials.py credentials_output.csv --dry-run

# Send via Gmail
export EMAIL_FROM=your@gmail.com
export EMAIL_PASSWORD=your-app-password
python3 send_credentials.py credentials_output.csv --provider gmail

# Send via SendGrid
export SENDGRID_API_KEY=sg_xxxxx
export EMAIL_FROM=noreply@domain.com
python3 send_credentials.py credentials_output.csv --provider sendgrid

# Send via SMTP
export SMTP_HOST=mail.domain.com
export SMTP_PORT=587
export EMAIL_FROM=admin@domain.com
export EMAIL_PASSWORD=your-password
python3 send_credentials.py credentials_output.csv --provider smtp
```

### Features

- ✅ Multiple email providers (Gmail, SendGrid, SMTP)
- ✅ Dry-run mode to preview emails
- ✅ Personalized emails with team and individual credentials
- ✅ Configurable rate limiting
- ✅ Professional template with setup instructions

### Configuration

**Gmail Setup:**
1. Enable 2FA at myaccount.google.com
2. Create App Password: https://myaccount.google.com/apppasswords
3. Use 16-character password in EMAIL_PASSWORD

**SendGrid Setup:**
1. Create account at https://sendgrid.com
2. Create API key: Settings > API Keys
3. Verify sender: Settings > Sender Authentication

**SMTP Setup:**
Use your organization's mail server settings

### All Options

```
python3 send_credentials.py <file.csv> [options]

Options:
  --dry-run              Preview emails without sending
  --provider {gmail,sendgrid,smtp}  Email provider
  --platform-url URL     Platform URL for participants
  --support-email EMAIL  Support email address
  --delay SECONDS        Delay between emails (default: 0.5)
```

**Full documentation is embedded in send_credentials.py** - Run with `-h` or `--help` to see complete details.

## Database Management

### Database Credentials

See `.env` file for:
- PostgreSQL credentials (for backend)
- CTFd settings

### PostgreSQL Access

```bash
# Connect to backend database
docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB

# Useful queries
SELECT * FROM users;              -- View all Entropy platform users
SELECT * FROM user_level_state;   -- View user progress
SELECT * FROM levels;              -- View all CTF levels
```

### CTFd Database

CTFd uses SQLite (persisted in `./ctfd/` directory):
```bash
# Access CTFd database
sqlite3 ./ctfd/ctfd.db
```

## Common Commands

```bash
# Start/stop services
docker compose up --build -d        # Start with rebuild
docker compose down                 # Stop all services
docker compose logs -f backend      # Watch backend logs

# Database operations
docker compose exec backend alembic upgrade head  # Run migrations
docker compose exec backend alembic revision -m "description"  # Create migration

# Seed teams
docker compose exec backend python3 seed_teams.py teams.csv

# Generate migrations (after model changes)
docker compose exec backend alembic revision --autogenerate -m "description"
```

## Architecture

### Services

1. **Backend** (FastAPI + uvicorn, port 8000)
   - Python API server at `app/main.py`
   - Entry point: `app.main:app`
   - Database: PostgreSQL

2. **Frontend** (Nginx + static files, port 80)
   - Serves `/chat/` with chat interface
   - Reverse-proxies `/api/` to backend
   - Reverse-proxies `/` to CTFd

3. **Database** (PostgreSQL 15)
   - Stores Entropy platform data
   - Accessed via SQLAlchemy ORM

4. **CTFd** (ctfd/ctfd:3.8.2)
   - Handles authentication and scoreboard
   - SQLite database at `/var/ctfd/ctfd.db`
   - Admin panel at root `/`

### Key Data Flow

1. Levels defined in `levels.yaml` → seeded into DB on startup
2. User opens a level → gets unique flag from pool
3. User chats → LLM receives system prompt with flag injected
4. User submits flag → validated locally, synced to CTFd leaderboard

## Project Structure

```
app/
├── main.py                 # FastAPI app, startup hooks, middleware
├── config.py              # Configuration via pydantic-settings
├── database.py            # SQLAlchemy setup
├── models/                # ORM models (User, Level, UserLevelState, etc.)
├── routers/               # API endpoints (/levels, /chat, /submit_flag, etc.)
├── schemas/               # Pydantic request/response models
├── services/              # Business logic (LLM, flags, hints, etc.)
├── scripts/               # Utility scripts (sync_ctfd.py, etc.)
└── middleware/            # Rate limiting, authentication, etc.

ctfd/                       # CTFd database and config
frontend/                   # HTML/CSS/JS for chat interface
nginx/                      # Nginx configuration
levels.yaml                 # CTF levels definition
import_csv.py              # Bulk import script (teams & users)
docker-compose.yml         # Docker services orchestration
```

## Documentation

- `CLAUDE.md` - Detailed architecture and implementation guide
- `DEPLOYMENT_CHECKLIST.md` - Production deployment checklist
- `SECURITY_AUDIT.md` - Security considerations

## Support

For issues or feedback:
- Report bugs: https://github.com/anomalyco/opencode
- Check existing documentation in project root
