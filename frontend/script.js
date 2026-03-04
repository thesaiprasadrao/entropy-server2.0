
// ── Config ────────────────────────────────────────────────────────────────────
const backendurl = "http://localhost:8000"
const LEVEL_ID = 1   // single jailbreak level

// ── Auth helpers (stored in localStorage) ────────────────────────────────────
function getUser() {
    const uid = localStorage.getItem('ctfd_user_id')
    const uname = localStorage.getItem('username')
    if (!uid || !uname) return null
    return { ctfd_user_id: parseInt(uid), username: uname }
}

function setUser(ctfd_user_id, username) {
    localStorage.setItem('ctfd_user_id', ctfd_user_id)
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

// ── Open level on page load (levels.html) ─────────────────────────────────────
async function openLevel(ctfd_user_id, username) {
    try {
        const res = await fetch(`${backendurl}/levels/${LEVEL_ID}/open`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ctfd_user_id, username }),
        })
        if (!res.ok) { return null }
        return await res.json()
    } catch (error) {
        console.error('Error opening level:', error)
        return null
    }
}

// ── Level status + flag submission (levels.html) ──────────────────────────────
if (document.URL.includes("levels.html")) {
    window.addEventListener("DOMContentLoaded", async () => {
        const user = getUser()
        if (!user) {
            alert("Please login first!")
            window.location.href = "../login/login.html"
            return
        }

        // Open level to get/create user secret
        const state = await openLevel(user.ctfd_user_id, user.username)
        if (state) {
            // Mark level as unlocked in UI
            const badge = document.querySelector(`#lvl${LEVEL_ID} .badge`)
            if (badge) {
                badge.classList.remove("locked")
                badge.classList.add("unlocked")
                badge.textContent = "unlocked"
            }
        }
    })

    const flagcheck = document.querySelectorAll('.check-btn')
    flagcheck.forEach(element => {
        element.addEventListener('click', async () => {
            const user = getUser()
            if (!user) {
                alert("Please login first!")
                return
            }

            const flaginput = element.closest('.flag-row').querySelector('.flag-input')
            const lvlEl = element.closest('.lvl')
            const lvlid = lvlEl ? parseInt(lvlEl.id.replace('lvl', '')) : LEVEL_ID

            if (!flaginput.value) { return }

            try {
                const res = await fetch(`${backendurl}/levels/${lvlid}/submit`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        ctfd_user_id: user.ctfd_user_id,
                        submitted_flag: flaginput.value,
                    }),
                })
                const response = await res.json()
                if (response.correct) {
                    flaginput.style.border = "1px solid #00ff88"
                    alert(`✅ Flag accepted! Attempts: ${response.attempts}`)
                } else {
                    flaginput.style.border = "1px solid #ff4444"
                    alert(`❌ Wrong flag. ${response.message}`)
                }
            } catch (error) {
                console.error('Error:', error)
                alert("Error submitting flag, try again later")
            }
        })
    })
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
                body: JSON.stringify({ ctfd_user_id: user.ctfd_user_id, message: userInput }),
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
            const ctfdId = document.querySelector('#ctfd-id-input').value.trim()
            const username = document.querySelector('#username-input').value.trim()

            if (!ctfdId || !username) {
                alert("Enter both your CTFd User ID and username.")
                return
            }
            if (isNaN(parseInt(ctfdId))) {
                alert("CTFd User ID must be a number.")
                return
            }

            setUser(parseInt(ctfdId), username)
            alert(`Logged in as: ${username} (ID: ${ctfdId})`)
            window.location.href = "../index.html"
        })
    }
}
