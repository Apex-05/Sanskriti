(function () {
    "use strict";

    /**
     * ENHANCED CHAT SYSTEM - PRODUCTION QUALITY
     * Features: Typing indicators, online status, message delivery, auto-scroll, etc.
     */

    // ===== UTILITY FUNCTIONS =====
    function getCsrfToken() {
        const csrfInput = document.querySelector('#chatSendForm input[name="csrfmiddlewaretoken"]');
        if (csrfInput && csrfInput.value) {
            return csrfInput.value;
        }
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta && csrfMeta.content && csrfMeta.content !== "NOTPROVIDED") {
            return csrfMeta.content;
        }
        const cookieMatch = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return cookieMatch ? decodeURIComponent(cookieMatch[1]) : "";
    }

    function appendTextWithLineBreaks(container, text) {
        const segments = String(text || "").split("\n");
        segments.forEach(function (segment, index) {
            if (index > 0) {
                container.appendChild(document.createElement("br"));
            }
            container.appendChild(document.createTextNode(segment));
        });
    }

    function formatTimeAgo(dateString) {
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMins === 0) return "now";
            if (diffMins < 60) return diffMins + "m ago";
            if (diffHours < 24) return diffHours + "h ago";
            if (diffDays === 1) return "yesterday";
            if (diffDays < 7) return diffDays + "d ago";

            return date.toLocaleDateString("en-US", {month: "short", day: "numeric"});
        } catch (e) {
            return "online";
        }
    }

    // ===== USER SEARCH MODULE =====
    function initializeUserSearch() {
        const searchInput = document.getElementById("chatUserSearchInput");
        const dropdown = document.getElementById("chatSearchDropdown");

        if (!searchInput || !dropdown) return;

        const searchUrl = searchInput.dataset.searchUrl || "";
        if (!searchUrl) return;

        let debounceTimer = null;

        function renderResults(results) {
            dropdown.innerHTML = "";

            if (!Array.isArray(results) || results.length === 0) {
                const emptyState = document.createElement("p");
                emptyState.className = "chat-search-empty";
                emptyState.textContent = "No users found.";
                dropdown.appendChild(emptyState);
                dropdown.classList.remove("d-none");
                return;
            }

            results.forEach(function (result) {
                const link = document.createElement("a");
                link.className = "chat-search-option";
                link.href = result.chat_url;
                link.innerHTML = '<span class="search-option-avatar">👤</span>' +
                    '<span class="search-option-name">' + (result.username || "") + '</span>';
                dropdown.appendChild(link);
            });

            dropdown.classList.remove("d-none");
        }

        async function runSearch() {
            const query = searchInput.value.trim();
            if (!query) {
                dropdown.classList.add("d-none");
                return;
            }

            try {
                const response = await fetch(searchUrl + "?q=" + encodeURIComponent(query), {
                    headers: {"X-Requested-With": "XMLHttpRequest"}
                });

                if (!response.ok) {
                    dropdown.classList.add("d-none");
                    return;
                }

                const payload = await response.json();
                renderResults(payload.results || []);
            } catch (error) {
                dropdown.classList.add("d-none");
            }
        }

        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(runSearch, 220);
        });

        searchInput.addEventListener("focus", function () {
            if (searchInput.value.trim()) runSearch();
        });

        document.addEventListener("click", function (event) {
            const clickedInside = searchInput.contains(event.target) || dropdown.contains(event.target);
            if (!clickedInside) dropdown.classList.add("d-none");
        });
    }

    // ===== CONVERSATION POLLING & MESSAGING =====
    function initializeConversationPolling() {
        const messageArea = document.getElementById("chatMessageArea");
        const sendForm = document.getElementById("chatSendForm");
        const messageInput = document.getElementById("chatMessageInput");
        const sendButton = document.getElementById("chatSendButton");
        const sendError = document.getElementById("chatSendError");
        const charCount = document.getElementById("charCount");
        const typingIndicator = document.getElementById("chatTypingIndicator");
        const typingUserName = document.getElementById("typingUserName");

        if (!messageArea || !sendForm || !messageInput) return;

        const fetchUrl = messageArea.dataset.fetchUrl || "";
        const sendUrl = sendForm.dataset.sendUrl || messageArea.dataset.sendUrl || "";
        const deliveredUrl = messageArea.dataset.deliveredUrl || "";
        const typingUrl = messageArea.dataset.typingUrl || "";
        const checkTypingUrl = messageArea.dataset.checkTypingUrl || "";
        const onlineStatusUrl = messageArea.dataset.onlineStatusUrl || "";
        const currentUsername = messageArea.dataset.currentUsername || "";
        const pollSeconds = Number.parseInt(messageArea.dataset.pollSeconds || "4", 10);
        const pollIntervalMs = Math.max(2, Number.isNaN(pollSeconds) ? 4 : pollSeconds) * 1000;
        const activityUpdateUrl = messageArea.dataset.activityUpdateUrl || "";
        const activityOfflineUrl = messageArea.dataset.activityOfflineUrl || "";

        if (!fetchUrl || !sendUrl || !currentUsername) return;

        const renderedMessageIds = new Set();
        let lastMessageId = 0;
        let fetchInProgress = false;
        let isUserTyping = false;
        let typingTimeout = null;

        // Initialize rendered message IDs
        messageArea.querySelectorAll(".chat-message-row[data-message-id]").forEach(function (row) {
            const rowId = Number.parseInt(row.dataset.messageId || "0", 10);
            if (rowId > 0) {
                renderedMessageIds.add(rowId);
                if (rowId > lastMessageId) lastMessageId = rowId;
            }
        });

        // ===== UI HELPERS =====
        function shouldStickToBottom() {
            const distanceFromBottom = messageArea.scrollHeight - messageArea.scrollTop - messageArea.clientHeight;
            return distanceFromBottom < 130;
        }

        function scrollToBottom() {
            setTimeout(() => {
                messageArea.scrollTop = messageArea.scrollHeight;
            }, 50);
        }

        function removeEmptyState() {
            const emptyNode = document.getElementById("chatEmptyConversation");
            if (emptyNode) emptyNode.remove();
        }

        function setSendError(message) {
            if (!sendError) return;
            if (!message) {
                sendError.classList.add("d-none");
                sendError.textContent = "";
                return;
            }
            sendError.textContent = message;
            sendError.classList.remove("d-none");
        }

        function updateCharCount() {
            if (!charCount) return;
            const count = messageInput.value.length;
            charCount.textContent = count + " / 2000";
        }

        function updateSendButtonState() {
            if (!sendButton) return;
            sendButton.disabled = false;
        }

        function containsFiles(event) {
            const dataTransfer = event && event.dataTransfer;
            if (dataTransfer && dataTransfer.files && dataTransfer.files.length > 0) {
                return true;
            }

            const clipboardData = event && event.clipboardData;
            if (!clipboardData || !clipboardData.items) {
                return false;
            }

            for (let index = 0; index < clipboardData.items.length; index += 1) {
                if (clipboardData.items[index].kind === "file") {
                    return true;
                }
            }

            return false;
        }

        function blockFileLoading(event) {
            if (!containsFiles(event)) return;
            event.preventDefault();
            setSendError("File upload is disabled. Please send text messages only.");
        }

        // ===== MESSAGE RENDERING =====
        function buildMessageRow(message) {
            const row = document.createElement("article");
            row.className = "chat-message-row " + (message.is_outgoing ? "outgoing" : "incoming");
            row.dataset.messageId = String(message.id);
            row.dataset.isRead = String(message.is_read || false);
            row.dataset.isDelivered = String(message.is_delivered || false);

            const wrapper = document.createElement("div");
            wrapper.className = "chat-message-bubble-wrapper";

            const bubble = document.createElement("div");
            bubble.className = "chat-message-bubble";

            const content = document.createElement("p");
            content.className = "chat-message-content";
            appendTextWithLineBreaks(content, message.content);

            const footer = document.createElement("div");
            footer.className = "chat-message-footer";

            const time = document.createElement("span");
            time.className = "chat-message-time";
            time.textContent = message.timestamp_display || "";
            footer.appendChild(time);

            // Status indicators for outgoing messages
            if (message.is_outgoing) {
                const statusSpan = document.createElement("span");
                statusSpan.className = "chat-message-status";
                statusSpan.id = "msg-status-" + message.id;

                const statusText = document.createElement("span");
                if (message.is_read) {
                    statusText.className = "status-seen";
                    statusText.textContent = "✔✔";
                    statusText.title = "Seen";
                } else if (message.is_delivered) {
                    statusText.className = "status-delivered";
                    statusText.textContent = "✔✔";
                    statusText.title = "Delivered";
                } else {
                    statusText.className = "status-sent";
                    statusText.textContent = "✔";
                    statusText.title = "Sent";
                }
                statusSpan.appendChild(statusText);
                footer.appendChild(statusSpan);
            }

            bubble.appendChild(content);
            bubble.appendChild(footer);
            wrapper.appendChild(bubble);
            row.appendChild(wrapper);

            return row;
        }

        function appendMessages(messages) {
            if (!Array.isArray(messages) || messages.length === 0) return;

            const keepBottom = shouldStickToBottom();
            let appendedCount = 0;

            messages.forEach(function (message) {
                if (!message || typeof message.id !== "number" || renderedMessageIds.has(message.id)) {
                    return;
                }

                removeEmptyState();
                const row = buildMessageRow(message);
                messageArea.appendChild(row);
                renderedMessageIds.add(message.id);
                lastMessageId = Math.max(lastMessageId, message.id);
                appendedCount += 1;
            });

            if (appendedCount > 0 && keepBottom) {
                scrollToBottom();
            }
        }

        function updateMessageStatus(messageId, isDelivered, isRead) {
            const row = messageArea.querySelector('[data-message-id="' + messageId + '"]');
            if (!row) return;

            row.dataset.isDelivered = String(isDelivered || false);
            row.dataset.isRead = String(isRead || false);

            const statusEl = row.querySelector(".chat-message-status span");
            if (statusEl) {
                statusEl.className = "";
                if (isRead) {
                    statusEl.className = "status-seen";
                    statusEl.textContent = "✔✔";
                    statusEl.title = "Seen";
                } else if (isDelivered) {
                    statusEl.className = "status-delivered";
                    statusEl.textContent = "✔✔";
                    statusEl.title = "Delivered";
                } else {
                    statusEl.className = "status-sent";
                    statusEl.textContent = "✔";
                    statusEl.title = "Sent";
                }
            }
        }

        // ===== MESSAGE POLLING =====
        async function pollMessages() {
            if (fetchInProgress) return;

            fetchInProgress = true;
            try {
                const response = await fetch(fetchUrl + "?after_id=" + encodeURIComponent(String(lastMessageId)), {
                    headers: {"X-Requested-With": "XMLHttpRequest"}
                });

                if (!response.ok) return;

                const payload = await response.json();
                appendMessages(payload.messages || []);

                const payloadLastId = Number.parseInt(String(payload.last_message_id || "0"), 10);
                if (payloadLastId > lastMessageId) {
                    lastMessageId = payloadLastId;
                }
            } catch (error) {
                // Silently handle polling errors
            } finally {
                fetchInProgress = false;
            }
        }

        // Mark messages as delivered
        async function markMessagesDelivered() {
            if (!deliveredUrl) return;
            try {
                await fetch(deliveredUrl, {
                    method: "POST",
                    headers: {"X-CSRFToken": getCsrfToken()}
                });
            } catch (e) {
                // Silently fail
            }
        }

        // ===== TYPING INDICATORS =====
        async function sendTypingStatus(isTyping) {
            if (!typingUrl) return;
            try {
                await fetch(typingUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: "is_typing=" + (isTyping ? "true" : "false")
                });
            } catch (e) {
                // Silently fail
            }
        }

        async function checkTypingStatus() {
            if (!checkTypingUrl || !typingIndicator) return;
            try {
                const response = await fetch(checkTypingUrl, {
                    headers: {"X-Requested-With": "XMLHttpRequest"}
                });
                if (response.ok) {
                    const data = await response.json();
                    if (data.is_typing) {
                        typingIndicator.style.display = "flex";
                    } else {
                        typingIndicator.style.display = "none";
                    }
                }
            } catch (e) {
                typingIndicator.style.display = "none";
            }
        }

        // ===== ONLINE STATUS =====
        async function updateOnlineStatus() {
            const statusText = document.getElementById("chatUserStatusText");
            if (!statusText || !onlineStatusUrl) return;

            try {
                const response = await fetch(onlineStatusUrl, {
                    headers: {"X-Requested-With": "XMLHttpRequest"}
                });
                if (response.ok) {
                    const data = await response.json();
                    const statusEl = document.getElementById("chatUserOnlineStatus");
                    if (statusEl) {
                        statusEl.classList.remove("online", "offline");
                        statusEl.classList.add(data.is_online ? "online" : "offline");
                    }
                    if (data.is_online) {
                        statusText.textContent = "online";
                    } else if (data.last_seen) {
                        statusText.textContent = formatTimeAgo(data.last_seen);
                    } else {
                        statusText.textContent = "offline";
                    }
                }
            } catch (e) {
                // Silently fail
            }
        }

        // ===== MESSAGE SENDING =====
        sendForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const content = messageInput.value.trim();
            if (!content) {
                messageInput.classList.add("is-invalid");
                setSendError("Message cannot be empty.");
                return;
            }

            messageInput.classList.remove("is-invalid");
            messageInput.disabled = true;
            setSendError("");

            // Stop typing immediately after sending
            isUserTyping = false;
            clearTimeout(typingTimeout);
            await sendTypingStatus(false);

            try {
                const response = await fetch(sendUrl, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest"
                    },
                    body: JSON.stringify({ content: content })
                });

                if (!response.ok) {
                    messageInput.classList.add("is-invalid");
                    try {
                        const errorPayload = await response.json();
                        setSendError(errorPayload.detail || "Unable to send message.");
                    } catch (jsonError) {
                        setSendError("Unable to send message.");
                    }
                    return;
                }

                const payload = await response.json();
                appendMessages(payload.message ? [payload.message] : []);
                messageInput.value = "";
                messageInput.focus();
                setSendError("");
                updateCharCount();
                updateSendButtonState();
            } catch (error) {
                messageInput.classList.add("is-invalid");
                setSendError("Network error while sending message.");
            } finally {
                messageInput.disabled = false;
                updateSendButtonState();
            }
        });

        // ===== MESSAGE INPUT HANDLERS =====
        messageInput.addEventListener("input", function () {
            if (messageInput.classList.contains("is-invalid") && messageInput.value.trim()) {
                messageInput.classList.remove("is-invalid");
                setSendError("");
            }
            updateCharCount();
            updateSendButtonState();

            // Typing indicator
            if (!isUserTyping && messageInput.value.trim()) {
                isUserTyping = true;
                sendTypingStatus(true);
            }

            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => {
                isUserTyping = false;
                sendTypingStatus(false);
            }, 3000);
        });

        messageInput.addEventListener("keydown", function (evt) {
            // Enter to send, Shift+Enter for new line
            if (evt.key === "Enter" && !evt.shiftKey) {
                evt.preventDefault();
                sendForm.dispatchEvent(new Event("submit"));
            }
        });

        messageInput.addEventListener("dragover", blockFileLoading);
        messageInput.addEventListener("drop", blockFileLoading);
        messageInput.addEventListener("paste", blockFileLoading);
        sendForm.addEventListener("dragover", blockFileLoading);
        sendForm.addEventListener("drop", blockFileLoading);

        // Auto-expand textarea
        messageInput.addEventListener("input", function () {
            this.style.height = "auto";
            this.style.height = Math.min(this.scrollHeight, 100) + "px";
        });

        // ===== INITIALIZATION & POLLING =====
        function initializeAutoActivity() {
            // Update user activity on page visibility
            document.addEventListener("visibilitychange", function () {
                if (document.hidden) {
                    // Page is hidden
                    if (activityOfflineUrl) {
                        fetch(activityOfflineUrl, {
                            method: "POST",
                            headers: {"X-CSRFToken": getCsrfToken()}
                        }).catch(e => {});
                    }
                } else {
                    // Page is visible
                    if (activityUpdateUrl) {
                        fetch(activityUpdateUrl, {
                            method: "POST",
                            headers: {"X-CSRFToken": getCsrfToken()}
                        }).catch(e => {});
                    }
                }
            });

            // Update activity periodically
            setInterval(() => {
                if (!document.hidden && activityUpdateUrl) {
                    fetch(activityUpdateUrl, {
                        method: "POST",
                        headers: {"X-CSRFToken": getCsrfToken()}
                    }).catch(e => {});
                }
            }, 30000); // Every 30 seconds
        }

        // Initial scroll to bottom
        scrollToBottom();
        markMessagesDelivered();
        updateOnlineStatus();

        // Set up polling intervals
        window.setInterval(pollMessages, pollIntervalMs);
        window.setInterval(checkTypingStatus, 1000); // Check typing every second
        window.setInterval(updateOnlineStatus, 5000); // Update online status every 5 seconds
        window.setInterval(markMessagesDelivered, 3000); // Mark as delivered every 3 seconds

        // Auto-activity tracking
        initializeAutoActivity();

        // Initial button state
        updateSendButtonState();
        updateCharCount();
    }

    // ===== INITIALIZE ON DOM READY =====
    document.addEventListener("DOMContentLoaded", function () {
        initializeUserSearch();
        initializeConversationPolling();
    });
})();
