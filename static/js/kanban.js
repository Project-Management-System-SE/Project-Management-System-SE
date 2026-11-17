document.addEventListener("DOMContentLoaded", () => {
    const board = document.querySelector("[data-kanban-board]");
    if (!board) return;

    let draggedCard = null;
    const announcement = document.querySelector("[data-kanban-announcement]");

    board.querySelectorAll("[data-kanban-card][draggable='true']").forEach((card) => {
        card.addEventListener("dragstart", (event) => {
            draggedCard = card;
            card.classList.add("kanban-card-dragging");
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", card.dataset.taskId);
        });

        card.addEventListener("dragend", () => {
            card.classList.remove("kanban-card-dragging");
            board.querySelectorAll(".kanban-column-drop-target").forEach((column) => {
                column.classList.remove("kanban-column-drop-target");
            });
            draggedCard = null;
        });
    });

    board.querySelectorAll("[data-kanban-column]").forEach((column) => {
        column.addEventListener("dragover", (event) => {
            if (!draggedCard) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            column.classList.add("kanban-column-drop-target");
        });

        column.addEventListener("dragleave", (event) => {
            if (!column.contains(event.relatedTarget)) {
                column.classList.remove("kanban-column-drop-target");
            }
        });

        column.addEventListener("drop", (event) => {
            if (!draggedCard) return;
            event.preventDefault();
            column.classList.remove("kanban-column-drop-target");

            const moveForm = draggedCard.querySelector(".kanban-move-form");
            const statusSelect = moveForm?.elements.namedItem("status");
            const targetStatus = column.dataset.kanbanColumn;
            if (!statusSelect || !Array.from(statusSelect.options).some((option) => option.value === targetStatus)) {
                if (announcement) {
                    announcement.textContent = "That task cannot move to this workflow stage.";
                }
                return;
            }

            statusSelect.value = targetStatus;
            if (announcement) {
                announcement.textContent = `Moving task to ${column.querySelector("h2").textContent}.`;
            }
            moveForm.requestSubmit();
        });
    });
});
