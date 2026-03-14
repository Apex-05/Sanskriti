(function () {
    'use strict';

    const appElement = document.getElementById('quizApp');
    if (!appElement) {
        return;
    }

    if (!window.React || !window.ReactDOM || typeof window.ReactDOM.createRoot !== 'function') {
        appElement.innerHTML = '<div class="quiz-result">Quiz UI could not start because React failed to load.</div>';
        return;
    }

    const { useCallback, useEffect, useMemo, useRef, useState } = window.React;
    const h = window.React.createElement;

    function readJsonScript(scriptId, fallbackValue) {
        const node = document.getElementById(scriptId);
        if (!node || !node.textContent) {
            return fallbackValue;
        }

        try {
            return JSON.parse(node.textContent);
        } catch (error) {
            return fallbackValue;
        }
    }

    function getCsrfToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find((cookie) => cookie.startsWith('csrftoken='));

        return cookieValue ? decodeURIComponent(cookieValue.split('=')[1]) : '';
    }

    function formatCategoryLabel(value) {
        return String(value || '')
            .split('_')
            .filter(Boolean)
            .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
            .join(' ');
    }

    function formatTimer(totalSeconds) {
        const safeSeconds = Number.isFinite(totalSeconds) ? Math.max(totalSeconds, 0) : 0;
        const minutes = Math.floor(safeSeconds / 60);
        const seconds = safeSeconds % 60;
        return `Time Left ${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function normalizePayload(payload) {
        const safePayload = payload && typeof payload === 'object' ? payload : {};

        return {
            mode: safePayload.mode || 'practice',
            mode_label: safePayload.mode_label || 'Practice Quiz',
            description: safePayload.description || '',
            features: Array.isArray(safePayload.features) ? safePayload.features : [],
            has_timer: Boolean(safePayload.has_timer),
            duration_seconds: Number(safePayload.duration_seconds || 0),
            instant_feedback: Boolean(safePayload.instant_feedback),
            can_reset: Boolean(safePayload.can_reset),
            submit_url: safePayload.submit_url || '',
            selected_category: safePayload.selected_category || '',
            questions: Array.isArray(safePayload.questions) ? safePayload.questions : [],
            daily_locked: Boolean(safePayload.daily_locked),
            daily_result: safePayload.daily_result || null,
            leaderboard: Array.isArray(safePayload.leaderboard) ? safePayload.leaderboard : [],
        };
    }

    function buildSummary(questions, answersByQuestion) {
        const totalQuestions = questions.length;
        let correctAnswers = 0;

        questions.forEach((question, index) => {
            if (answersByQuestion[index] && answersByQuestion[index] === question.correct_answer) {
                correctAnswers += 1;
            }
        });

        const incorrectAnswers = Math.max(totalQuestions - correctAnswers, 0);
        const percentage = totalQuestions ? Math.round((correctAnswers / totalQuestions) * 100) : 0;

        return {
            score: correctAnswers,
            total_questions: totalQuestions,
            correct_answers: correctAnswers,
            incorrect_answers: incorrectAnswers,
            percentage,
        };
    }

    function LeaderboardSection({ entries }) {
        const hasEntries = Array.isArray(entries) && entries.length > 0;

        return h('div', { className: 'section-panel mb-4' }, [
            h('span', { className: 'section-label', key: 'label' }, 'Leaderboard'),
            h('h2', { className: 'h4 mb-3', key: 'title' }, 'Top 10 quiz performers (last 24 hours)'),
            h(
                'div',
                { className: 'row g-3', key: 'rows' },
                hasEntries
                    ? entries.map((entry, index) => h('div', { className: 'col-12 col-md-6 col-xl-4', key: `${entry.username || 'user'}-${index}` }, [
                        h('div', { className: 'quiz-result h-100' }, [
                            h('div', { className: 'd-flex justify-content-between align-items-start gap-2' }, [
                                h('div', { key: 'left' }, [
                                    h('strong', { key: 'name' }, `#${index + 1} ${entry.username || 'Anonymous'}`),
                                    h('div', { className: 'small text-muted', key: 'mode' }, entry.mode_label || entry.mode || ''),
                                ]),
                                h('span', { className: 'resource-badge mb-0', key: 'percentage' }, `${entry.percentage || 0}%`),
                            ]),
                            h(
                                'p',
                                { className: 'mt-2 mb-0' },
                                `Score ${entry.score || 0}/${entry.total_questions || 0} on ${entry.played_on || ''}`
                            ),
                        ]),
                    ]))
                    : [
                        h('div', { className: 'col-12', key: 'empty' }, [
                            h('div', { className: 'quiz-result' }, 'No quiz attempts recorded in the last 24 hours yet.'),
                        ]),
                    ]
            ),
        ]);
    }

    function StatsRow({ stats }) {
        return h('div', { className: 'learn-stats-wrap mb-4' }, [
            h(
                'div',
                { className: 'learn-stats-row', key: 'row' },
                stats.map((stat) => h('div', { className: 'section-stat-chip section-stat-chip--soft', key: stat.label }, [
                    h('strong', { key: 'value' }, String(stat.value)),
                    h('span', { key: 'label' }, stat.label),
                ]))
            ),
        ]);
    }

    function QuizModes({
        modes,
        currentMode,
        onModeChange,
        modeLabel,
        description,
        features,
        categoryChoices,
        selectedCategory,
        onCategoryChange,
        onApplyFilter,
        isLoading,
    }) {
        return h('div', { className: 'section-panel mb-4 learn-mode-panel' }, [
            h('span', { className: 'section-label', key: 'label' }, 'Quiz Modes'),
            h('h2', { className: 'h4 mb-3', key: 'title' }, 'Choose how you want to learn'),
            h(
                'div',
                { className: 'd-flex flex-wrap gap-2 mb-4', key: 'buttons' },
                modes.map((mode) => {
                    const isActive = currentMode === mode.key;
                    const className = `btn ${isActive ? 'dashboard-btn' : 'btn-outline-secondary'}`;
                    return h(
                        'button',
                        {
                            type: 'button',
                            className,
                            onClick: () => onModeChange(mode.key),
                            disabled: isLoading,
                            key: mode.key,
                        },
                        mode.label
                    );
                })
            ),
            h('div', { className: 'row g-4 align-items-end', key: 'details' }, [
                h('div', { className: 'col-lg-8', key: 'description' }, [
                    h('span', { className: 'section-label', key: 'mode-label' }, modeLabel),
                    h('p', { className: 'section-subcopy mb-3', key: 'mode-description' }, description),
                    h(
                        'div',
                        { className: 'feature-pill-list', key: 'features' },
                        features.length
                            ? features.map((feature, index) => h('span', { className: 'feature-pill', key: `${feature}-${index}` }, [
                                h('i', { className: 'bi bi-check2-circle', 'aria-hidden': 'true', key: 'icon' }),
                                feature,
                            ]))
                            : [h('span', { className: 'feature-pill', key: 'empty' }, 'No features available for this mode yet.')]
                    ),
                ]),
                h('div', { className: 'col-lg-4', key: 'filter' }, [
                    h(
                        'form',
                        {
                            className: 'learn-mode-filter',
                            onSubmit: (event) => {
                                event.preventDefault();
                                onApplyFilter();
                            },
                            key: 'filter-form',
                        },
                        [
                            h('label', { htmlFor: 'quizCategory', className: 'form-label fw-semibold mb-1', key: 'filter-label' }, 'Category'),
                            h('div', { className: 'd-flex gap-2', key: 'filter-controls' }, [
                                h(
                                    'select',
                                    {
                                        id: 'quizCategory',
                                        className: 'form-select',
                                        value: selectedCategory,
                                        onChange: (event) => onCategoryChange(event.target.value),
                                        disabled: isLoading,
                                        key: 'filter-select',
                                    },
                                    [
                                        h('option', { value: '', key: 'all' }, 'All categories'),
                                        ...categoryChoices.map((choice) => h('option', { value: choice.value, key: choice.value }, choice.label)),
                                    ]
                                ),
                                h(
                                    'button',
                                    {
                                        type: 'submit',
                                        className: 'btn dashboard-btn',
                                        disabled: isLoading,
                                        key: 'filter-button',
                                    },
                                    'Apply'
                                ),
                            ]),
                        ]
                    ),
                ]),
            ]),
        ]);
    }

    function QuizCard({
        question,
        questionNumber,
        totalQuestions,
        selectedAnswer,
        onSelectAnswer,
        isPracticeMode,
        practiceGrade,
        isBusy,
        showNextButton,
        nextButtonLabel,
        onNextQuestion,
    }) {
        const options = [
            { key: 'a', text: question.option_a },
            { key: 'b', text: question.option_b },
            { key: 'c', text: question.option_c },
            { key: 'd', text: question.option_d },
        ];

        const tagsText = Array.isArray(question.tags) && question.tags.length ? question.tags.join(', ') : '';
        const isAnswerLocked = isBusy || (isPracticeMode && Boolean(practiceGrade));

        let feedbackText = '';
        let feedbackClass = 'quiz-feedback mb-0';

        if (isPracticeMode && practiceGrade) {
            if (practiceGrade.isCorrect) {
                feedbackText = practiceGrade.explanation
                    ? `Correct. ${practiceGrade.explanation}`
                    : 'Correct.';
                feedbackClass = 'quiz-feedback is-positive mb-0';
            } else {
                const correctOption = options.find((option) => option.key === practiceGrade.correctAnswer);
                const correctText = correctOption ? correctOption.text : 'Review the correct option.';
                feedbackText = practiceGrade.explanation
                    ? `Incorrect. Correct answer: ${correctText}. ${practiceGrade.explanation}`
                    : `Incorrect. Correct answer: ${correctText}.`;
                feedbackClass = 'quiz-feedback is-negative mb-0';
            }
        }

        return h('div', { className: 'learn-quiz-card section-panel' }, [
            h('div', { className: 'learn-question-head', key: 'head' }, [
                h('span', { className: 'section-label', key: 'counter' }, `Question ${questionNumber} of ${totalQuestions}`),
                h('span', { className: 'section-chip', key: 'category' }, formatCategoryLabel(question.category) || 'General'),
            ]),
            h('p', { className: 'quiz-question-title learn-question-title', key: 'question-title' }, question.question_text),
            tagsText
                ? h('p', { className: 'text-muted small mb-3', key: 'tags' }, `Tags: ${tagsText}`)
                : null,
            h(
                'div',
                { className: 'learn-quiz-options', key: 'options' },
                options.map((option) => {
                    let className = 'quiz-option';
                    if (isPracticeMode && practiceGrade) {
                        if (option.key === practiceGrade.correctAnswer) {
                            className += ' is-answer';
                        }
                        if (!practiceGrade.isCorrect && option.key === practiceGrade.selected) {
                            className += ' is-selected-wrong';
                        }
                    }
                    if (isAnswerLocked) {
                        className += ' is-disabled';
                    }

                    return h('label', { className, key: option.key }, [
                        h('input', {
                            type: 'radio',
                            name: `quiz-option-${questionNumber}`,
                            value: option.key,
                            checked: selectedAnswer === option.key,
                            onChange: () => onSelectAnswer(option.key),
                            disabled: isAnswerLocked,
                            key: `input-${option.key}`,
                        }),
                        option.text,
                    ]);
                })
            ),
            h('p', { className: feedbackClass, key: 'feedback' }, feedbackText),
            showNextButton
                ? h('div', { className: 'learn-quiz-actions', key: 'actions' }, [
                    h(
                        'button',
                        {
                            type: 'button',
                            className: 'btn dashboard-btn',
                            onClick: onNextQuestion,
                            disabled: isBusy,
                        },
                        nextButtonLabel
                    ),
                ])
                : null,
        ]);
    }

    function QuizCompletionCard({ summary, message, showRestart, onRestart, isSavingDaily }) {
        if (!summary) {
            return null;
        }

        return h('div', { className: 'learn-quiz-card section-panel learn-completion-card' }, [
            h('span', { className: 'section-label', key: 'label' }, 'Quiz Completed'),
            h('h3', { className: 'h4 mt-2 mb-2', key: 'title' }, `Score ${summary.score} / ${summary.total_questions}`),
            message
                ? h('p', { className: 'section-subcopy mb-3', key: 'message' }, message)
                : null,
            isSavingDaily
                ? h('p', { className: 'section-subcopy mb-3', key: 'saving' }, 'Saving daily challenge result...')
                : null,
            h('div', { className: 'row g-3', key: 'summary-grid' }, [
                h('div', { className: 'col-6 col-md-3', key: 'score' }, [
                    h('strong', { key: 'score-label' }, 'Score'),
                    h('div', { key: 'score-value' }, `${summary.score} / ${summary.total_questions}`),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'correct' }, [
                    h('strong', { key: 'correct-label' }, 'Correct'),
                    h('div', { key: 'correct-value' }, String(summary.correct_answers)),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'incorrect' }, [
                    h('strong', { key: 'incorrect-label' }, 'Incorrect'),
                    h('div', { key: 'incorrect-value' }, String(summary.incorrect_answers)),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'accuracy' }, [
                    h('strong', { key: 'accuracy-label' }, 'Accuracy'),
                    h('div', { key: 'accuracy-value' }, `${summary.percentage}%`),
                ]),
            ]),
            showRestart
                ? h('div', { className: 'learn-quiz-actions mt-3', key: 'restart' }, [
                    h(
                        'button',
                        {
                            type: 'button',
                            className: 'btn btn-outline-secondary',
                            onClick: onRestart,
                        },
                        'Restart Quiz'
                    ),
                ])
                : null,
        ]);
    }

    function DailyLockPanel({ summary }) {
        if (!summary) {
            return null;
        }

        return h('div', { className: 'quiz-result' }, [
            h('p', { className: 'fw-semibold mb-3', key: 'message' }, "You have already completed today's daily challenge."),
            h('div', { className: 'row g-3', key: 'summary-grid' }, [
                h('div', { className: 'col-6 col-md-3', key: 'score' }, [
                    h('strong', { key: 'score-label' }, 'Score'),
                    h('div', { key: 'score-value' }, `${summary.score} / ${summary.total_questions}`),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'correct' }, [
                    h('strong', { key: 'correct-label' }, 'Correct'),
                    h('div', { key: 'correct-value' }, String(summary.correct_answers)),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'incorrect' }, [
                    h('strong', { key: 'incorrect-label' }, 'Incorrect'),
                    h('div', { key: 'incorrect-value' }, String(summary.incorrect_answers)),
                ]),
                h('div', { className: 'col-6 col-md-3', key: 'accuracy' }, [
                    h('strong', { key: 'accuracy-label' }, 'Accuracy'),
                    h('div', { key: 'accuracy-value' }, `${summary.percentage}%`),
                ]),
            ]),
        ]);
    }

    function TimedQuizStartPanel({ durationSeconds, onStart, isBusy }) {
        const minutes = Math.floor(Number(durationSeconds || 0) / 60);

        return h('div', { className: 'quiz-result mb-0' }, [
            h('span', { className: 'section-label', key: 'label' }, 'Timed Quiz'),
            h('h3', { className: 'h5 mt-2 mb-2', key: 'title' }, 'Start when you are ready'),
            h(
                'p',
                { className: 'mb-3', key: 'description' },
                `Click Start Timed Quiz to begin. The timer starts immediately and auto-submits after ${minutes} minutes.`
            ),
            h(
                'button',
                {
                    type: 'button',
                    className: 'btn dashboard-btn',
                    onClick: onStart,
                    disabled: isBusy,
                    key: 'start',
                },
                'Start Timed Quiz'
            ),
        ]);
    }

    function QuizApp() {
        const modeUrls = {
            practice: appElement.dataset.practiceUrl || '',
            timed: appElement.dataset.timedUrl || '',
            daily: appElement.dataset.dailyUrl || '',
        };

        const stats = [
            { label: 'Quiz questions', value: Number(appElement.dataset.questionTotal || 0) },
            { label: 'Topic zones', value: Number(appElement.dataset.topicZoneCount || 0) },
            { label: 'Saved results', value: Number(appElement.dataset.savedResultCount || 0) },
        ];

        const quizModes = readJsonScript('quizModesPayload', []);
        const categoryChoicesPayload = readJsonScript('quizCategoryChoicesPayload', []);
        const categoryChoices = Array.isArray(categoryChoicesPayload)
            ? categoryChoicesPayload.map((choice) => ({
                value: choice[0],
                label: choice[1],
            }))
            : [];

        const initialPayload = normalizePayload(readJsonScript('initialQuizPayload', {}));

        const [quizPayload, setQuizPayload] = useState(initialPayload);
        const [leaderboardEntries, setLeaderboardEntries] = useState(initialPayload.leaderboard || []);
        const [dailyResultSummary, setDailyResultSummary] = useState(initialPayload.daily_result || null);
        const [selectedCategory, setSelectedCategory] = useState(initialPayload.selected_category || '');
        const [isLoading, setIsLoading] = useState(false);
        const [isSavingDaily, setIsSavingDaily] = useState(false);
        const [errorMessage, setErrorMessage] = useState('');

        const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
        const [selectedAnswer, setSelectedAnswer] = useState('');
        const [score, setScore] = useState(0);
        const [quizCompleted, setQuizCompleted] = useState(false);

        const [answersByQuestion, setAnswersByQuestion] = useState({});
        const [practiceGrades, setPracticeGrades] = useState({});
        const [completionSummary, setCompletionSummary] = useState(null);
        const [completionMessage, setCompletionMessage] = useState('');
        const [timeRemaining, setTimeRemaining] = useState(initialPayload.has_timer ? initialPayload.duration_seconds : 0);
        const [quizStarted, setQuizStarted] = useState(!initialPayload.has_timer);

        const didAutoSubmitRef = useRef(false);

        const resetQuizProgress = useCallback((payload) => {
            setCurrentQuestionIndex(0);
            setSelectedAnswer('');
            setScore(0);
            setQuizCompleted(false);
            setAnswersByQuestion({});
            setPracticeGrades({});
            setCompletionSummary(null);
            setCompletionMessage('');
            setErrorMessage('');
            setTimeRemaining(payload.has_timer ? Number(payload.duration_seconds || 0) : 0);
            setQuizStarted(!payload.has_timer);
            didAutoSubmitRef.current = false;
        }, []);

        const questions = useMemo(
            () => (Array.isArray(quizPayload.questions) ? quizPayload.questions : []),
            [quizPayload.questions]
        );

        const totalQuestions = questions.length;
        const currentQuestion = questions[currentQuestionIndex] || null;
        const currentPracticeGrade = practiceGrades[currentQuestionIndex] || null;
        const isPracticeMode = quizPayload.mode === 'practice';
        const isDailyMode = quizPayload.mode === 'daily';
        const timerText = formatTimer(timeRemaining);
        const timerWarning = timeRemaining <= 30;

        const showNextButton = Boolean(
            currentQuestion
            && (isPracticeMode ? currentPracticeGrade : selectedAnswer)
        );

        const nextButtonLabel = currentQuestionIndex >= totalQuestions - 1
            ? 'Finish Quiz'
            : 'Next Question \u2192';

        const saveDailyResult = useCallback(async (summary) => {
            if (!quizPayload.submit_url) {
                return;
            }

            setIsSavingDaily(true);

            try {
                const response = await window.fetch(quizPayload.submit_url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify(summary),
                });

                const responsePayload = await response.json().catch(() => ({}));

                if (responsePayload.leaderboard) {
                    setLeaderboardEntries(responsePayload.leaderboard);
                }

                if (responsePayload.result) {
                    setDailyResultSummary(responsePayload.result);
                    setCompletionSummary(responsePayload.result);
                    setScore(Number(responsePayload.result.score || 0));
                }

                if (!response.ok) {
                    setCompletionMessage(responsePayload.detail || 'Daily challenge score could not be saved.');
                    return;
                }

                setCompletionMessage(responsePayload.detail || 'Daily challenge score saved.');
            } catch (error) {
                setCompletionMessage('Score calculated locally, but saving the daily result failed.');
            } finally {
                setIsSavingDaily(false);
            }
        }, [quizPayload.submit_url]);

        const completeQuiz = useCallback((autoSubmitted) => {
            if (!questions.length) {
                return;
            }

            const summary = buildSummary(questions, answersByQuestion);
            setScore(summary.score);
            setQuizCompleted(true);
            setCompletionSummary(summary);
            setCompletionMessage(autoSubmitted ? 'Time ended, so the quiz was auto-submitted.' : '');

            if (isDailyMode && !quizPayload.daily_locked) {
                void saveDailyResult(summary);
            }
        }, [answersByQuestion, isDailyMode, questions, quizPayload.daily_locked, saveDailyResult]);

        useEffect(() => {
            setSelectedAnswer(answersByQuestion[currentQuestionIndex] || '');
        }, [answersByQuestion, currentQuestionIndex]);

        useEffect(() => {
            if (!quizPayload.has_timer || !quizStarted || quizCompleted || quizPayload.daily_locked || !totalQuestions) {
                return;
            }

            if (timeRemaining <= 0) {
                if (!didAutoSubmitRef.current) {
                    didAutoSubmitRef.current = true;
                    completeQuiz(true);
                }
                return;
            }

            const timeoutId = window.setTimeout(() => {
                setTimeRemaining((previous) => Math.max(previous - 1, 0));
            }, 1000);

            return () => {
                window.clearTimeout(timeoutId);
            };
        }, [completeQuiz, quizCompleted, quizPayload.daily_locked, quizPayload.has_timer, quizStarted, timeRemaining, totalQuestions]);

        const loadQuiz = useCallback(async (mode, category) => {
            const modeUrl = modeUrls[mode];
            if (!modeUrl || isLoading) {
                return;
            }

            setIsLoading(true);
            setErrorMessage('');

            try {
                const url = new URL(modeUrl, window.location.origin);
                if (category) {
                    url.searchParams.set('category', category);
                }

                const response = await window.fetch(url.toString(), {
                    headers: {
                        Accept: 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                if (!response.ok) {
                    throw new Error('Quiz questions could not be loaded.');
                }

                const loadedPayload = normalizePayload(await response.json());
                setQuizPayload(loadedPayload);
                setLeaderboardEntries(loadedPayload.leaderboard || []);
                setDailyResultSummary(loadedPayload.daily_result || null);
                setSelectedCategory(loadedPayload.selected_category || '');
                resetQuizProgress(loadedPayload);

                const selected = loadedPayload.selected_category || '';
                const newUrl = selected
                    ? `${modeUrl}?category=${encodeURIComponent(selected)}`
                    : modeUrl;
                window.history.replaceState({}, '', newUrl);
            } catch (error) {
                setErrorMessage('Unable to load quiz questions right now. Please try again.');
            } finally {
                setIsLoading(false);
            }
        }, [isLoading, modeUrls.daily, modeUrls.practice, modeUrls.timed, resetQuizProgress]);

        const handleModeChange = useCallback((mode) => {
            loadQuiz(mode, selectedCategory);
        }, [loadQuiz, selectedCategory]);

        const handleApplyFilter = useCallback(() => {
            loadQuiz(quizPayload.mode, selectedCategory);
        }, [loadQuiz, quizPayload.mode, selectedCategory]);

        const handleSelectAnswer = useCallback((value) => {
            if (!currentQuestion || quizCompleted || isLoading || (quizPayload.has_timer && !quizStarted)) {
                return;
            }

            if (isPracticeMode && practiceGrades[currentQuestionIndex]) {
                return;
            }

            setSelectedAnswer(value);
            setAnswersByQuestion((previous) => ({
                ...previous,
                [currentQuestionIndex]: value,
            }));

            if (!isPracticeMode) {
                return;
            }

            setPracticeGrades((previousGrades) => {
                if (previousGrades[currentQuestionIndex]) {
                    return previousGrades;
                }

                const isCorrect = value === currentQuestion.correct_answer;
                if (isCorrect) {
                    setScore((previousScore) => previousScore + 1);
                }

                return {
                    ...previousGrades,
                    [currentQuestionIndex]: {
                        selected: value,
                        correctAnswer: currentQuestion.correct_answer,
                        isCorrect,
                        explanation: currentQuestion.explanation || '',
                    },
                };
            });
        }, [currentQuestion, currentQuestionIndex, isLoading, isPracticeMode, practiceGrades, quizCompleted, quizPayload.has_timer, quizStarted]);

        const handleNextQuestion = useCallback(() => {
            if (!currentQuestion || !showNextButton || isLoading || (quizPayload.has_timer && !quizStarted)) {
                return;
            }

            if (currentQuestionIndex >= totalQuestions - 1) {
                completeQuiz(false);
                return;
            }

            const nextIndex = currentQuestionIndex + 1;
            setCurrentQuestionIndex(nextIndex);
            setSelectedAnswer(answersByQuestion[nextIndex] || '');
        }, [answersByQuestion, completeQuiz, currentQuestion, currentQuestionIndex, isLoading, quizPayload.has_timer, quizStarted, showNextButton, totalQuestions]);

        const handleStartTimedQuiz = useCallback(() => {
            if (isLoading || quizCompleted || !quizPayload.has_timer || !totalQuestions) {
                return;
            }

            setQuizStarted(true);
        }, [isLoading, quizCompleted, quizPayload.has_timer, totalQuestions]);

        const handleRestartQuiz = useCallback(() => {
            resetQuizProgress(quizPayload);
        }, [quizPayload, resetQuizProgress]);

        const showDailyLock = Boolean(quizPayload.daily_locked && dailyResultSummary);
        const showEmptyState = !isLoading && !quizCompleted && !showDailyLock && totalQuestions === 0;
        const showStartPrompt = !isLoading && !quizCompleted && !showDailyLock && Boolean(quizPayload.has_timer && !quizStarted && totalQuestions > 0);
        const showQuizCard = !isLoading && !quizCompleted && !showDailyLock && !showStartPrompt && totalQuestions > 0 && currentQuestion;
        const showCompletion = quizCompleted && completionSummary;
        const showRestartButton = Boolean(quizPayload.can_reset);
        const showInterfaceTimer = Boolean(quizPayload.has_timer && quizStarted && !quizCompleted && !showDailyLock && totalQuestions > 0);

        const quizProgressText = quizCompleted
            ? 'Completed'
            : (quizPayload.has_timer && !quizStarted && totalQuestions
                ? 'Ready to start'
                : (totalQuestions ? `Question ${Math.min(currentQuestionIndex + 1, totalQuestions)} of ${totalQuestions}` : 'No questions'));

        return h(window.React.Fragment, null, [
            h(LeaderboardSection, { entries: leaderboardEntries, key: 'leaderboard' }),
            h(StatsRow, { stats, key: 'stats' }),
            h(QuizModes, {
                modes: quizModes,
                currentMode: quizPayload.mode,
                onModeChange: handleModeChange,
                modeLabel: quizPayload.mode_label,
                description: quizPayload.description,
                features: quizPayload.features,
                categoryChoices,
                selectedCategory,
                onCategoryChange: setSelectedCategory,
                onApplyFilter: handleApplyFilter,
                isLoading,
                key: 'modes',
            }),
            h('div', { className: 'quiz-shell section-panel learn-quiz-shell', key: 'quiz-shell' }, [
                h('div', { className: 'd-flex justify-content-between align-items-center flex-wrap gap-2 mb-4', key: 'heading' }, [
                    h('div', { key: 'title-wrap' }, [
                        h('span', { className: 'section-label', key: 'title-label' }, 'Question Set'),
                        h('h2', { className: 'h4 mb-0', key: 'title' }, quizPayload.mode_label),
                    ]),
                    h('div', { className: 'd-flex align-items-center gap-2', key: 'badges' }, [
                        h('span', { className: 'section-chip', key: 'progress' }, quizProgressText),
                        h('span', { className: 'resource-badge mb-0', key: 'score' }, `Score ${score}`),
                        showInterfaceTimer
                            ? h(
                                'span',
                                {
                                    className: `resource-badge mb-0 ${timerWarning ? 'quiz-timer-warning' : ''}`,
                                    key: 'timer',
                                },
                                timerText
                            )
                            : null,
                    ]),
                ]),
                errorMessage
                    ? h('div', { className: 'quiz-result mb-4', key: 'error' }, errorMessage)
                    : null,
                isLoading
                    ? h('div', { className: 'quiz-result mb-0', key: 'loading' }, 'Loading quiz questions...')
                    : null,
                showDailyLock
                    ? h(DailyLockPanel, { summary: dailyResultSummary, key: 'daily-lock' })
                    : null,
                showEmptyState
                    ? h(
                        'div',
                        { className: 'quiz-result mb-0', key: 'empty' },
                        'No quiz questions are available for this mode and category yet. Add approved questions in admin to build this set.'
                    )
                    : null,
                showStartPrompt
                    ? h(TimedQuizStartPanel, {
                        durationSeconds: quizPayload.duration_seconds,
                        onStart: handleStartTimedQuiz,
                        isBusy: isLoading,
                        key: 'timed-start',
                    })
                    : null,
                showQuizCard
                    ? h('div', { className: 'learn-quiz-stage', key: 'stage' }, [
                        h(QuizCard, {
                            question: currentQuestion,
                            questionNumber: currentQuestionIndex + 1,
                            totalQuestions,
                            selectedAnswer,
                            onSelectAnswer: handleSelectAnswer,
                            isPracticeMode,
                            practiceGrade: currentPracticeGrade,
                            isBusy: isLoading,
                            showNextButton,
                            nextButtonLabel,
                            onNextQuestion: handleNextQuestion,
                        }),
                    ])
                    : null,
                showCompletion
                    ? h('div', { className: 'learn-quiz-stage', key: 'completion' }, [
                        h(QuizCompletionCard, {
                            summary: completionSummary,
                            message: completionMessage,
                            showRestart: showRestartButton,
                            onRestart: handleRestartQuiz,
                            isSavingDaily,
                        }),
                    ])
                    : null,
            ]),
        ]);
    }

    window.ReactDOM.createRoot(appElement).render(h(QuizApp));
})();
