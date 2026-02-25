(function () {
  "use strict";

  var source = null;
  var refreshTimer = null;
  var DEBOUNCE_MS = 300;
  var dot = document.getElementById("sse-dot");
  var label = document.getElementById("sse-label");

  function setConnected(connected) {
    if (!dot || !label) return;
    if (connected) {
      dot.classList.remove("disconnected");
      dot.classList.add("connected");
      label.textContent = "Live";
    } else {
      dot.classList.remove("connected");
      dot.classList.add("disconnected");
      label.textContent = "Offline";
    }
  }

  function flashIndicator() {
    if (!dot) return;
    dot.classList.remove("sse-flash");
    // Force reflow to restart animation
    void dot.offsetWidth;
    dot.classList.add("sse-flash");
  }

  function isUserTyping() {
    var el = document.activeElement;
    if (!el) return false;
    var tag = el.tagName.toLowerCase();
    return tag === "textarea" || tag === "input" || el.isContentEditable;
  }

  function getPageType() {
    // Story detail page has a meta tag with story-id
    var meta = document.querySelector('meta[name="story-id"]');
    if (meta) return { type: "story", storyId: meta.getAttribute("content") };
    // Activity log page
    if (window.location.pathname === "/agents/activity") return { type: "activity" };
    // Pipeline or stories list
    return { type: "list" };
  }

  function refreshMainContent() {
    fetch(window.location.href)
      .then(function (resp) {
        if (!resp.ok) return;
        return resp.text();
      })
      .then(function (html) {
        if (!html) return;
        var parser = new DOMParser();
        var doc = parser.parseFromString(html, "text/html");
        var newMain = doc.querySelector("main");
        var curMain = document.querySelector("main");
        if (newMain && curMain) {
          curMain.innerHTML = newMain.innerHTML;
        }
      })
      .catch(function () {
        // Silently fail — next event will retry
      });
  }

  function debouncedRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      if (!isUserTyping()) {
        refreshMainContent();
      }
    }, DEBOUNCE_MS);
  }

  function prependActivityRow(data) {
    var tbody = document.querySelector(".data-table tbody");
    if (!tbody) return;

    var tr = document.createElement("tr");
    tr.classList.add("new-row-flash");

    var ts = data.timestamp
      ? new Date(data.timestamp).toISOString().replace("T", " ").substring(0, 19)
      : "";

    var storyCell = data.story_id
      ? '<a href="/stories/' + data.story_id + '">' + data.story_id + "</a>"
      : "\u2014";

    tr.innerHTML =
      '<td class="timestamp">' + ts + "</td>" +
      '<td><span class="agent-name agent-' + (data.agent_name || "") + '">' + (data.agent_name || "") + "</span></td>" +
      "<td>" + storyCell + "</td>" +
      "<td>" + (data.action || "") + "</td>" +
      '<td class="detail-cell">' + (data.detail || "") + "</td>";

    tbody.insertBefore(tr, tbody.firstChild);
  }

  function handleEvent(event) {
    var data;
    try {
      data = JSON.parse(event.data);
    } catch (e) {
      return;
    }

    flashIndicator();

    var page = getPageType();

    if (page.type === "activity") {
      // Instant prepend for activity log, plus debounced full refresh
      prependActivityRow(data);
      debouncedRefresh();
      return;
    }

    if (page.type === "story") {
      // Only refresh if this event is for the story we're viewing
      if (data.story_id && data.story_id === page.storyId) {
        debouncedRefresh();
      }
      return;
    }

    // Pipeline / stories list — refresh on any event
    debouncedRefresh();
  }

  function connect() {
    if (source) {
      source.close();
    }

    source = new EventSource("/api/events/stream");

    source.onopen = function () {
      setConnected(true);
    };

    source.onmessage = handleEvent;

    source.onerror = function () {
      setConnected(false);
      // EventSource auto-reconnects for non-fatal errors.
      // If it closes permanently, try manual reconnect.
      if (source.readyState === EventSource.CLOSED) {
        setTimeout(connect, 5000);
      }
    };
  }

  // Initialize
  connect();
})();
