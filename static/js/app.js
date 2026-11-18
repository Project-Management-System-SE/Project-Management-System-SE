/* Shared page behaviour: theme toggle, mobile navigation, help dialog and
 * confirmation dialogs for destructive actions (SRS 3.1). */
(() => {
    const root = document.documentElement;

    // Dark / light theme toggle, remembered per browser.
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
            root.setAttribute("data-theme", next);
            try {
                localStorage.setItem("pms-theme", next);
            } catch (error) {
                /* Storage can be unavailable (private mode); the toggle still works for this page. */
            }
        });
    });

    // Off-canvas sidebar on small screens.
    const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
    const backdrop = document.querySelector("[data-sidebar-close]");
    const setSidebar = (open) => {
        document.body.classList.toggle("sidebar-open", open);
        if (sidebarToggle) sidebarToggle.setAttribute("aria-expanded", String(open));
        if (backdrop) backdrop.hidden = !open;
    };
    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", () => {
            setSidebar(!document.body.classList.contains("sidebar-open"));
        });
    }
    if (backdrop) backdrop.addEventListener("click", () => setSidebar(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setSidebar(false);
    });

    // Help dialog.
    const helpDialog = document.querySelector("[data-help-dialog]");
    document.querySelectorAll("[data-help-open]").forEach((button) => {
        button.addEventListener("click", () => helpDialog && helpDialog.showModal());
    });

    // Confirmation dialog: any form with data-confirm="message" asks first.
    const confirmDialog = document.querySelector("[data-confirm-dialog]");
    const confirmMessage = confirmDialog && confirmDialog.querySelector("[data-confirm-message]");
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (form.dataset.confirmed === "true" || !confirmDialog) return;
            event.preventDefault();
            confirmMessage.textContent = form.dataset.confirm;
            confirmDialog.returnValue = "";
            confirmDialog.showModal();
            confirmDialog.addEventListener("close", function onClose() {
                confirmDialog.removeEventListener("close", onClose);
                if (confirmDialog.returnValue === "confirm") {
                    form.dataset.confirmed = "true";
                    form.requestSubmit();
                }
            });
        });
    });
})();
