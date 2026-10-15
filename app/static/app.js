// FluentPulse AI — Frontend Logic

const state = {
  config: null,
  units: [],
  generalTopics: [],
  selectedDate: '',
  selectedUnitScope: 'all',
  currentSet: null,
  draftAnswers: {}, // question_number -> string
  activeUnitFilter: 'all',
};

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatScopeLabel(scope) {
  if (!scope || scope === 'all') return 'All Units (Daily 25 Categorized Mix)';
  if (scope === 'general') return 'General Topics (Daily 25 Vocab & Grammar Mix)';
  if (String(scope).startsWith('general:')) {
    const sub = String(scope).slice(8);
    const matched = state.generalTopics.find((t) => t.topic_id === sub);
    return matched ? `General: ${matched.title}` : `General Topic: ${sub}`;
  }
  const unit = state.units.find((u) => String(u.unit_id) === String(scope));
  return unit ? unit.display_name : `Unit ${scope}`;
}

function showLoading(title, subtitle) {
  const banner = document.getElementById('loading-banner');
  document.getElementById('loading-title').textContent = title || 'Working...';
  document.getElementById('loading-subtitle').textContent = subtitle || '';
  banner.classList.remove('hidden');
}

function hideLoading() {
  document.getElementById('loading-banner').classList.add('hidden');
}

function scoreColorClass(score) {
  if (score >= 90) return 'score-excellent';
  if (score >= 75) return 'score-good';
  if (score >= 45) return 'score-partial';
  return 'score-low';
}

async function initApp() {
  bindNavigation();
  try {
    const [cfgResp, unitsResp] = await Promise.all([
      fetch('/api/config').then((r) => r.json()),
      fetch('/api/units').then((r) => r.json()),
    ]);
    state.config = cfgResp;
    state.units = unitsResp.units || [];
    state.generalTopics = unitsResp.general_topics || [];
    state.selectedDate = cfgResp.today;

    document.getElementById('header-model-name').textContent = cfgResp.model_name;
    const datePicker = document.getElementById('daily-date-picker');
    datePicker.value = state.selectedDate;
    datePicker.addEventListener('change', (e) => {
      if (e.target.value) {
        state.selectedDate = e.target.value;
        loadDailySet(state.selectedDate, state.selectedUnitScope);
      }
    });

    document.getElementById('btn-generate-new').addEventListener('click', () => {
      generateNewDailySet(state.selectedDate, state.selectedUnitScope);
    });

    document.getElementById('btn-grade-all').addEventListener('click', () => {
      gradeAllAnswered();
    });

    document.getElementById('btn-refresh-history').addEventListener('click', () => {
      loadHistory();
    });

    const customForm = document.getElementById('custom-topic-form');
    if (customForm) {
      customForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const inputEl = document.getElementById('custom-topic-input');
        const val = (inputEl?.value || '').trim();
        const targetScope = val ? `general:${val}` : 'general';
        state.selectedUnitScope = targetScope;
        state.activeUnitFilter = 'all';
        renderUnitScopeSidebar();
        loadDailySet(state.selectedDate, state.selectedUnitScope);
      });
    }

    renderUnitScopeSidebar();
    renderStudyUnitSelector();
    if (state.units.length > 0) {
      loadStudyGuide(state.units[0].unit_id);
    }

    await loadDailySet(state.selectedDate, state.selectedUnitScope);
    await loadHistory();
  } catch (err) {
    console.error('Initialization failed:', err);
  }
}

function bindNavigation() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.getAttribute('data-tab');
      document.querySelectorAll('.tab-view').forEach((sec) => {
        sec.classList.add('hidden');
        sec.classList.remove('active');
      });
      const activeSec = document.getElementById(`view-${target}`);
      if (activeSec) {
        activeSec.classList.remove('hidden');
        activeSec.classList.add('active');
      }
      if (target === 'analytics') {
        renderCurrentSetAnalytics();
        loadHistory();
      }
    });
  });
}

