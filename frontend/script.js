
// ── Config ────────────────────────────────────────────────────────────────────
const backendurl = "/api"
const LEVEL_ID = 1   // single jailbreak level

// ── Auth helpers (stored in localStorage) ────────────────────────────────────
function getUser() {
    const uname = localStorage.getItem('username')
    if (!uname) return null
    return { username: uname }
}

function setUser(username) {
    localStorage.setItem('username', username)
}

// ── Level card expand/collapse ────────────────────────────────────────────────
const lvlclass = document.querySelectorAll('.lvl')
lvlclass.forEach(element => {
    element.addEventListener('click', (event) => {
        const clickedElement = event.target.closest('.lvl')
        if (!clickedElement) { return }
        const tagName = event.target.tagName;
        const ignoredTags = ['INPUT', 'BUTTON', 'A', 'CODE'];
        if (ignoredTags.includes(tagName)) { return }
        clickedElement.classList.toggle("expanded")
    })
})

// ── Home page: countdown + server status ─────────────────────────────────────
const midnight = new Date()
midnight.setHours(24, 0, 0, 0)

function timeleft() {
    const now = new Date()
    const difference = midnight - now
    const target = difference < 0 ? 0 : difference
    const fulltime = Math.floor(target / 1000)
    const hours = Math.floor(fulltime / 3600)
    const minutes = Math.floor((fulltime % 3600) / 60)
    const seconds = fulltime % 60
    const formattedh = String(hours).padStart(2, '0')
    const formattedm = String(minutes).padStart(2, '0')
    const formatteds = String(seconds).padStart(2, '0')
    const timeid = document.getElementById('time')
    if (timeid) { timeid.textContent = `${formattedh}:${formattedm}:${formatteds}` }
}

async function serverstatus() {
    try {
        const ping = await fetch(`${backendurl}/health`)
        const pingData = await ping.json()
        const serverid = document.getElementById('serverstats')
        if (serverid) {
            serverid.textContent = pingData.status === "ok" ? "$online" : "$offline"
        }
    } catch (error) {
        const serverid = document.getElementById('serverstats')
        if (serverid) { serverid.textContent = "$offline" }
    }
}

try {
    timeleft()
    serverstatus()
} catch (error) { console.error('Error:', error) }

setInterval(() => { timeleft() }, 1200)

// ── Levels page: fetch + render + open + flag submit (levels.html) ────────────
if (document.URL.includes("levels.html")) {
    window.addEventListener("DOMContentLoaded", async () => {
        const user = getUser()
        if (!user) {
            alert("Please login first!")
            window.location.href = "../login/login.html"
            return
        }

        const loadingEl = document.getElementById("levels-loading")
        const rowEl = document.getElementById("levels-row")

        // 1. Fetch all levels from backend
        let levels = []
        try {
            const res = await fetch(`${backendurl}/levels/list`)
            if (res.ok) { levels = await res.json() }
        } catch (e) {
            console.error("Failed to fetch levels:", e)
        }

        if (!levels.length) {
            if (loadingEl) loadingEl.textContent = "No levels found."
            return
        }
        if (loadingEl) loadingEl.remove()

        // 2. Render each level card
        levels.forEach(lvl => {
            const card = document.createElement("div")
            card.className = "lvl"
            card.id = `lvl${lvl.id}`
            card.innerHTML = `
                <div class="title">lvl${lvl.id}</div>
                <div class="meta">${escapeHtml(lvl.name)}</div>
                <div class="badge locked">locked</div>
                <div class="hiddencontent">
                    <p class="small">${escapeHtml(lvl.description)}</p>
                    <div class="flag-row">
                        <input type="text" placeholder="enter flag (e.g. ENTROPY{...})" class="flag-input" />
                        <button class="check-btn">check</button>
                        <div class="filler-lvl-btn"></div>
                    </div>
                </div>`
            rowEl.appendChild(card)

            // Expand/collapse on click
            card.addEventListener("click", (event) => {
                const ignoredTags = ["INPUT", "BUTTON", "A", "CODE"]
                if (ignoredTags.includes(event.target.tagName)) return
                card.classList.toggle("expanded")
            })

            // Flag submission
            card.querySelector(".check-btn").addEventListener("click", async () => {
                const flaginput = card.querySelector(".flag-input")
                if (!flaginput.value) return
                try {
                    const res = await fetch(`${backendurl}/levels/${lvl.id}/submit`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ username: user.username, submitted_flag: flaginput.value }),
                    })
                    const data = await res.json()
                    if (data.correct) {
                        flaginput.style.border = "1px solid #00ff88"
                        alert(`✅ Flag accepted! Attempts: ${data.attempts}`)
                    } else {
                        flaginput.style.border = "1px solid #ff4444"
                        alert(`❌ Wrong flag. ${data.message}`)
                    }
                } catch (e) {
                    alert("Error submitting flag, try again later")
                }
            })
        })

        // 3. Open all levels to fetch unlock state
        await Promise.all(levels.map(async (lvl) => {
            try {
                const res = await fetch(`${backendurl}/levels/${lvl.id}/open`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username: user.username }),
                })
                if (res.ok) {
                    const badge = document.querySelector(`#lvl${lvl.id} .badge`)
                    if (badge) {
                        badge.classList.remove("locked")
                        badge.classList.add("unlocked")
                        badge.textContent = "unlocked"
                    }
                }
            } catch (e) { /* silently ignore per-level open errors */ }
        }))
    })
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
}

