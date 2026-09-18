
(() => {
    "use strict";

    const VALID_MODES =
        new Set([
            "system",
            "light",
            "dark",
        ]);

    const VALID_THEMES =
        new Set([
            "fusion",
            "nebula",
            "ember",
            "neutral",
        ]);

    const MODE_KEY =
        "hackdex.ui_mode";

    const THEME_KEY =
        "hackdex.ui_theme";


    function validMode(value) {
        return VALID_MODES.has(value)
            ? value
            : "system";
    }


    function validTheme(value) {
        const legacyThemes = {
            hybrid: "fusion",
            romm: "nebula",
            hackdex: "ember",
        };

        value =
            legacyThemes[value]
            || value;

        return VALID_THEMES.has(value)
            ? value
            : "fusion";
    }


    function applyAppearance(
        mode,
        theme,
        persist = true,
    ) {
        mode =
            validMode(mode);

        theme =
            validTheme(theme);

        document
            .documentElement
            .setAttribute(
                "data-mode",
                mode,
            );

        document
            .documentElement
            .setAttribute(
                "data-theme",
                theme,
            );

        if (persist) {
            try {
                localStorage.setItem(
                    MODE_KEY,
                    mode,
                );

                localStorage.setItem(
                    THEME_KEY,
                    theme,
                );

            } catch {
                // Storage can be disabled.
            }
        }

        window.dispatchEvent(
            new CustomEvent(
                "hackdexappearancechange",
                {
                    detail: {
                        mode,
                        theme,
                    },
                },
            )
        );
    }


    function cachedAppearance() {
        let mode =
            "system";

        let theme =
            "fusion";

        try {
            mode =
                localStorage.getItem(
                    MODE_KEY
                )
                || mode;

            theme =
                localStorage.getItem(
                    THEME_KEY
                )
                || theme;

        } catch {
            // Ignore storage failures.
        }

        return {
            mode:
                validMode(mode),

            theme:
                validTheme(theme),
        };
    }


    async function loadServerAppearance() {
        try {
            const response =
                await fetch(
                    "/api/settings",
                    {
                        cache:
                            "no-store",
                    }
                );

            if (!response.ok) {
                return;
            }

            const settings =
                await response.json();

            applyAppearance(
                settings.ui_mode,
                settings.ui_theme,
                true,
            );

        } catch {
            // Cached appearance remains active.
        }
    }


    const cached =
        cachedAppearance();

    applyAppearance(
        cached.mode,
        cached.theme,
        false,
    );



    function currentPage() {
        const path =
            window.location.pathname;

        if (
            path === "/"
            || path === ""
        ) {
            return "library";
        }

        if (
            path === "/review"
        ) {
            return "review";
        }

        if (
            path === "/library-health"
        ) {
            return "health";
        }

        if (
            path.startsWith(
                "/base-roms"
            )
        ) {
            return "base-roms";
        }

        if (
            path.startsWith(
                "/settings"
            )
        ) {
            return "settings";
        }

        return "library";
    }


    function pageTitle(page) {
        const titles = {
            library:
                "Library",

            "base-roms":
                "Base ROMs",

            review:
                "Needs Review",

            health:
                "Library Health",

            settings:
                "Settings",
        };

        return titles[page]
            || "HackDex Manager";
    }


    function navLink(
        href,
        icon,
        label,
        key,
        page,
    ) {
        const active =
            key === page
            ? " active"
            : "";

        return `
            <a
                class="hd-nav-link${active}"
                href="${href}"
            >
                <span
                    class="hd-nav-icon"
                    aria-hidden="true"
                >
                    ${icon}
                </span>

                <span>
                    ${label}
                </span>
            </a>
        `;
    }


    function shellMarkup(page) {
        return `
            <aside
                class="hd-sidebar"
                id="hd-sidebar"
            >
                <a
                    class="
                        hd-sidebar-brand
                        hd-sidebar-brand-link
                    "
                    href="/"
                    title="HackDex Manager Home"
                >

                    <div
                        class="hd-brand-mark"
                        aria-hidden="true"
                    >
                        <svg
                            class="hd-pokeball"
                            viewBox="0 0 64 64"
                            focusable="false"
                        >
                            <circle
                                class="pk-outer"
                                cx="32"
                                cy="32"
                                r="30"
                            />
                            <path
                                class="pk-top"
                                d="M2 32A30 30 0 0 1 62 32Z"
                            />
                            <path
                                class="pk-bottom"
                                d="M2 32A30 30 0 0 0 62 32Z"
                            />
                            <rect
                                class="pk-band"
                                x="2"
                                y="29"
                                width="60"
                                height="6"
                            />
                            <circle
                                class="pk-button-ring"
                                cx="32"
                                cy="32"
                                r="10"
                            />
                            <circle
                                class="pk-button-core"
                                cx="32"
                                cy="32"
                                r="5"
                            />
                        </svg>
                    </div>

                    <div class="hd-brand-name">
                        HackDex Manager
                    </div>

                </a>

                <nav class="hd-sidebar-nav">

                    <div class="hd-nav-label">
                        Library
                    </div>

                    ${navLink(
                        "/",
                        "⌂",
                        "Library",
                        "library",
                        page,
                    )}

                    ${navLink(
                        "/base-roms",
                        "◆",
                        "Base ROMs",
                        "base-roms",
                        page,
                    )}

                    ${navLink(
                        "/review",
                        "◫",
                        "Needs Review",
                        "review",
                        page,
                    )}

                    ${navLink(
                        "/library-health",
                        "♡",
                        "Library Health",
                        "health",
                        page,
                    )}

                    <div class="hd-nav-label">
                        Configuration
                    </div>

                    ${navLink(
                        "/settings",
                        "⚙",
                        "Settings",
                        "settings",
                        page,
                    )}


                </nav>

                <div class="hd-sidebar-footer">
                    <div class="hd-sidebar-footer-card">

                        <div class="hd-sidebar-footer-title">
                            HackDex Library Intelligence
                        </div>

                        <div class="hd-sidebar-footer-text">
                            Local ROM management
                            with live HackDex
                            catalog intelligence.
                        </div>

                    </div>
                </div>
            </aside>

            <div
                class="hd-sidebar-overlay"
                id="hd-sidebar-overlay"
            ></div>

            <div class="hd-topbar">

                <div class="hd-topbar-left">

                    <button
                        type="button"
                        class="
                            hd-icon-button
                            hd-mobile-menu
                        "
                        id="hd-mobile-menu"
                        title="Open navigation"
                    >
                        ☰
                    </button>

                    <div class="hd-page-title">
                        ${pageTitle(page)}
                    </div>

                    <div class="hd-global-search">
                        <span
                            class="hd-search-icon"
                            aria-hidden="true"
                        >
                            ⌕
                        </span>

                        <input
                            type="search"
                            id="hd-global-search"
                            placeholder="Search hacks..."
                            autocomplete="off"
                        >

                        <span class="hd-search-hint">
                            /
                        </span>
                    </div>

                </div>

                <div class="hd-topbar-actions">

                    <span
                        class="hd-shell-version"
                        id="hd-shell-version"
                    >
                        v…
                    </span>

                    <button
                        type="button"
                        class="hd-icon-button"
                        id="hd-mode-toggle"
                        title="Toggle light/dark mode"
                    >
                        ◐
                    </button>

                </div>

            </div>
        `;
    }


    async function loadShellVersion() {
        const element =
            document.getElementById(
                "hd-shell-version"
            );

        if (!element) {
            return;
        }

        try {
            const response =
                await fetch(
                    "/health",
                    {
                        cache:
                            "no-store",
                    }
                );

            const data =
                await response.json();

            const version =
                String(
                    data.version || ""
                );

            element.textContent =
                version.startsWith("v")
                ? version
                : "v" + version;

        } catch {
            element.textContent =
                "v?";
        }
    }


    function wireLibrarySearch() {
        const globalInput =
            document.getElementById(
                "hd-global-search"
            );

        if (!globalInput) {
            return;
        }

        const page =
            currentPage();

        const libraryInput =
            document.getElementById(
                "search"
            );

        if (
            page === "library"
            && libraryInput
        ) {
            globalInput.value =
                libraryInput.value || "";

            /*
             * The original Library search remains
             * functional but is visually redundant.
             */
            const originalControls =
                libraryInput.closest(
                    ".controls"
                );

            if (originalControls) {
                libraryInput.style.display =
                    "none";
            }

            globalInput.addEventListener(
                "input",
                () => {
                    libraryInput.value =
                        globalInput.value;

                    libraryInput.dispatchEvent(
                        new Event(
                            "input",
                            {
                                bubbles: true,
                            }
                        )
                    );
                }
            );

        } else {
            globalInput.addEventListener(
                "keydown",
                event => {
                    if (
                        event.key !== "Enter"
                    ) {
                        return;
                    }

                    const query =
                        globalInput
                            .value
                            .trim();

                    if (!query) {
                        window.location.href =
                            "/";
                        return;
                    }

                    window.location.href =
                        "/?q="
                        + encodeURIComponent(
                            query
                        );
                }
            );
        }
    }


    function applyQuerySearch() {
        if (
            currentPage()
            !== "library"
        ) {
            return;
        }

        const params =
            new URLSearchParams(
                window.location.search
            );

        const query =
            params.get("q");

        if (!query) {
            return;
        }

        const input =
            document.getElementById(
                "hd-global-search"
            );

        if (!input) {
            return;
        }

        input.value =
            query;

        input.dispatchEvent(
            new Event(
                "input",
                {
                    bubbles: true,
                }
            )
        );
    }


    function wireShellActions() {
        const menu =
            document.getElementById(
                "hd-mobile-menu"
            );

        const overlay =
            document.getElementById(
                "hd-sidebar-overlay"
            );

        if (menu) {
            menu.addEventListener(
                "click",
                () => {
                    document.body
                        .classList
                        .toggle(
                            "hd-sidebar-open"
                        );
                }
            );
        }

        if (overlay) {
            overlay.addEventListener(
                "click",
                () => {
                    document.body
                        .classList
                        .remove(
                            "hd-sidebar-open"
                        );
                }
            );
        }

        const modeButton =
            document.getElementById(
                "hd-mode-toggle"
            );

        if (modeButton) {
            modeButton.addEventListener(
                "click",
                async () => {
                    const root =
                        document.documentElement;

                    const currentMode =
                        root.getAttribute(
                            "data-mode"
                        )
                        || "system";

                    let effective =
                        currentMode;

                    if (
                        effective === "system"
                    ) {
                        effective =
                            window.matchMedia(
                                "(prefers-color-scheme: dark)"
                            ).matches
                            ? "dark"
                            : "light";
                    }

                    const next =
                        effective === "dark"
                        ? "light"
                        : "dark";

                    const theme =
                        root.getAttribute(
                            "data-theme"
                        )
                        || "fusion";

                    applyAppearance(
                        next,
                        theme,
                        true,
                    );

                    try {
                        await fetch(
                            "/api/settings",
                            {
                                method:
                                    "PUT",

                                headers: {
                                    "Content-Type":
                                        "application/json",
                                },

                                body:
                                    JSON.stringify({
                                        ui_mode:
                                            next,

                                        ui_theme:
                                            theme,
                                    }),
                            }
                        );

                    } catch {
                        // Local appearance remains.
                    }
                }
            );
        }

        document.addEventListener(
            "keydown",
            event => {
                if (
                    event.key !== "/"
                    || event.ctrlKey
                    || event.metaKey
                    || event.altKey
                ) {
                    return;
                }

                const target =
                    event.target;

                if (
                    target
                    && (
                        target.tagName
                        === "INPUT"
                        || target.tagName
                        === "TEXTAREA"
                        || target.tagName
                        === "SELECT"
                    )
                ) {
                    return;
                }

                const search =
                    document.getElementById(
                        "hd-global-search"
                    );

                if (search) {
                    event.preventDefault();
                    search.focus();
                }
            }
        );
    }


    function createShell() {
        if (
            document.getElementById(
                "hd-sidebar"
            )
        ) {
            return;
        }

        const page =
            currentPage();

        document.body
            .insertAdjacentHTML(
                "afterbegin",
                shellMarkup(page),
            );

        document.body
            .classList
            .add(
                "hd-shell-active"
            );

        wireLibrarySearch();
        wireShellActions();
        loadShellVersion();

        window.setTimeout(
            applyQuerySearch,
            0,
        );
    }



    window.HackDexUI = {
        applyAppearance,
        loadServerAppearance,
        validMode,
        validTheme,
        createShell,
    };


    if (
        document.readyState
        === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            () => {
                createShell();
                loadServerAppearance();
            },
            {
                once: true,
            }
        );

    } else {
        createShell();
        loadServerAppearance();
    }
})();