function renderUnitScopeSidebar() {
  const generalContainer = document.getElementById('general-scope-list');
  if (generalContainer) {
    const generalItems = [
      {
        scope: 'general',
        title: '🌟 General Topics (Daily 25 Mix)',
        meta: '5 diverse domains: Vocab, Idioms, Collocations & Grammar',
        badge: '25 Qs',
      },
      ...state.generalTopics.map((t) => ({
        scope: `general:${t.topic_id}`,
        title: t.title,
        meta: 'General Vocabulary & Grammar Practice',
        badge: '25 Qs',
      })),
    ];

    if (
      String(state.selectedUnitScope).startsWith('general:') &&
      !generalItems.some((it) => it.scope === state.selectedUnitScope)
    ) {
      const customName = String(state.selectedUnitScope).slice(8);
      generalItems.push({
        scope: state.selectedUnitScope,
        title: `Custom: ${customName}`,
        meta: 'Custom General Topic (Vocab & Grammar)',
        badge: '25 Qs',
      });
    }

    generalContainer.innerHTML = generalItems
      .map(
        (it) => `
        <button class="unit-scope-btn ${state.selectedUnitScope === it.scope ? 'active' : ''}" data-scope="${escapeHtml(it.scope)}">
          <div class="unit-scope-title">
            <span>${escapeHtml(it.title)}</span>
            <span class="pill pill-subtle">${escapeHtml(it.badge)}</span>
          </div>
          <div class="unit-scope-meta">${escapeHtml(it.meta)}</div>
        </button>
      `
      )
      .join('');

    generalContainer.querySelectorAll('.unit-scope-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const scope = btn.getAttribute('data-scope');
        state.selectedUnitScope = scope;
        state.activeUnitFilter = 'all';
        renderUnitScopeSidebar();
        loadDailySet(state.selectedDate, state.selectedUnitScope);
      });
    });
  }

  const container = document.getElementById('unit-scope-list');
  const items = [
    {
      scope: 'all',
      title: 'All Units (Daily 25 Mix)',
      meta: '25 questions categorized across units',
      badge: '25 Qs',
    },
    ...state.units.map((u) => ({
      scope: String(u.unit_id),
      title: u.display_name,
      meta: `${u.lesson_count} Lessons ${u.has_markdown_files ? '• .md Notes' : '• Study Guide'}`,
      badge: '25 Qs',
    })),
  ];

  container.innerHTML = items
    .map(
      (it) => `
      <button class="unit-scope-btn ${state.selectedUnitScope === it.scope ? 'active' : ''}" data-scope="${escapeHtml(it.scope)}">
        <div class="unit-scope-title">
          <span>${escapeHtml(it.title)}</span>
          <span class="pill pill-subtle">${escapeHtml(it.badge)}</span>
        </div>
        <div class="unit-scope-meta">${escapeHtml(it.meta)}</div>
      </button>
    `
    )
    .join('');

  container.querySelectorAll('.unit-scope-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const scope = btn.getAttribute('data-scope');
      state.selectedUnitScope = scope;
      state.activeUnitFilter = 'all';
      renderUnitScopeSidebar();
      loadDailySet(state.selectedDate, state.selectedUnitScope);
    });
  });
}

async function loadDailySet(dateStr, unitScope) {
  showLoading(
    `Loading Daily 25 Questions (${dateStr})...`,
    `Using LLM model "${state.config?.model_name || 'from .env'}" to prepare multi-turn conversations & reading passages.`
  );
  try {
    const url = `/api/daily?date_str=${encodeURIComponent(dateStr)}&unit_scope=${encodeURIComponent(unitScope)}&auto_generate=true`;
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.daily_set) {
      setActiveDailySet(data.daily_set);
    }
  } catch (err) {
    console.error('Error loading daily set:', err);
  } finally {
    hideLoading();
  }
}

async function generateNewDailySet(dateStr, unitScope) {
  showLoading(
    `Generating 25 Brand-New Questions for ${dateStr}...`,
    `Creating 5 fresh multi-turn conversations & reading passages with ${state.config?.model_name || '.env model'}.`
  );
  try {
    const resp = await fetch('/api/daily/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date_str: dateStr, unit_scope: unitScope }),
    });
    const data = await resp.json();
    if (data.daily_set) {
      state.draftAnswers = {};
      setActiveDailySet(data.daily_set);
      loadHistory();
    }
  } catch (err) {
    console.error('Error generating new daily set:', err);
  } finally {
    hideLoading();
  }
}

