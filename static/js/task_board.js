(() => {
    const board = document.querySelector("[data-task-board]");
    const feedback = document.querySelector("[data-task-board-feedback]");
    if (!board || !feedback) {
        return;
    }

    function showFeedback(message, isError = false) {
        feedback.textContent = message;
        feedback.hidden = false;
        feedback.classList.toggle("is-error", isError);
        feedback.classList.toggle("is-success", !isError);
        feedback.setAttribute("role", isError ? "alert" : "status");
    }

    function updateColumnCount(column) {
        if (!column) {
            return false;
        }
        const cards = column.querySelectorAll("[data-task-card]");
        const count = column.querySelector("[data-task-board-count]");
        const list = column.querySelector("[data-task-board-cards]");
        if (!count || !list) {
            return false;
        }
        count.textContent = cards.length;
        let emptyState = list.querySelector(".task-board-empty");
        if (cards.length === 0 && !emptyState) {
            emptyState = document.createElement("li");
            emptyState.className = "task-board-empty";
            emptyState.textContent = "No tasks in this status.";
            list.appendChild(emptyState);
        } else if (cards.length > 0 && emptyState) {
            emptyState.remove();
        }
        return true;
    }

    board.querySelectorAll("[data-task-status-form]").forEach((form) => {
        const card = form.closest("[data-task-card]");
        const statusSelect = form.querySelector("select[name='status']");
        const submitButton = form.querySelector("button[type='submit']");
        const sourceColumn = card && card.closest("[data-status-column]");
        if (!card || !statusSelect || !submitButton || !sourceColumn) {
            return;
        }

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (form.dataset.pending === "true") {
                return;
            }

            const originalStatus = card.dataset.taskStatus;
            const formData = new FormData(form);
            let serverConfirmed = false;
            form.dataset.pending = "true";
            submitButton.disabled = true;
            statusSelect.disabled = true;

            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    body: formData,
                    credentials: "same-origin",
                    headers: { Accept: "application/json" },
                });

                if (response.redirected) {
                    throw new Error("Your session may have expired. Sign in and try again.");
                }

                let result = {};
                if ((response.headers.get("content-type") || "").includes("application/json")) {
                    try {
                        result = await response.json();
                    } catch {
                        throw new Error("The server returned an invalid response. Please try again.");
                    }
                }

                if (!response.ok) {
                    const message = result.error || (
                        response.status === 403
                            ? "You do not have permission to change this task."
                            : response.status === 404
                                ? "This task is no longer available."
                                : "The server could not update the task. Please try again."
                    );
                    throw new Error(message);
                }
                if (result.success !== true || typeof result.status !== "string") {
                    throw new Error(result.error || "The task status was not updated.");
                }
                const hasValidStatus = Array.from(statusSelect.options).some(
                    (option) => option.value === result.status
                );
                if (!hasValidStatus) {
                    throw new Error(
                        "The server returned an invalid task status. Refresh the board and try again."
                    );
                }
                serverConfirmed = true;

                const destinationColumn = document.getElementById(
                    `task-status-${result.status}`
                );
                if (!destinationColumn) {
                    statusSelect.value = result.status;
                    card.dataset.taskStatus = result.status;
                    showFeedback(
                        "Task status was saved. Refresh the board to see its updated column."
                    );
                    return;
                }

                statusSelect.value = result.status;
                card.dataset.taskStatus = result.status;
                const statusFilter = document.querySelector(
                    ".search-filter-form select[name='status']"
                );
                const filteredOut = statusFilter
                    && statusFilter.value
                    && statusFilter.value !== result.status;
                if (filteredOut) {
                    card.remove();
                    updateColumnCount(sourceColumn);
                } else if (sourceColumn !== destinationColumn) {
                    const destinationList = destinationColumn.querySelector(
                        "[data-task-board-cards]"
                    );
                    if (!destinationList) {
                        showFeedback(
                            "Task status was saved. Refresh the board to see its updated column."
                        );
                        return;
                    }
                    destinationList.appendChild(card);
                    updateColumnCount(sourceColumn);
                    updateColumnCount(destinationColumn);
                }
                showFeedback(result.message || "Task status updated.");
            } catch (error) {
                if (!serverConfirmed) {
                    statusSelect.value = originalStatus;
                }
                showFeedback(
                    error instanceof Error
                        ? error.message
                        : "The task status could not be updated. Please try again.",
                    true
                );
            } finally {
                delete form.dataset.pending;
                submitButton.disabled = false;
                statusSelect.disabled = false;
            }
        });
    });
})();
