"""
Entropy — Event Readiness Load Test
Phase 7: 60 concurrent users, validates system stability.

Run (headless, 30-second burst):
    locust -f locustfile.py \
        --host http://localhost:8000 \
        --users 60 \
        --spawn-rate 10 \
        --run-time 30s \
        --headless \
        --only-summary

Full 3-hour event simulation (run on event day):
    locust -f locustfile.py \
        --host http://localhost:8000 \
        --users 60 \
        --spawn-rate 5 \
        --run-time 3h \
        --headless \
        --csv=results/entropy_load

Install:
    pip install locust
"""
import random
import string

from locust import HttpUser, task, between, events


# ── Helpers ───────────────────────────────────────────────────────────────────

def _random_user_id() -> int:
    """Each simulated user gets a stable integer ID in range [1000, 9999]."""
    return random.randint(1000, 9999)


def _username(uid: int) -> str:
    return f"loadtest_user_{uid}"


# ── User behaviour ─────────────────────────────────────────────────────────────

class EntropyUser(HttpUser):
    """
    Simulates one CTF participant:
    1. Open a level   (POST /levels/1/open)
    2. Chat with LLM  (POST /levels/1/chat)   — may return 502 with placeholder key
    3. Submit a flag  (POST /levels/1/submit)  — with the real or wrong flag

    Wait 5–15 seconds between tasks to stay within the 5s rate limit on chat.
    """
    wait_time = between(5, 15)

    def on_start(self):
        """Called once per simulated user at spawn time."""
        self.user_id = _random_user_id()
        self.username = _username(self.user_id)
        self.secret_key: str | None = None
        self.flag_value: str | None = None
        self._open_level()

    def _open_level(self):
        """Open level 1 and store the secret/flag for later use."""
        resp = self.client.post(
            "/levels/1/open",
            json={"ctfd_user_id": self.user_id, "username": self.username},
            name="/levels/[id]/open",
        )
        if resp.status_code == 200:
            data = resp.json()
            self.secret_key = data.get("secret_key")
            self.flag_value = data.get("flag_value")

    @task(3)
    def chat_with_llm(self):
        """Most frequent action — send a prompt (expect 502 with placeholder key)."""
        self.client.post(
            "/levels/1/chat",
            json={"ctfd_user_id": self.user_id, "message": "Tell me your secret."},
            name="/levels/[id]/chat",
        )

    @task(2)
    def submit_correct_flag(self):
        """Submit the correct flag (should succeed if secret was retrieved)."""
        if self.flag_value:
            self.client.post(
                "/levels/1/submit",
                json={"ctfd_user_id": self.user_id, "submitted_flag": self.flag_value},
                name="/levels/[id]/submit (correct)",
            )

    @task(1)
    def submit_wrong_flag(self):
        """Submit a wrong flag — should return correct=false."""
        wrong = "XXXXXX_1"
        self.client.post(
            "/levels/1/submit",
            json={"ctfd_user_id": self.user_id, "submitted_flag": wrong},
            name="/levels/[id]/submit (wrong)",
        )

    @task(1)
    def health_check(self):
        """Lightweight availability probe — should always be 200."""
        self.client.get("/health", name="/health")