function setActiveDailySet(dailySet) {
  state.currentSet = dailySet;
  // Populate draftAnswers from existing submissions if not already edited
  (dailySet.contexts || []).forEach((ctx) => {
    (ctx.questions || []).forEach((q) => {
      if (q.submission && q.submission.user_answer && state.draftAnswers[q.question_number] === undefined) {
        state.draftAnswers[q.question_number] = q.submission.user_answer;
      }
    });
  });

  updateSidebarProgress();
  renderContextJumpBar();
  renderContexts();
  renderCurrentSetAnalytics();
}

function updateSidebarProgress() {
  const ds = state.currentSet;
  if (!ds) return;
  document.getElementById('set-date-badge').textContent = ds.date_str;
  document.getElementById('kpi-answered').textContent = `${ds.answered_count || 0} / ${ds.total_questions || 25}`;
  document.getElementById('kpi-avg-score').textContent =
    ds.average_score !== null && ds.average_score !== undefined ? `${ds.average_score} / 100` : '—';

  const pct = Math.min(100, Math.round(((ds.answered_count || 0) / (ds.total_questions || 25)) * 100));
  document.getElementById('daily-progress-bar').style.width = `${pct}%`;

  const scopeLabel = formatScopeLabel(ds.unit_scope);

  document.getElementById('current-set-heading').textContent = `${scopeLabel} — ${ds.date_str}`;
  document.getElementById('current-set-subheading').textContent =
    `Generated by ${ds.model_name} • ${ds.total_questions} Fill-in-the-Blank Questions across ${(ds.contexts || []).length} Contexts`;

  const miniEl = document.getElementById('unit-breakdown-mini');
  const breakdown = ds.unit_breakdown || [];
  miniEl.innerHTML = breakdown
    .map(
      (u) => `
      <div class="mini-unit-row">
        <span>${escapeHtml(u.unit_name)}</span>
        <strong>${u.answered_questions}/${u.total_questions} ${u.average_score !== null ? `(${u.average_score}/100)` : ''}</strong>
      </div>
    `
    )
    .join('');
}

function renderContextJumpBar() {
  const ds = state.currentSet;
  const bar = document.getElementById('context-jump-bar');
  if (!ds || !ds.contexts) {
    bar.innerHTML = '';
    return;
  }

  // Build unit filter pills so the user can filter questions by Unit category
  const unitMap = new Map();
  ds.contexts.forEach((ctx) => {
    unitMap.set(String(ctx.unit_id), ctx.unit_name);
  });

  const pills = [
    `<button class="jump-pill ${state.activeUnitFilter === 'all' ? 'active' : ''}" data-unit-filter="all">
      All Contexts (25 Questions)
    </button>`,
  ];

  unitMap.forEach((uName, uId) => {
    const count = ds.contexts
      .filter((c) => String(c.unit_id) === uId)
      .reduce((acc, c) => acc + (c.questions?.length || 0), 0);
    pills.push(`
      <button class="jump-pill ${state.activeUnitFilter === uId ? 'active' : ''}" data-unit-filter="${escapeHtml(uId)}">
        ${escapeHtml(uName)} (${count} Qs)
      </button>
    `);
  });

  bar.innerHTML = pills.join('');
  bar.querySelectorAll('.jump-pill').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.activeUnitFilter = btn.getAttribute('data-unit-filter');
      renderContextJumpBar();
      renderContexts();
    });
  });
}

function renderInlineBlanksInText(text, questionsMap, isConversation = false) {
  const escaped = escapeHtml(text);
  return escaped.replace(/___\((\d+)\)___/g, (_, numStr) => {
    const qnum = parseInt(numStr, 10);
    const val = state.draftAnswers[qnum] !== undefined ? state.draftAnswers[qnum] : '';
    const q = questionsMap[qnum];
    const isSentence = isConversation || (q && q.answer_format === 'sentence');
    const placeholder = isSentence
      ? `Write a complete sentence (#${qnum})...`
      : q
      ? `${q.category}...`
      : `Blank #${qnum}...`;
    return `<span class="inline-blank-wrap ${isSentence ? 'inline-sentence-wrap' : ''}" title="${escapeHtml(q ? q.clue : '')}">
      <span class="inline-blank-num">#${qnum}</span>
      <input
        type="text"
        class="inline-blank-input ${isSentence ? 'inline-sentence-input' : ''}"
        data-qnum="${qnum}"
        value="${escapeHtml(val)}"
        placeholder="${escapeHtml(placeholder)}"
        autocomplete="off"
      />
    </span>`;
  });
}

