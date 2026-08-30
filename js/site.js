(function () {
    var THEME_KEY = "theme";
    var STYLES_KEY = "styles";
    var root = document.documentElement;
    var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
    var buttons = {};

    function read(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (e) {
            return null;
        }
    }

    function write(key, value) {
        try {
            window.localStorage.setItem(key, value);
        } catch (e) {
            return;
        }
    }

    var theme = read(THEME_KEY);
    if (theme !== "light" && theme !== "dark") {
        theme = null;
    }
    var stylesOn = read(STYLES_KEY) !== "off";

    function effectiveTheme() {
        if (theme) {
            return theme;
        }
        return darkQuery.matches ? "dark" : "light";
    }

    function applyTheme() {
        if (theme) {
            root.setAttribute("data-theme", theme);
        } else {
            root.removeAttribute("data-theme");
        }
    }

    function applyStyles() {
        var links = document.querySelectorAll("link[data-styling]");
        for (var i = 0; i < links.length; i++) {
            links[i].disabled = !stylesOn;
        }
        root.setAttribute("data-styles", stylesOn ? "on" : "off");
    }

    function syncButtons() {
        var active = stylesOn ? effectiveTheme() : "none";
        Object.keys(buttons).forEach(function (key) {
            buttons[key].setAttribute("aria-pressed", key === active ? "true" : "false");
        });
    }

    function select(value) {
        if (value === "none") {
            stylesOn = false;
        } else {
            stylesOn = true;
            theme = value;
            write(THEME_KEY, value);
            applyTheme();
        }
        write(STYLES_KEY, stylesOn ? "on" : "off");
        applyStyles();
        syncButtons();
    }

    function makeButton(value, icon, label) {
        var button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-pressed", "false");

        var glyph = document.createElement("i");
        glyph.className = "fas " + icon;
        glyph.setAttribute("aria-hidden", "true");

        var text = document.createElement("span");
        text.textContent = label;

        button.appendChild(glyph);
        button.appendChild(text);
        button.addEventListener("click", function () {
            select(value);
        });

        buttons[value] = button;
        return button;
    }

    function buildControls() {
        var host = document.getElementById("site-controls");
        if (!host) {
            return;
        }
        host.className = "site-controls";
        host.setAttribute("role", "group");
        host.setAttribute("aria-label", "Page appearance");
        host.appendChild(makeButton("light", "fa-sun", "Light"));
        host.appendChild(makeButton("dark", "fa-moon", "Dark"));
        host.appendChild(makeButton("none", "fa-ban", "None"));
        syncButtons();
    }

    applyTheme();
    applyStyles();

    if (darkQuery.addEventListener) {
        darkQuery.addEventListener("change", function () {
            if (!theme) {
                syncButtons();
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", buildControls);
    } else {
        buildControls();
    }
})();