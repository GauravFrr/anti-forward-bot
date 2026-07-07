// Initialize Telegram WebApp WebApp SDK
const tg = window.Telegram.WebApp;
tg.expand(); // Expand TWA to fill screen

// API configuration
const apiBase = ""; // FastAPI runs on the same domain/port
const initData = tg.initData || "";

// State
let channels = [];
let selectedChannel = null;

// Auth Headers
const getHeaders = () => {
    return {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData
    };
};

// Initialize Application
async function init() {
    try {
        // Authenticate User
        const response = await fetch(`${apiBase}/api/me`, { headers: getHeaders() });
        if (response.status === 401) {
            document.body.innerHTML = '<div class="glass-panel" style="margin: 20px; text-align: center;"><h3>Session Error</h3><p class="tip">Please open this dashboard inside the Telegram Bot.</p></div>';
            return;
        }
        
        const user = await response.json();
        
        // Update user UI
        document.getElementById("user-name").innerText = `${user.first_name || 'User'}`;
        
        if (user.is_owner) {
            document.getElementById("user-role").innerText = "👑 Bot Owner";
            document.getElementById("admin-tab-btn").style.display = "block";
            loadAdminStats();
        } else {
            document.getElementById("user-role").innerText = "👤 Subscriber";
        }
        
        // Load Channels
        await loadChannels();
        
    } catch (err) {
        console.error("Initialization failed:", err);
    }
}

// Switch Tabs
function switchTab(tabId) {
    // Toggle active tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = Array.from(document.querySelectorAll(".tab-btn")).find(btn => btn.innerText.toLowerCase().includes(tabId));
    if (activeBtn) activeBtn.classList.add("active");

    // Toggle active contents
    document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));
    document.getElementById(`tab-${tabId}`).classList.add("active");
    
    if (tabId === 'admin') {
        loadAdminStats();
    }
}

// Load User Channels
async function loadChannels() {
    try {
        const response = await fetch(`${apiBase}/api/channels`, { headers: getHeaders() });
        channels = await response.json();
        renderChannels();
    } catch (err) {
        console.error("Failed to load channels:", err);
    }
}

// Render Channels List
function renderChannels() {
    const listEl = document.getElementById("channels-list");
    listEl.innerHTML = "";
    
    if (channels.length === 0) {
        listEl.innerHTML = '<p class="loading-text">⚠️ No channels registered.<br><small class="tip">Add the bot as administrator to your channel to get started!</small></p>';
        return;
    }
    
    channels.forEach(ch => {
        const card = document.createElement("div");
        card.className = "glass-panel channel-card";
        card.onclick = () => openSettings(ch);
        
        const statusMap = {
            "active": "Active",
            "paused": "Paused",
            "permission_error": "Error"
        };
        
        const statusClassMap = {
            "active": "status-active",
            "paused": "status-paused",
            "permission_error": "status-error",
            "removed": "status-error"
        };
        
        const statusLabel = statusMap[ch.status] || ch.status;
        const statusClass = statusClassMap[ch.status] || "status-paused";
        
        card.innerHTML = `
            <div class="channel-meta">
                <h4>${ch.title || 'No Title'}</h4>
                <p class="subtitle">ID: ${ch.channel_id}</p>
            </div>
            <span class="channel-status ${statusClass}">${statusLabel}</span>
        `;
        listEl.appendChild(card);
    });
}

// Open Channel Settings Panel
function openSettings(channel) {
    selectedChannel = channel;
    
    document.getElementById("selected-channel-title").innerText = channel.title || 'Configure Channel';
    document.getElementById("custom-footer").value = channel.custom_footer || "";
    document.getElementById("auto-pin").checked = channel.auto_pin_enabled;
    
    const queueCheckbox = document.getElementById("queue-enabled");
    queueCheckbox.checked = channel.queue_enabled;
    
    document.getElementById("queue-interval").value = channel.queue_interval_minutes || 15;
    document.getElementById("slider-val").innerText = channel.queue_interval_minutes || 15;
    
    toggleQueueSlider();
    
    document.getElementById("settings-panel").style.display = "block";
    document.getElementById("settings-panel").scrollIntoView({ behavior: 'smooth' });
}