/* ============================================================
   v0.3.59
   Enhanced Appearance settings UI
   ============================================================ */

(function () {
    "use strict";

    const MODES = [
        {
            value: "system",
            label: "System",
            description: "Follow your device preference.",
            icon: "▣",
        },
        {
            value: "light",
            label: "Light",
            description: "Always use the light interface.",
            icon: "☀",
        },
        {
            value: "dark",
            label: "Dark",
            description: "Always use the dark interface.",
            icon: "◐",
        },
    ];

    const THEMES = [
        {
            value: "fusion",
            label: "Fusion",
            description: "Balanced blue and teal.",
            colors: [
                "#6293ec",
                "#2db29b",
                "#e0a142",
                "#1b232e",
            ],
        },
        {
            value: "nebula",
            label: "Nebula",
            description: "Indigo, purple and electric blue.",
            colors: [
                "#667cff",
                "#7959df",
                "#35a4f4",
                "#171d32",
            ],
        },
        {
            value: "ember",
            label: "Ember",
            description: "Crimson, charcoal and warm accents.",
            colors: [
                "#e64d70",
                "#b73554",
                "#e59542",
                "#1b1519",
            ],
        },
        {
            value: "neutral",
            label: "Neutral",
            description: "Quiet slate and neutral tones.",
            colors: [
                "#8ba0b5",
                "#74889b",
                "#b49a73",
                "#20262d",
            ],
        },
    ];

    function fireChange(element) {
        element.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles: true,
                }
            )
        );

        if (
            typeof window.previewAppearance
            === "function"
        ) {
            window.previewAppearance();
        }
    }

    function createModeCard(item, select) {
        const button =
            document.createElement("button");

        button.type = "button";
        button.className =
            "hd-appearance-option hd-mode-option";

        button.dataset.value =
            item.value;

        button.innerHTML = `
            <span class="hd-option-radio"></span>

            <span class="hd-mode-icon">
                ${item.icon}
            </span>

            <span class="hd-option-copy">
                <strong>
                    ${item.label}
                </strong>

                <small>
                    ${item.description}
                </small>
            </span>
        `;

        button.addEventListener(
            "click",
            function () {
                select.value =
                    item.value;

                fireChange(select);
                syncCards();
            }
        );

        return button;
    }

    function createThemeCard(item, select) {
        const button =
            document.createElement("button");

        button.type = "button";
        button.className =
            "hd-appearance-option hd-theme-option";

        button.dataset.value =
            item.value;

        const swatches =
            item.colors
                .map(
                    color => (
                        `<i style="background:${color}"></i>`
                    )
                )
                .join("");

        button.innerHTML = `
            <span class="hd-option-radio"></span>

            <span class="hd-theme-swatches">
                ${swatches}
            </span>

            <span class="hd-option-copy">
                <strong>
                    ${item.label}
                </strong>

                <small>
                    ${item.description}
                </small>
            </span>
        `;

        button.addEventListener(
            "click",
            function () {
                select.value =
                    item.value;

                fireChange(select);
                syncCards();
                renderMiniPreview();
            }
        );

        return button;
    }

    function syncCards() {
        const mode =
            document.querySelector(
                "#ui-mode"
            );

        const theme =
            document.querySelector(
                "#ui-theme"
            );

        if (!mode || !theme) {
            return;
        }

        document
            .querySelectorAll(
                ".hd-mode-option"
            )
            .forEach(
                card => {
                    card.classList.toggle(
                        "is-selected",
                        card.dataset.value
                            === mode.value
                    );
                }
            );

        document
            .querySelectorAll(
                ".hd-theme-option"
            )
            .forEach(
                card => {
                    card.classList.toggle(
                        "is-selected",
                        card.dataset.value
                            === theme.value
                    );
                }
            );
    }

    function renderMiniPreview() {
        const host =
            document.querySelector(
                "#hd-live-theme-preview"
            );

        const mode =
            document.querySelector(
                "#ui-mode"
            );

        const theme =
            document.querySelector(
                "#ui-theme"
            );

        if (
            !host
            || !mode
            || !theme
        ) {
            return;
        }

        host.dataset.previewMode =
            mode.value;

        host.dataset.previewTheme =
            theme.value;

        const themeInfo =
            THEMES.find(
                item =>
                    item.value
                    === theme.value
            ) || THEMES[0];

        host.querySelector(
            ".hd-preview-theme-name"
        ).textContent =
            themeInfo.label;
    }

    function buildAppearanceEnhancement() {
        if (
            !location.pathname.startsWith(
                "/settings/appearance"
            )
        ) {
            return;
        }

        const modeSelect =
            document.querySelector(
                "#ui-mode"
            );

        const themeSelect =
            document.querySelector(
                "#ui-theme"
            );

        if (
            !modeSelect
            || !themeSelect
            || document.querySelector(
                ".hd-appearance-enhanced"
            )
        ) {
            return;
        }

        const modeWrapper =
            modeSelect.closest(
                ".setting-field, .field, div"
            );

        const themeWrapper =
            themeSelect.closest(
                ".setting-field, .field, div"
            );

        const root =
            document.createElement("section");

        root.className =
            "hd-appearance-enhanced";

        root.innerHTML = `
            <div class="hd-appearance-panel">

                <div class="hd-appearance-section">
                    <div class="hd-appearance-section-head">
                        <div>
                            <span class="hd-kicker">
                                DISPLAY
                            </span>

                            <h3>
                                Display Mode
                            </h3>

                            <p>
                                Choose how HackDex Manager
                                follows your display preference.
                            </p>
                        </div>
                    </div>

                    <div
                        id="hd-mode-options"
                        class="hd-option-grid hd-mode-grid"
                    ></div>
                </div>

                <div class="hd-appearance-section">
                    <div class="hd-appearance-section-head">
                        <div>
                            <span class="hd-kicker">
                                COLOR
                            </span>

                            <h3>
                                Color Theme
                            </h3>

                            <p>
                                Choose the personality of the
                                interface independently from
                                light or dark mode.
                            </p>
                        </div>
                    </div>

                    <div
                        id="hd-theme-options"
                        class="hd-option-grid hd-theme-grid"
                    ></div>
                </div>

                <div class="hd-appearance-section">
                    <div class="hd-appearance-section-head">
                        <div>
                            <span class="hd-kicker">
                                PREVIEW
                            </span>

                            <h3>
                                Live Preview
                            </h3>

                            <p>
                                A miniature preview of the
                                selected display mode and theme.
                            </p>
                        </div>

                        <span class="hd-preview-theme-name">
                        </span>
                    </div>

                    <div
                        id="hd-live-theme-preview"
                        class="hd-live-theme-preview"
                    >
                        <div class="hd-mini-sidebar">
                            <div class="hd-mini-brand">
                                HD
                            </div>

                            <div
                                class="hd-mini-nav active"
                            >
                                Library
                            </div>

                            <div class="hd-mini-nav">
                                Needs Review
                            </div>

                            <div class="hd-mini-nav">
                                Library Health
                            </div>
                        </div>

                        <div class="hd-mini-app">
                            <div class="hd-mini-topbar">
                                <div class="hd-mini-search">
                                    Search hacks...
                                </div>
                            </div>

                            <div class="hd-mini-content">
                                <div class="hd-mini-hero">
                                    <small>
                                        ROMHACK LIBRARY
                                    </small>

                                    <strong>
                                        Welcome to
                                        HackDex Manager
                                    </strong>

                                    <span>
                                        Manage, verify,
                                        update and discover.
                                    </span>
                                </div>

                                <div class="hd-mini-stats">
                                    <div>
                                        <b>318</b>
                                        <span>Catalog</span>
                                    </div>

                                    <div>
                                        <b>73</b>
                                        <span>Owned</span>
                                    </div>

                                    <div>
                                        <b>12</b>
                                        <span>Updates</span>
                                    </div>
                                </div>

                                <div class="hd-mini-panels">
                                    <div>
                                        <b>Update Queue</b>

                                        <span></span>
                                        <span></span>
                                        <span></span>
                                    </div>

                                    <div>
                                        <b>Library Health</b>

                                        <span></span>
                                        <span></span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

            </div>
        `;

        const appearanceHeading =
            Array.from(
                document.querySelectorAll(
                    "h1, h2"
                )
            ).find(
                el =>
                    el.textContent.trim()
                    === "Appearance"
            );

        const candidateContainer =
            appearanceHeading
                ? appearanceHeading.parentElement
                : document.querySelector("main");

        if (!candidateContainer) {
            return;
        }

        const originalCard =
            modeSelect.closest(
                ".settings-card"
            )
            || modeSelect.parentElement
                ?.parentElement
                ?.parentElement;

        if (originalCard) {
            originalCard.classList.add(
                "hd-original-appearance-fields"
            );

            originalCard.insertAdjacentElement(
                "afterend",
                root
            );
        } else {
            candidateContainer.appendChild(
                root
            );
        }

        const modeGrid =
            root.querySelector(
                "#hd-mode-options"
            );

        MODES.forEach(
            item => {
                modeGrid.appendChild(
                    createModeCard(
                        item,
                        modeSelect
                    )
                );
            }
        );

        const themeGrid =
            root.querySelector(
                "#hd-theme-options"
            );

        THEMES.forEach(
            item => {
                themeGrid.appendChild(
                    createThemeCard(
                        item,
                        themeSelect
                    )
                );
            }
        );

        modeSelect.addEventListener(
            "change",
            function () {
                syncCards();
                renderMiniPreview();
            }
        );

        themeSelect.addEventListener(
            "change",
            function () {
                syncCards();
                renderMiniPreview();
            }
        );

        document.body.classList.add(
            "hd-appearance-ui-ready"
        );

        syncCards();
        renderMiniPreview();
    }

    /*
     * The shared UI script may load after DOMContentLoaded.
     * Initialize immediately when the DOM is already ready.
     */
    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            buildAppearanceEnhancement
        );
    } else {
        buildAppearanceEnhancement();
    }
})();