// ── Chatbot (all pages with chatbotcorner) ────────────────────────────────────
if (document.querySelector('#chatboticon')) {
    const chatboticon = document.querySelector('#chatboticon')
    const chatbotid = document.querySelector('#chatbotcorner')
    const toppart = document.querySelector('#top-part')

    chatboticon.addEventListener('click', () => {
        if (chatbotid.classList.contains("expanded")) { return }
        if (!toppart.contains(chatboticon)) { toppart.prepend(chatboticon) }
        chatbotid.classList.add("expanded")
    })

    const chatbotcloseid = document.querySelector('#chatbotclose')
    chatbotcloseid.addEventListener('click', () => {
        if (chatbotid.classList.contains("expanded")) {
            chatbotid.classList.remove("expanded")
        }
        if (toppart.contains(chatboticon)) { chatbotid.prepend(chatboticon) }
    })

    const chatbotsend = document.querySelector('#chatsend')
    chatbotsend.addEventListener('click', async () => {
        const user = getUser()
        const userInput = document.querySelector('#chatinput').value
        if (!userInput) { return }

        const chatPart = document.querySelector('#chat-part')
        const userMessage = document.createElement('p')
        userMessage.classList.add('user')
        userMessage.textContent = userInput
        chatPart.appendChild(userMessage)
        document.querySelector('#chatinput').value = ''

        if (!user) {
            const botMsg = document.createElement('p')
            botMsg.classList.add('bot')
            botMsg.textContent = "Please login first to chat!"
            chatPart.appendChild(botMsg)
            return
        }

        try {
            const res = await fetch(`${backendurl}/levels/${LEVEL_ID}/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: user.username, message: userInput }),
            })
            const data = await res.json()
            const botMessage = document.createElement('p')
            botMessage.classList.add('bot')
            botMessage.textContent = res.ok ? data.response : `Error: ${data.detail}`
            chatPart.appendChild(botMessage)
            chatPart.scrollTop = chatPart.scrollHeight
        } catch (error) {
            console.error('Error:', error)
        }
    })

    // Also send on Enter key
    document.querySelector('#chatinput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { chatbotsend.click() }
    })
}

// ── Leaderboard (leaderboard.html) ───────────────────────────────────────────
if (document.URL.includes("leaderboard.html")) {
    async function get_leaderboard() {
        try {
            const res = await fetch(`${backendurl}/leaderboard`, { method: "GET" })
            const data = await res.json()

            // Clear existing rows (keep header)
            const table = document.querySelector('table')
            const rows = table.querySelectorAll('tr:not(:first-child)')
            rows.forEach(r => r.remove())

            // Clear podium
            const podiumNames = document.querySelectorAll('.team-name')
            podiumNames.forEach(p => { p.textContent = '—' })

            let place = 1
            for (const element of data) {
                const solvedAt = element.last_solved_at
                    ? new Date(element.last_solved_at).toLocaleTimeString()
                    : '—'
                const tabledata = `<tr>
                    <td>[${place}]</td>
                    <td>${element.username}</td>
                    <td>${element.solved_count}<span><img src="../images/flag-dark.png" alt="flag"></span></td>
                    <td>${solvedAt}</td>
                </tr>`
                table.insertAdjacentHTML('beforeend', tabledata)

                // Podium: sec=[1], fir=[2], thir=[3]
                if (place === 1) {
                    document.querySelector('#sec .team-name').textContent = element.username
                } else if (place === 2) {
                    document.querySelector('#fir .team-name').textContent = element.username
                } else if (place === 3) {
                    document.querySelector('#thir .team-name').textContent = element.username
                }
                place++
            }
        } catch (error) {
            console.error('Leaderboard error:', error)
        }
    }

    get_leaderboard()
    setInterval(get_leaderboard, 15000) // refresh every 15s
}

// ── Login (login.html) — stores ctfd_user_id in localStorage  ────────────────
if (document.URL.includes("login.html")) {
    const loginbtn = document.querySelector('#loginbtn')
    if (loginbtn) {
        loginbtn.addEventListener('click', async () => {
            const username = document.querySelector('#username-input').value.trim()
            if (!username) {
                alert("Enter your team name.")
                return
            }
            setUser(username)
            alert(`Logged in as: ${username}`)
            window.location.href = "../index.html"
        })
    }
}
