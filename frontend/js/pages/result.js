import { h, notice, ring, hbars, colorOf, waveform, fmtDateTime, icon } from "../ui.js";
import { t, tClass } from "../i18n.js";

const bars = (probs, n = 9) => hbars(
  Object.entries(probs)
    .filter(([, v]) => v > 0.0005)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([k, v]) => ({
      label: tClass(k),
      value: v,
      color: colorOf(k),
      text: (v * 100).toFixed(1) + "%"
    }))
);

/* The real, stage-by-stage trace of one analysis */
export function traceView(res, { animate = true } = {}) {
  let i = 0;

  const st = (n, title, ms, ...body) =>
    h("div", {
      class: "stage",
      style: {
        animationDelay: animate ? `${i++ * 0.35}s` : "0s",
        animationDuration: animate ? ".6s" : "0s"
      }
    },
      h("h3", {},
        h("span", { class: "n" }, n),
        title,
        ms != null
          ? h("span", {
              class: "muted small",
              style: { marginLeft: "auto", fontWeight: 600 }
            }, `${ms} ms`)
          : null
      ),
      ...body
    );

  const ms = (k) =>
    (res.trace.find((t) => t.key === k) || {}).ms;

  const detail = (k) =>
    (res.trace.find((t) => t.key === k) || {}).detail;

  const arrow = () =>
    h("div", {
      class: "arrow",
      style: { animationDelay: "0s" }
    }, "↓");

  const flow = [];

  if (res.source === "audio") {
    flow.push(
      st(
        1,
        "Listen: decode + find cry units",
        ms("segment"),
        h("p", { class: "muted small" },
          detail("decode") + ". " + detail("segment")
        ),
        waveform(
          res.waveform,
          res.waveform_seconds,
          res.units.map((u) => ({
            start: u.start,
            end: u.end
          }))
        ),
        h("div", { class: "muted small" },
          "Purple bands = detected cry units"
        )
      ),
      arrow()
    );
  } else {
    flow.push(
      st(
        1,
        "Start from a real dataset row",
        0,
        h("p", { class: "muted small" }, res.trace[0].detail),
        res.true_label
          ? h("div", { class: "chips" },
              h("span", { class: "chip" },
                "Label in dataset: " + res.true_label
              )
            )
          : null
      ),
      arrow()
    );
  }

  const keys = [
    "Duration",
    "Mean_F0",
    "Min_F0",
    "Max_F0",
    "Std_F0",
    "HNR",
    "MFCC_1",
    "MFCC_2",
    "MFCC_3"
  ];

  flow.push(
    st(
      2,
      "Measure 19 acoustic features per unit",
      ms("features"),
      h("div", {
        class: "tablewrap",
        style: { overflowX: "auto" }
      },
        h("table", { class: "mini" },
          h("thead", {},
            h("tr", {},
              h("th", {}, "Unit"),
              keys.map((k) =>
                h("th", {}, k.replace("_", " "))
              )
            )
          ),
          h("tbody", {},
            res.units.slice(0, 6).map((u) =>
              h("tr", {},
                h("td", {},
                  res.source === "audio"
                    ? `${u.start.toFixed(1)}–${u.end.toFixed(1)}s`
                    : "row"
                ),
                keys.map((k) =>
                  h("td", {},
                    u.features[k].toFixed(
                      k === "Duration" ? 2 : 1
                    )
                  )
                )
              )
            )
          )
        )
      ),
      res.units.length > 6
        ? h("div", { class: "muted small" },
            `…and ${res.units.length - 6} more unit(s)`
          )
        : null
    ),
    arrow()
  );

  const ORDER = ["rf", "ada", "et", "hgb"];

  const names = Object.keys(res.stages).sort(
    (a, b) => ORDER.indexOf(a) - ORDER.indexOf(b)
  );

  names.forEach((n, idx) => {
    flow.push(
      st(
        3 + idx,
        `Stage ${idx + 1} · ${res.stage_titles[n]}`,
        ms(n),
        h("p", { class: "muted small" },
          n === "rf"
            ? "Hundreds of decision trees vote on the cry type. Averaged over all units."
            : n === "ada"
              ? "Boosted shallow trees that focus on the examples the forest finds hard."
              : "Extra learner."
        ),
        bars(res.stages[n], 5)
      ),
      arrow()
    );
  });

  let n = 3 + names.length;

  const mlProbs = res.ml
    ? res.ml.probabilities
    : res.probabilities;

  flow.push(
    st(
      n++,
      "ML branch · Stage 3 Logistic Regression",
      ms("meta"),
      h("p", { class: "muted small" },
        "Combines the stage outputs into the ML branch's answer. Reliance: " +
        Object.entries(res.stage_reliance)
          .sort((a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0]))
          .map(([k, v]) =>
            `${res.stage_titles[k]} ${(v * 100).toFixed(0)}%`
          )
          .join(", ")
      ),
      bars(mlProbs, 5)
    ),
    arrow()
  );

  const fused =
    res.fusion &&
    res.fusion.mode === "ml+dl" &&
    res.deep &&
    res.deep.probabilities;

  if (fused) {
    flow.push(
      st(
        n++,
        "DL branch · CNN + BiGRU (parallel)",
        (res.deep.timings_ms || {}).network,
        h("p", { class: "muted small" },
          `A neural network reads the mel-spectrogram over ${res.deep.n_windows || 1} window(s) and votes independently of the ML branch.`
        ),
        bars(res.deep.probabilities, 5)
      ),
      arrow()
    );

    flow.push(
      st(
        n++,
        `Fusion · weighted average (deep weight ${res.fusion.dl_weight})`,
        (res.trace.find((tr) => tr.key === "fusion") || {}).ms,
        h("p", { class: "muted small" },
          `fused = ${(1 - res.fusion.dl_weight).toFixed(2)} × ML + ${Number(res.fusion.dl_weight).toFixed(2)} × DL. The weight was tuned on validation data. ${res.fusion.agree ? "Both branches agreed." : "The branches disagreed; the fused vote decides."}`
        ),
        bars(res.fusion.fused, 5)
      ),
      arrow()
    );
  } else if (res.deep && res.deep.status === "needs_audio") {
    flow.push(
      st(
        n++,
        "DL branch · needs audio",
        null,
        h("p", { class: "muted small" },
          "The CNN works on the recording's spectrogram, so it can't run on a pre-computed dataset row. With real audio, both branches run and are fused."
        )
      ),
      arrow()
    );
  }

  const c = colorOf(res.label);

  flow.push(
    st(
      n++,
      "Final decision",
      null,
      h("div", {
        class: "row",
        style: { gap: "12px" }
      },
        h("b", {
          style: {
            fontSize: "22px",
            color: c
          }
        },
          res.uncertain
            ? `Unclear (best guess: ${res.label})`
            : res.label
        ),
        h("b", {},
          (res.confidence * 100).toFixed(1) + "%"
        )
      ),
      h("p", { class: "muted small" },
        res.uncertain
          ? "Confidence or the gap to the runner-up was too small, so the app does not commit to one cause."
          : "Confidence and margin passed the reliability gate."
      ),
      h("div", { class: "muted small" },
        "Total compute time: " +
        res.trace.reduce((a, t) => a + (t.ms || 0), 0).toFixed(0) +
        " ms"
      )
    )
  );

  return h("div", { class: "lab-flow" }, flow);
}