/* ============================================================
   v0.3.68
   Needs Review comparison layout enhancement
   ============================================================ */

(function () {
    "use strict";

    function enhanceActions(actions) {
        if (
            !actions
            || actions.dataset.hdEnhanced === "true"
        ) {
            return;
        }

        const approve =
            actions.querySelector(".approve");

        const reject =
            actions.querySelector(".reject");

        const assign =
            actions.querySelector(".assign");

        const select =
            actions.querySelector(".hack-select");

        if (
            approve
            || reject
        ) {
            const primary =
                document.createElement("div");

            primary.className =
                "hd-review-primary-actions";

            if (approve) {
                primary.appendChild(approve);
            }

            if (reject) {
                primary.appendChild(reject);
            }

            actions.appendChild(primary);
        }

        if (
            select
            || assign
        ) {
            const manual =
                document.createElement("div");

            manual.className =
                "hd-review-manual-actions";

            const label =
                document.createElement("span");

            label.className =
                "hd-review-manual-label";

            label.textContent =
                "Assign another match";

            manual.appendChild(label);

            if (select) {
                manual.appendChild(select);
            }

            if (assign) {
                manual.appendChild(assign);
            }

            actions.appendChild(manual);
        }

        actions.dataset.hdEnhanced =
            "true";
    }


    function enhanceTitleCard(card) {
        if (
            !card
            || card.dataset.hdCompareEnhanced
                === "true"
        ) {
            return;
        }

        const localTitle =
            card.querySelector(".local-title");

        const arrow =
            card.querySelector(".arrow");

        const suggested =
            card.querySelector(".suggested");

        if (
            !localTitle
            || !arrow
            || !suggested
        ) {
            return;
        }

        /*
         * The second direct child is the existing content
         * container in the current review-card renderer.
         */
        const content =
            Array.from(card.children)
                .find(
                    child =>
                        child !== card.querySelector(
                            ".art, .art-placeholder"
                        )
                );

        if (!content) {
            return;
        }

        const actions =
            content.querySelector(".actions");

        const score =
            content.querySelector(".score");

        const children =
            Array.from(content.children);

        const localIndex =
            children.indexOf(localTitle);

        const arrowIndex =
            children.indexOf(arrow);

        const suggestedIndex =
            children.indexOf(suggested);

        if (
            localIndex === -1
            || arrowIndex === -1
            || suggestedIndex === -1
        ) {
            return;
        }

        const compare =
            document.createElement("div");

        compare.className =
            "hd-review-compare";


        const localPanel =
            document.createElement("section");

        localPanel.className =
            "hd-review-side hd-review-local";


        const suggestedPanel =
            document.createElement("section");

        suggestedPanel.className =
            "hd-review-side hd-review-suggested";


        const localLabel =
            document.createElement("div");

        localLabel.className =
            "hd-review-side-label";

        localLabel.textContent =
            "Local ROM";


        const suggestedLabel =
            document.createElement("div");

        suggestedLabel.className =
            "hd-review-side-label";

        suggestedLabel.textContent =
            "Suggested HackDex Match";


        localPanel.appendChild(
            localLabel
        );

        suggestedPanel.appendChild(
            suggestedLabel
        );


        /*
         * Move everything from local-title up to the
         * old arrow into the Local ROM side.
         */
        children
            .slice(
                localIndex,
                arrowIndex
            )
            .forEach(
                node => {
                    if (
                        node !== score
                        && node !== actions
                    ) {
                        localPanel.appendChild(
                            node
                        );
                    }
                }
            );


        /*
         * Match confidence belongs with the proposed
         * HackDex candidate.
         */
        if (score) {
            score.classList.add(
                "hd-review-confidence"
            );

            suggestedPanel.appendChild(
                score
            );
        }


        /*
         * Move the candidate and its following metadata
         * into the suggestion side until the action area.
         */
        const suggestedEnd =
            actions
                ? children.indexOf(actions)
                : children.length;

        children
            .slice(
                suggestedIndex,
                suggestedEnd === -1
                    ? children.length
                    : suggestedEnd
            )
            .forEach(
                node => {
                    if (
                        node !== score
                        && node !== actions
                    ) {
                        suggestedPanel.appendChild(
                            node
                        );
                    }
                }
            );


        /*
         * The old arrow is redundant once we have clearly
         * labeled comparison columns.
         */
        arrow.remove();


        compare.appendChild(
            localPanel
        );

        compare.appendChild(
            suggestedPanel
        );


        if (actions) {
            content.insertBefore(
                compare,
                actions
            );

            enhanceActions(
                actions
            );
        } else {
            content.appendChild(
                compare
            );
        }

        card.dataset.hdCompareEnhanced =
            "true";
    }


    function enhanceReviewCards() {
        if (
            !location.pathname.startsWith(
                "/review"
            )
        ) {
            return;
        }

        document
            .querySelectorAll(
                "#title-items .review-card"
            )
            .forEach(
                enhanceTitleCard
            );
    }


    function initializeReviewEnhancement() {
        if (
            !location.pathname.startsWith(
                "/review"
            )
        ) {
            return;
        }

        enhanceReviewCards();

        [
            document.querySelector(
                "#title-items"
            ),
            document.querySelector(
                "#version-items"
            ),
        ]
            .filter(Boolean)
            .forEach(
                host => {
                    const observer =
                        new MutationObserver(
                            enhanceReviewCards
                        );

                    observer.observe(
                        host,
                        {
                            childList: true,
                            subtree: true,
                        }
                    );
                }
            );
    }


    if (
        document.readyState === "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initializeReviewEnhancement
        );
    } else {
        initializeReviewEnhancement();
    }

})();