// Close Settings Panel
function closeSettings() {
    document.getElementById("settings-panel").style.display = "none";
    selectedChannel = null;
}

// Toggle Queue Slider Visibility
function toggleQueueSlider() {
    const queueEnabled = document.getElementById("queue-enabled").checked;
    document.getElementById("queue-slider-container").style.display = queueEnabled ? "block" : "none";
}

// Update Slider value text
function updateSliderLabel(val) {
    document.getElementById("slider-val").innerText = val;
}

// Save Channel Configuration
async function saveSettings() {
    if (!selectedChannel) return;
    
    const saveBtn = document.getElementById("save-settings-btn");
    saveBtn.innerText = "Saving Configuration...";
    saveBtn.disabled = true;
    
    const payload = {
        custom_footer: document.getElementById("custom-footer").value.trim() || null,
        auto_pin_enabled: document.getElementById("auto-pin").checked,
        queue_enabled: document.getElementById("queue-enabled").checked,
        queue_interval_minutes: parseInt(document.getElementById("queue-interval").value)
    };
    
    try {
        const response = await fetch(`${apiBase}/api/channels/${selectedChannel.id}/settings`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            tg.showPopup({
                title: "Settings Saved",
                message: "Channel configuration updated successfully!",
                buttons: [{ type: "ok" }]
            });
            
            // Reload channels settings
            await loadChannels();
            closeSettings();
        } else {
            throw new Error("Failed to save");
        }
    } catch (err) {
        tg.showPopup({
            title: "Error",
            message: "Failed to update settings. Please try again.",
            buttons: [{ type: "close" }]
        });
    } finally {
        saveBtn.innerText = "Save Configuration";
        saveBtn.disabled = false;
    }
}

// Load Owner Stats (Owner only)
async function loadAdminStats() {
    try {
        const response = await fetch(`${apiBase}/api/stats`, { headers: getHeaders() });
        if (response.ok) {
            const stats = await response.json();
            document.getElementById("metric-users").innerText = stats.total_users;
            document.getElementById("metric-channels").innerText = stats.active_channels;
            document.getElementById("metric-posts").innerText = stats.total_messages;
        }
    } catch (err) {
        console.error("Failed to load admin stats:", err);
    }
}

// Send Broadcast Announcement (Owner only)
async function sendBroadcast() {
    const textEl = document.getElementById("broadcast-message");
    const msg = textEl.value.trim();
    if (!msg) {
        tg.showPopup({
            title: "Warning",
            message: "Broadcast message text cannot be empty.",
            buttons: [{ type: "close" }]
        });
        return;
    }
    
    tg.showPopup({
        title: "Confirm Broadcast",
        message: "Are you sure you want to broadcast this message to all bot subscribers?",
        buttons: [
            { id: "send", type: "destructive", text: "Yes, Send" },
            { id: "cancel", type: "cancel", text: "Cancel" }
        ]
    }, async (btnId) => {
        if (btnId !== "send") return;
        
        try {
            const response = await fetch(`${apiBase}/api/broadcast`, {
                method: "POST",
                headers: getHeaders(),
                body: JSON.stringify({ message: msg })
            });
            
            if (response.ok) {
                const data = await response.json();
                tg.showPopup({
                    title: "Success",
                    message: `Broadcast started in the background to ${data.total_users} users!`,
                    buttons: [{ type: "ok" }]
                });
                textEl.value = "";
            } else {
                throw new Error();
            }
        } catch (err) {
            tg.showPopup({
                title: "Error",
                message: "Broadcast execution failed.",
                buttons: [{ type: "close" }]
            });
        }
    });
}

// Launch application on DOM ready
document.addEventListener("DOMContentLoaded", init);
