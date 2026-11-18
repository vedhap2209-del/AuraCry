
import { api } from "../api.js";
import { h, notice, backBar, mascot, fmtDate } from "../ui.js";

function bubble(kind, text) {
  return h(
    "div",
    { class: `chat-bubble ${kind}` },
    kind === "bot"
      ? h("span", { class: "bot-mark" }, "🤖")
      : null,
    h("span", {}, text)
  );
}

export async function companionPage() {
  const thread = h("div", { class: "chat-thread" });
  const status = h("div");

  const input = h("textarea", {
    rows: 2,
    maxlength: 2000,
    placeholder: "Ask AuraCry anything about your baby's care…",
    class: "chat-input"
  });

  const send = h(
    "button",
    { class: "btn", type: "button" },
    "Send"
  );

  // Memory suggestion card
  const appendMemoryPrompt = (m) => {
    const card = h(
      "div",
      { class: "memory-confirm card" },

      h(
        "b",
        {},
        `Save “${m.title}” to Baby's Memory Diary?`
      ),

      h(
        "p",
        { class: "muted small" },
        `${m.story} · ${m.event_date}`
      ),

      h(
        "div",
        { class: "row wrap" },

        h(
          "button",
          {
            class: "btn",
            onclick: async () => {
              try {
                await api("/companion/memories", {
                  method: "POST",
                  body: m
                });

                card.replaceChildren(
                  notice(
                    "ok",
                    "Saved to Baby's Memory Diary."
                  )
                );

              } catch (e) {
                card.replaceChildren(
                  notice(
                    "err",
                    e.message || "Could not save memory."
                  )
                );
              }
            }
          },
          "Save memory"
        ),

        h(
          "button",
          {
            class: "btn ghost",
            onclick: () => card.remove()
          },
          "Not now"
        )
      )
    );

    thread.append(card);
  };

  // Send message to AuraCry AI
  const ask = async () => {
    const msg = input.value.trim();

    if (!msg || send.disabled) return;

    thread.append(bubble("user", msg));

    input.value = "";
    send.disabled = true;

    const waiting = bubble("bot", "AuraCry is thinking…");
    thread.append(waiting);

    try {
      const d = await api("/companion/chat", {
        method: "POST",
        body: {
          message: msg
        }
      });

      waiting.replaceWith(
        bubble(
          "bot",
          d.answer || "I couldn't generate a response. Please try again."
        )
      );

      if (d.memory_suggestion) {
        appendMemoryPrompt(d.memory_suggestion);
      }

    } catch (e) {
      waiting.replaceWith(
        bubble(
          "bot",
          e.message || "I couldn't answer just now. Please try again."
        )
      );

    } finally {
      send.disabled = false;
      thread.scrollTop = thread.scrollHeight;
    }
  };

  send.onclick = ask;

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  });

  // Quick questions
  const quick = [
    "Why might my baby be crying?",
    "How can I soothe my baby?",
    "Explain my latest cry result.",
    "What should I ask the pediatrician?"
  ];

  return h(
    "div",
    { class: "stack-lg" },

    backBar(
      "AuraCry AI Companion",
      "/user/home"
    ),

    h(
      "div",
      { class: "companion-head card" },

      h(
        "div",
        { class: "bot-avatar" },
        "🤖"
      ),

      h(
        "div",
        {},

        h(
          "h2",
          {},
          "AuraCry AI Companion"
        ),

        h(
          "p",
          { class: "muted small" },
          "Your baby's caring AI friend"
        )
      )
    ),

    h(
      "div",
      { class: "card stack" },

      thread,
      status,

      h(
        "div",
        { class: "quick-prompts" },

        quick.map((q) =>
          h(
            "button",
            {
              class: "chip",
              onclick: () => {
                input.value = q;
                ask();
              }
            },
            q
          )
        )
      ),

      h(
        "div",
        { class: "chat-compose" },
        input,
        send
      )
    ),

    h(
      "p",
      { class: "muted small" },
      "AuraCry provides educational guidance, not a medical diagnosis. For urgent symptoms or concerns, contact a healthcare professional."
    )
  );
}


// ============================================
// BABY'S MEMORY DIARY
// ============================================

export async function diaryPage() {

  const holder = h(
    "div",
    { class: "stack" }
  );

  // Load all saved memories
  const load = async () => {

    holder.replaceChildren(
      notice("info", "Loading your baby's memories...")
    );

    try {

      const d = await api("/companion/memories");

      const memories = Array.isArray(d.memories)
        ? d.memories
        : [];

      // Empty diary
      if (memories.length === 0) {

        holder.replaceChildren(
          h(
            "div",
            { class: "card empty" },

            h("div", {}, "📖"),

            h(
              "h3",
              {},
              "No memories yet"
            ),

            h(
              "p",
              { class: "muted" },
              "Your baby's special moments will appear here. Tell AuraCry AI about a first step, first word or another special moment."
            )
          )
        );

        return;
      }

      // Create one card for every memory
      const cards = memories.map((m) => {

        const deleteButton = h(
          "button",
          {
            class: "text-btn",
            onclick: async () => {

              if (!confirm("Are you sure you want to delete this memory?")) {
                return;
              }

              try {

                await api(
                  `/companion/memories/${m.id}`,
                  {
                    method: "DELETE"
                  }
                );

                // Reload diary after deletion
                await load();

              } catch (e) {

                alert(
                  e.message || "Could not delete memory."
                );

              }
            }
          },
          "Delete memory"
        );

        return h(
          "article",
          { class: "memory-card card" },

          h(
            "div",
            { class: "memory-date" },
            `📅 ${fmtDate(m.event_date)}`
          ),

          h(
            "h3",
            {},
            m.title || "Special Memory"
          ),

          h(
            "p",
            {},
            m.story || ""
          ),

          deleteButton
        );
      });

      // IMPORTANT:
      // Pass individual DOM elements to replaceChildren.
      // Do not pass the cards array as one argument.
      holder.replaceChildren(...cards);

    } catch (e) {

      holder.replaceChildren(
        notice(
          "err",
          e.message || "Could not load your baby's memories."
        )
      );

    }
  };

  // Load diary when the page opens
  await load();

  return h(
    "div",
    { class: "stack-lg" },

    backBar(
      "Baby's Memory Diary",
      "/user/home"
    ),

    h(
      "div",
      { class: "diary-intro card" },

      h(
        "div",
        { class: "diary-icon" },
        "📖"
      ),

      h(
        "h2",
        {},
        "Little moments, forever remembered"
      ),

      h(
        "p",
        { class: "muted" },
        "Tell AuraCry AI about a first step, first word or another special moment. It can suggest a diary entry for you to confirm."
      )
    ),

    h(
      "button",
      {
        class: "btn block",
        onclick: () => window.__go("/user/ai")
      },
      "Tell AuraCry AI about a memory"
    ),

    holder
  );
}