/* ---------------- ADVICE VIEW ---------------- */

export function adviceView(a) {
  const done = new Set();

  const kids = [
    h("div", { class: "card" },
      h("h3", {}, t("what_try")),
      h("p", { class: "muted small mt" }, a.intro),
      h("ol", { class: "adv" },
        a.steps.map((s) =>
          h("li", {},
            h("b", {}, s.title + ". "),
            s.detail
          )
        )
      ),
      a.source === "gemini"
        ? h("div", { class: "muted small" },
            "Personalised with Gemini from the measured evidence."
          )
        : null
    )
  ];

  if (a.massage) {
    kids.push(
      h("div", { class: "card" },
        h("h3", {}, "Massage guide: " + a.massage.name),
        h("p", { class: "muted small" }, a.massage.body_part),
        h("ol", { class: "adv" },
          a.massage.how_to.map((s) =>
            h("li", {}, s)
          )
        ),
        h("div", { class: "notice warn" },
          a.massage.caution
        )
      )
    );
  }

  if (a.show_lullaby && a.lullaby) {
    kids.push(
      h("div", { class: "card" },
        h("h3", {}, "Lullaby"),
        h("p", {},
          a.lullaby.style + " · " + a.lullaby.tempo
        ),
        h("ul", { class: "adv" },
          a.lullaby.tips.map((tip) =>
            h("li", {}, tip)
          )
        )
      )
    );
  }

  if (a.videos.length) {
    kids.push(
      h("div", { class: "card vid" },
        h("h3", {}, "Helpful videos"),
        a.videos.map((v) =>
          h("a", {
            href: v.url,
            target: "_blank",
            rel: "noopener noreferrer"
          },
            (v.kind === "video" ? "▶ " : "🔎 ") +
            v.label +
            (v.title ? ": " + v.title : "")
          )
        )
      )
    );
  }

  kids.push(
    h("div", { class: "card" },
      h("h3", {}, t("when_help")),
      h("ul", { class: "adv" },
        a.red_flags.map((rf) =>
          h("li", {}, rf)
        )
      ),
      h("p", { class: "muted small mt" }, a.disclaimer)
    )
  );

  return kids;
}