function renderContexts() {
  const container = document.getElementById('contexts-container');
  const ds = state.currentSet;
  if (!ds || !ds.contexts) {
    container.innerHTML = '<p class="text-muted">No questions loaded.</p>';
    return;
  }

  const questionsMap = {};
  ds.contexts.forEach((ctx) => {
    (ctx.questions || []).forEach((q) => {
      questionsMap[q.question_number] = q;
    });
  });

  const filteredContexts =
    state.activeUnitFilter === 'all'
      ? ds.contexts
      : ds.contexts.filter((c) => String(c.unit_id) === String(state.activeUnitFilter));

  container.innerHTML = filteredContexts
    .map((ctx) => {
      const isConversation = ctx.context_type === 'conversation';
      const qNums = (ctx.questions || []).map((q) => q.question_number);
      const qRange = qNums.length ? `Questions #${qNums[0]}–#${qNums[qNums.length - 1]}` : '';

      let readingHtml = '';
      if (isConversation && ctx.turns && ctx.turns.length > 0) {
        readingHtml = `
          <div class="panel-section-label">💬 Multi-Turn Conversation — Complete-Sentence Blanks (${escapeHtml(qRange)})</div>
          <div class="dialogue-list">
            ${ctx.turns
              .map(
                (t) => `
              <div class="dialogue-turn">
                <div class="speaker-tag">
                  <span>[${escapeHtml(t.speaker)}]</span>
                  ${t.role ? `<span class="speaker-role">• ${escapeHtml(t.role)}</span>` : ''}
                </div>
                <div class="turn-text">${renderInlineBlanksInText(t.text, questionsMap, true)}</div>
              </div>
            `
              )
              .join('')}
          </div>
        `;
      } else {
        const paragraphs =
          ctx.passage_paragraphs && ctx.passage_paragraphs.length > 0
            ? ctx.passage_paragraphs
            : (ctx.content_text || '').split(/\n\n+/);
        readingHtml = `
          <div class="panel-section-label">📄 Reading Passage (${escapeHtml(qRange)})</div>
          <div class="passage-body">
            ${paragraphs.map((p) => `<p>${renderInlineBlanksInText(p, questionsMap, false)}</p>`).join('')}
          </div>
        `;
      }

      const questionsHtml = (ctx.questions || [])
        .map((q) => {
          const qnum = q.question_number;
          const isSentence = isConversation || q.answer_format === 'sentence';
          const draftVal = state.draftAnswers[qnum] !== undefined ? state.draftAnswers[qnum] : '';
          const sub = q.submission;
          let feedbackHtml = '';
          if (sub) {
            const sClass = scoreColorClass(sub.score);
            feedbackHtml = `
              <div class="q-feedback-box" id="feedback-box-${qnum}">
                <div class="score-header">
                  <span class="score-pill ${sClass}">Score: ${sub.score} / 100 (${escapeHtml(sub.verdict)})</span>
                  <span class="text-muted">Graded by ${escapeHtml(sub.graded_by_model)}</span>
                </div>
                <p class="feedback-detail">${escapeHtml(sub.detailed_feedback)}</p>
                <div class="feedback-meta-list">
                  <div><strong>Grammar &amp; Vocab Rule:</strong> ${escapeHtml(sub.grammar_vocab_analysis)}</div>
                  <div><strong>Ideal Answer:</strong> <code>${escapeHtml(sub.ideal_answer)}</code></div>
                  ${sub.example_usage ? `<div><strong>Example:</strong> <em>${escapeHtml(sub.example_usage)}</em></div>` : ''}
                </div>
              </div>
            `;
          }

          return `
            <div class="question-card" id="q-card-${qnum}">
              <div class="q-top-row">
                <span class="q-num-badge">Question #${qnum}</span>
                <div>
                  <span class="q-format-badge ${isSentence ? 'format-sentence' : 'format-word'}">${isSentence ? '✍️ Complete Sentence' : '🔤 Word / Phrase'}</span>
                  <span class="q-cat-badge">${escapeHtml(q.category)}</span>
                  <span class="pill pill-subtle">${escapeHtml(q.unit_name)}</span>
                </div>
              </div>
              <div class="q-clue">
                <strong>Clue:</strong> ${escapeHtml(q.clue)}
              </div>
              <div class="q-input-row">
                <input
                  type="text"
                  class="q-blank-input ${isSentence ? 'q-sentence-input' : ''}"
                  id="q-input-${qnum}"
                  data-qnum="${qnum}"
                  value="${escapeHtml(draftVal)}"
                  placeholder="${isSentence ? `Write a complete sentence for Blank #${qnum}...` : `Type your fill-in-the-blank answer for #${qnum}...`}"
                  autocomplete="off"
                />
                <button class="btn btn-secondary btn-sm btn-hint" data-qnum="${qnum}" type="button">
                  💡 Hint
                </button>
                <button class="btn btn-primary btn-sm btn-grade-single" data-qnum="${qnum}" type="button">
                  Grade
                </button>
              </div>
              <div class="q-hint-box hidden" id="q-hint-${qnum}">
                <strong>Hint:</strong> ${escapeHtml(q.hint)}
              </div>
              ${feedbackHtml}
            </div>
          `;
        })
        .join('');

      return `
        <article class="context-card" id="context-card-${escapeHtml(ctx.context_id)}">
          <div class="context-header">
            <div>
              <div class="context-badges">
                <span class="badge-unit">${escapeHtml(ctx.unit_name)}</span>
                <span class="badge-lesson">${escapeHtml(ctx.lesson_name)}</span>
                <span class="badge-type">${isConversation ? 'Multi-Turn Conversation' : 'Reading Passage'}</span>
                <span class="pill pill-subtle">${escapeHtml(qRange)}</span>
              </div>
              <h3 class="context-title">${escapeHtml(ctx.title)}</h3>
              <p class="context-scenario">${escapeHtml(ctx.scenario_description)}</p>
            </div>
            <div>
              <button class="btn btn-accent btn-grade-context" data-context-id="${escapeHtml(ctx.context_id)}">
                ✨ Grade Context (${(ctx.questions || []).length} Qs)
              </button>
            </div>
          </div>

          <div class="context-body-grid">
            <div class="context-reading-panel">
              ${readingHtml}
            </div>
            <div class="questions-list">
              ${questionsHtml}
            </div>
          </div>
        </article>
      `;
    })
    .join('');

  bindQuestionInputs();
}

function bindQuestionInputs() {
  // Sync inline inputs and card inputs two-way
  document.querySelectorAll('.inline-blank-input, .q-blank-input').forEach((input) => {
    input.addEventListener('input', (e) => {
      const qnum = parseInt(e.target.getAttribute('data-qnum'), 10);
      const val = e.target.value;
      state.draftAnswers[qnum] = val;
      document
        .querySelectorAll(`.inline-blank-input[data-qnum="${qnum}"], .q-blank-input[data-qnum="${qnum}"]`)
        .forEach((peer) => {
          if (peer !== e.target) {
            peer.value = val;
          }
        });
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const qnum = parseInt(e.target.getAttribute('data-qnum'), 10);
        gradeQuestionsSubset([qnum]);
      }
    });
  });

  // Hint buttons
  document.querySelectorAll('.btn-hint').forEach((btn) => {
    btn.addEventListener('click', () => {
      const qnum = btn.getAttribute('data-qnum');
      const hintEl = document.getElementById(`q-hint-${qnum}`);
      if (hintEl) {
        hintEl.classList.toggle('hidden');
      }
    });
  });

  // Single question grade buttons
  document.querySelectorAll('.btn-grade-single').forEach((btn) => {
    btn.addEventListener('click', () => {
      const qnum = parseInt(btn.getAttribute('data-qnum'), 10);
      gradeQuestionsSubset([qnum]);
    });
  });

  // Context grade buttons
  document.querySelectorAll('.btn-grade-context').forEach((btn) => {
    btn.addEventListener('click', () => {
      const ctxId = btn.getAttribute('data-context-id');
      const ctx = (state.currentSet?.contexts || []).find((c) => c.context_id === ctxId);
      if (ctx && ctx.questions) {
        const qnums = ctx.questions.map((q) => q.question_number);
        gradeQuestionsSubset(qnums);
      }
    });
  });
}

async function gradeQuestionsSubset(questionNumbers) {
  if (!state.currentSet) return;
  const payloadAnswers = {};
  questionNumbers.forEach((qnum) => {
    payloadAnswers[String(qnum)] = (state.draftAnswers[qnum] || '').trim();
  });

  showLoading(
    `Grading ${questionNumbers.length} Answer(s) on a 1-100 Scale...`,
    `Analyzing context, grammar, and unit vocabulary with ${state.config?.model_name || '.env LLM'}.`
  );
  try {
    const resp = await fetch('/api/grade', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        set_id: state.currentSet.set_id,
        answers: payloadAnswers,
      }),
    });
    const data = await resp.json();
    if (data.daily_set) {
      setActiveDailySet(data.daily_set);
    }
    if (data.grading_result) {
      const banner = document.getElementById('overall-feedback-banner');
      banner.classList.remove('hidden');
      banner.innerHTML = `
        <strong>🎯 LLM Grading Complete (${escapeHtml(data.grading_result.model_name)}) — Batch Avg Score: ${data.grading_result.average_score} / 100</strong>
        <p>${escapeHtml(data.grading_result.overall_feedback)}</p>
      `;
    }
  } catch (err) {
    console.error('Grading failed:', err);
  } finally {
    hideLoading();
  }
}

async function gradeAllAnswered() {
  if (!state.currentSet) return;
  const allQnums = [];
  (state.currentSet.contexts || []).forEach((ctx) => {
    (ctx.questions || []).forEach((q) => {
      const val = (state.draftAnswers[q.question_number] || '').trim();
      if (val.length > 0) {
        allQnums.push(q.question_number);
      }
    });
  });

  if (allQnums.length === 0) {
    // If nothing typed yet, grade the first context so the user gets immediate feedback
    const firstCtx = state.currentSet.contexts?.[0];
    if (firstCtx && firstCtx.questions) {
      await gradeQuestionsSubset(firstCtx.questions.map((q) => q.question_number));
    }
    return;
  }
  await gradeQuestionsSubset(allQnums);
}

// STUDY GUIDES TAB
function renderStudyUnitSelector() {
  const container = document.getElementById('study-unit-selector');
  const studyItems = [
    ...state.units.map((u) => ({
      unit_id: u.unit_id,
      display_name: u.display_name,
    })),
    {
      unit_id: 'general',
      display_name: '🌟 General Topics (Vocab & Grammar)',
    },
  ];
  container.innerHTML = studyItems
    .map(
      (u, idx) => `
      <button class="btn btn-secondary study-unit-btn ${idx === 0 ? 'btn-primary' : ''}" data-unit-id="${escapeHtml(u.unit_id)}">
        ${escapeHtml(u.display_name)}
      </button>
    `
    )
    .join('');

  container.querySelectorAll('.study-unit-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.study-unit-btn').forEach((b) => b.classList.remove('btn-primary'));
      btn.classList.add('btn-primary');
      loadStudyGuide(btn.getAttribute('data-unit-id'));
    });
  });
}

function simpleMarkdownToHtml(md) {
  const lines = (md || '').split(/\r?\n/);
  let html = '';
  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (trimmed.startsWith('#### ')) {
      html += `<h4>${escapeHtml(trimmed.slice(5))}</h4>`;
    } else if (trimmed.startsWith('### ')) {
      html += `<h4>${escapeHtml(trimmed.slice(4))}</h4>`;
    } else if (trimmed.startsWith('## ')) {
      html += `<h4>${escapeHtml(trimmed.slice(3))}</h4>`;
    } else if (trimmed.startsWith('# ')) {
      return;
    } else if (trimmed.startsWith('> ')) {
      html += `<blockquote>${formatInlineMd(trimmed.slice(2))}</blockquote>`;
    } else if (trimmed.startsWith('- ') || /^\d+\.\s+/.test(trimmed)) {
      html += `<p>• ${formatInlineMd(trimmed.replace(/^(-|\d+\.)\s+/, ''))}</p>`;
    } else {
      html += `<p>${formatInlineMd(trimmed)}</p>`;
    }
  });
  return html;
}

function formatInlineMd(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

async function loadStudyGuide(unitId) {
  const container = document.getElementById('study-guide-content');
  try {
    const resp = await fetch(`/api/units/${encodeURIComponent(unitId)}`);
    const unit = await resp.json();
    container.innerHTML = (unit.lessons || [])
      .map(
        (lesson) => `
        <div class="lesson-study-card">
          <div class="card-header-row">
            <h3>Lesson ${lesson.lesson_number}: ${escapeHtml(lesson.title)}</h3>
            <span class="pill ${lesson.has_markdown_file ? 'pill-info' : 'pill-subtle'}">
              ${unit.unit_id === 'general' ? 'General Vocab & Grammar Guide' : lesson.has_markdown_file ? 'Loaded from Level/ .md file' : 'Curriculum Study Guide'}
            </span>
          </div>
          <div class="markdown-rendered">
            ${simpleMarkdownToHtml(lesson.content_md)}
          </div>
        </div>
      `
      )
      .join('');
  } catch (err) {
    container.innerHTML = '<p class="text-muted">Failed to load unit study guide.</p>';
  }
}

// ANALYTICS & HISTORY TAB
function renderCurrentSetAnalytics() {
  const ds = state.currentSet;
  if (!ds) return;

  const unitBarsEl = document.getElementById('analytics-unit-bars');
  unitBarsEl.innerHTML = (ds.unit_breakdown || [])
    .map((u) => {
      const avg = u.average_score !== null ? u.average_score : 0;
      return `
        <div class="bar-row">
          <div class="bar-label-line">
            <strong>${escapeHtml(u.unit_name)}</strong>
            <span>${u.answered_questions}/${u.total_questions} Answered • Avg: ${u.average_score !== null ? `${u.average_score}/100` : '—'}</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${avg}%"></div>
          </div>
        </div>
      `;
    })
    .join('');

  const catBarsEl = document.getElementById('analytics-category-bars');
  catBarsEl.innerHTML = (ds.category_breakdown || [])
    .map((c) => {
      const avg = c.average_score !== null ? c.average_score : 0;
      return `
        <div class="bar-row">
          <div class="bar-label-line">
            <strong>${escapeHtml(c.category)}</strong>
            <span>${c.answered_questions}/${c.total_questions} Answered • Avg: ${c.average_score !== null ? `${c.average_score}/100` : '—'}</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${avg}%"></div>
          </div>
        </div>
      `;
    })
    .join('');
}

async function loadHistory() {
  const wrapper = document.getElementById('history-table-wrapper');
  try {
    const resp = await fetch('/api/history');
    const data = await resp.json();
    const list = data.history || [];
    if (list.length === 0) {
      wrapper.innerHTML = '<p class="text-muted">No daily sets generated yet.</p>';
      return;
    }

    wrapper.innerHTML = `
      <table class="history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Unit / Topic Scope</th>
            <th>Model (.env)</th>
            <th>Questions Graded</th>
            <th>Avg Score (1-100)</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          ${list
            .map(
              (item) => `
            <tr>
              <td><strong>${escapeHtml(item.date_str)}</strong></td>
              <td>${escapeHtml(formatScopeLabel(item.unit_scope))}</td>
              <td><code>${escapeHtml(item.model_name)}</code></td>
              <td>${item.answered_count} / ${item.total_questions}</td>
              <td><strong>${item.average_score !== null ? `${item.average_score} / 100` : '—'}</strong></td>
              <td>
                <button class="btn btn-secondary btn-sm btn-open-set" data-set-id="${item.set_id}">
                  Open Set
                </button>
              </td>
            </tr>
          `
            )
            .join('')}
        </tbody>
      </table>
    `;

    wrapper.querySelectorAll('.btn-open-set').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const setId = btn.getAttribute('data-set-id');
        const r = await fetch(`/api/daily/${setId}`).then((res) => res.json());
        if (r.daily_set) {
          state.selectedDate = r.daily_set.date_str;
          state.selectedUnitScope = r.daily_set.unit_scope;
          document.getElementById('daily-date-picker').value = state.selectedDate;
          renderUnitScopeSidebar();
          setActiveDailySet(r.daily_set);
          document.getElementById('tab-btn-practice').click();
        }
      });
    });
  } catch (err) {
    wrapper.innerHTML = '<p class="text-muted">Failed to load history.</p>';
  }
}

document.addEventListener('DOMContentLoaded', initApp);