/* ---------------- ANALYSIS RESULT VIEW ---------------- */

export function analysisView(a, { admin = false } = {}) {
  const r = a.result;
  const c = colorOf(r.label);
  const v = r.validation || {};

  const warns = r.quality_warnings || [];

  // Baby illustration filename based on the predicted category.
  const babyImages = {
    Hungry: "hungry.png",
    Tired: "sleepy.png",
    Sleepy: "sleepy.png",
    Discomfort: "discomfort.png",
    "Needs Burping": "needs_burping.png",
    "Belly Pain": "belly_pain.png",
    Scared: "scared.png",
    "Cold / Hot": "cold_hot.png",
    Lonely: "lonely.png",
    Unclear: "unclear.png"
  };

  const babyImage = babyImages[r.label] || "unclear.png";

  const babyImageUrl = new URL(
    `../../assets/babies/${babyImage}`,
    import.meta.url
  ).href;

  const anim = ({
    Hungry: ["🍼", "Your baby may be ready for a feed."],
    Tired: ["🌙", "A calm sleep environment may help."],
    Sleepy: ["🌙", "A calm sleep environment may help."],
    Discomfort: ["🧸", "Check comfort, diaper and temperature."],
    "Needs Burping": ["☁️", "Your baby may need a gentle burp."],
    "Belly Pain": ["🤍", "Check for signs of tummy discomfort."],
    Scared: ["🌼", "A familiar, soothing voice may help."],
    "Cold / Hot": ["🌡️", "Check your baby's temperature and clothing."],
    Lonely: ["💗", "A little closeness may comfort your baby."],
    Unclear: ["👶", "Let's check your baby's needs."]
  }[r.label] || ["👶", "Let's check your baby's needs."]);

  const kids = [
    warns.length
      ? h("div", {
          class: "stack",
          style: { gap: "8px" }
        },
          warns.map((w) =>
            notice(
              w.code === "silent" || w.code === "maybe_not_cry"
                ? "warn"
                : "info",
              t("warn_" + w.code) || w.detail
            )
          )
        )
      : null,

    // Category-specific baby illustration.
    h("div", { class: "cry-animation card" },
      h("div", { class: "cry-baby" },
        h("img", {
          class: "cry-category-image",
          src: babyImageUrl,
          alt: `${r.label} baby illustration`,
          loading: "eager",
          style: {
            width: "100%",
            maxWidth: "230px",
            height: "auto",
            objectFit: "contain",
            display: "block"
          }
        })
      ),
      h("div", {},
        h("b", {}, anim[1]),
        h("div", { class: "muted small" },
          "AuraCry's estimated cry category"
        )
      )
    ),

    h("div", { class: "card" },
      h("div", { class: "muted small" },
        t("predicted_category")
      ),

      h("div", {
        class: "row",
        style: {
          gap: "16px",
          marginTop: "8px"
        }
      },
        ring(a.confidence, c),

        h("div", {},
          h("h1", {
            style: { color: c }
          },
            r.uncertain
              ? tClass("Unclear")
              : tClass(r.label)
          ),

          h("div", {
            class: "muted small",
            style: { marginTop: "4px" }
          },
            r.uncertain
              ? t("best_guess", {
                  x: tClass(r.label)
                })
              : t("confidence")
          )
        )
      ),

      r.uncertain
        ? h("div", { class: "mt" },
            notice(
              "warn",
              t("uncertain_note", {
                x: tClass(r.runner_up_label)
              })
            )
          )
        : null,

      h("div", { class: "honest mt" },
        `Reliability: in cross-validation (new recordings only) this cry type had recall ${v.class_recall == null ? "n/a" : (v.class_recall * 100).toFixed(0) + "%"} and precision ${v.class_precision == null ? "n/a" : (v.class_precision * 100).toFixed(0) + "%"}, learned from ${v.class_recordings ?? "?"} recording(s). ${v.class_share != null && v.class_precision != null && v.class_precision < v.class_share + 0.06 ? "That precision is about the same as always guessing this (most common) cry, so this answer carries little information on its own. " : ""}This is an experimental study tool, not a diagnosis.`
      ),

      r.drift && r.drift.length
        ? h("div", { class: "mt" },
            notice(
              "info",
              `${r.drift.length} measured value(s) lie outside the range of the training data (${r.drift.map((d) => d.feature).join(", ")}). The recording conditions may differ from the training set.`
            )
          )
        : null
    ),

    h("div", { class: "card" },
      h("h3", {}, t("all_categories")),
      bars(r.probabilities)
    ),

    h("div", { class: "card" },
      h("h3", {}, t("why_answer")),
      h("p", { class: "muted small" },
        r.explanation.headline
      ),

      r.explanation.supporting.length
        ? h("ul", { class: "adv" },
            r.explanation.supporting.map((s) =>
              h("li", {}, "✓ " + s.text)
            )
          )
        : null,

      r.explanation.conflicting.length
        ? h("ul", { class: "adv" },
            r.explanation.conflicting.map((s) =>
              h("li", {}, "✗ " + s.text)
            )
          )
        : null,

      r.explanation.caveats.map((tip) =>
        h("div", { class: "muted small" }, tip)
      )
    ),

    r.deep
      ? h("div", { class: "card" },
          h("h3", {}, t("deep_model_title")),
          h("p", { class: "muted small" },
            t("deep_model_blurb")
          ),
          bars(r.deep)
        )
      : null,

    h("details", { class: "card" },
      h("summary", {
        style: {
          cursor: "pointer",
          fontWeight: 800
        }
      }, t("how_decided")),
      h("div", { class: "mt" },
        traceView(r, { animate: false })
      )
    )
  ];

  /* ---------------- MULTI-BABY RESULTS ---------------- */

  const multi = r.multi_baby;

  if (multi && multi.status !== "disabled") {
    if (
      multi.status === "experimental" &&
      Array.isArray(multi.baby_analyses)
    ) {
      kids.push(
        h("div", { class: "card stack" },
          h("h3", {}, "Multiple-baby cry analysis (experimental)"),

          notice(
            "warn",
            multi.notice ||
            "Separated outputs are candidate sources and may not correspond perfectly to individual babies."
          ),

          multi.baby_analyses.map((baby) =>
            h("div", { class: "card stack" },
              h("h3", {},
                `Baby source ${baby.baby}`
              ),

              baby.status === "analyzed"
                ? h("div", {},
                    h("div", {
                      class: "row between"
                    },
                      h("b", {
                        style: {
                          color: colorOf(baby.label)
                        }
                      },
                        baby.uncertain
                          ? `Unclear (best guess: ${baby.label})`
                          : baby.label
                      ),

                      h("b", {},
                        baby.confidence == null
                          ? "—"
                          : (baby.confidence * 100).toFixed(1) + "%"
                      )
                    ),

                    h("p", {
                      class: "muted small"
                    },
                      `${baby.n_units || 0} cry unit(s) analyzed`
                    ),

                    bars(baby.probabilities || {}, 5)
                  )
                : notice(
                    "warn",
                    baby.message ||
                    "This separated source could not be analyzed."
                  )
            )
          )
        )
      );
    } else if (
      multi.status === "unavailable" ||
      multi.status === "not_separated" ||
      multi.status === "analysis_failed"
    ) {
      kids.push(
        notice(
          "info",
          "Multiple-baby separation was not completed. The standard AuraCry analysis above is unchanged. " +
          (multi.message || "")
        )
      );
    }
  }

  /* ---------------- USER ADVICE ---------------- */

  if (!admin) {
    kids.push(
      ...adviceView(r.advice),

      h("div", { class: "card stack" },
        h("h3", {}, "Have questions about this result?"),

        h("p", {
          class: "muted small"
        },
          "Ask AuraCry AI to explain the estimate or discuss general soothing ideas."
        ),

        h("button", {
          class: "btn block",
          onclick: () => window.__go("/user/ai")
        }, "Ask AuraCry AI")
      )
    );
  }

  /* ---------------- AUDIO QUALITY ---------------- */

  const q = r.quality;

  if (q) {
    const audioEl = h("audio", {
      controls: true,
      preload: "metadata",
      src: a.audio_url
    });

    const seg = h("div", {
      class: "seg",
      role: "group"
    });

    const pick = (clean) => {
      seg.replaceChildren(
        h("button", {
          type: "button",
          class: clean ? "" : "on",
          onclick: () => {
            audioEl.src = a.audio_url;
            pick(false);
          }
        }, t("audio_original")),

        h("button", {
          type: "button",
          class: clean ? "on" : "",
          onclick: () => {
            audioEl.src = a.audio_url + "?clean=1";
            pick(true);
          }
        }, t("audio_cleaned"))
      );
    };

    pick(false);

    const col =
      q.label === "good"
        ? "#2FAE80"
        : q.label === "fair"
          ? "#E98A2B"
          : "#DB4F6A";

    kids.push(
      h("div", { class: "card" },
        h("h3", {}, t("quality_label")),

        h("div", {
          class: "row",
          style: {
            gap: "12px",
            alignItems: "center",
            marginTop: "6px"
          }
        },
          h("b", {
            style: {
              fontSize: "26px",
              color: col
            }
          }, q.score),

          h("span", { class: "muted" },
            "/100 · " + t("q_" + q.label)
          )
        ),

        h("div", {
          class: "muted small",
          style: { marginTop: "4px" }
        },
          t("q_snr", { db: q.snr_db })
        ),

        h("div", { class: "mt" }, seg),
        audioEl,

        h("div", {
          class: "muted small mt"
        },
          t("cleaned_hint")
        )
      )
    );
  }

  /* ---------------- AUDIO AND SPECTROGRAM ---------------- */

  kids.push(
    h("div", { class: "card" },
      h("h3", {}, t("audio")),

      h("audio", {
        controls: true,
        preload: "metadata",
        src: a.audio_url
      }),

      h("div", { class: "muted small mt" },
        `${a.audio_filename} • ${a.duration_sec}s`
      )
    ),

    h("div", { class: "card" },
      h("h3", {}, t("mel_spec")),

      h("img", {
        class: "spec",
        src: a.spectrogram_url,
        alt: t("mel_spec")
      })
    ),

    h("div", { class: "card" },
      admin && a.user
        ? [
            h("div", { class: "kv" },
              h("span", {}, "User"),
              h("b", {}, a.user.name)
            ),

            h("div", { class: "kv" },
              h("span", {}, "Email"),
              h("span", {}, a.user.email)
            )
          ]
        : null,

      h("div", { class: "kv" },
        h("span", {}, "Analysis ID"),
        h("b", {}, a.code)
      ),

      h("div", { class: "kv" },
        h("span", {}, "Date / time"),
        h("span", {}, fmtDateTime(a.created_at))
      )
    )
  );

  if (a.report_url) {
    kids.push(
      h("div", { class: "card" },
        h("a", {
          class: "btn",
          href: a.report_url,
          target: "_blank",
          rel: "noopener"
        }, "⬇ " + t("download_report"))
      )
    );
  }

  kids.push(
    h("div", { class: "card disclaimer" },
      h("h3", {},
        "⚕️ " + t("medical_disclaimer_title")
      ),

      h("p", {
        class: "muted small",
        style: { marginTop: "6px" }
      },
        t("medical_disclaimer")
      )
    )
  );

  return h("div", { class: "stack" }, kids);
}