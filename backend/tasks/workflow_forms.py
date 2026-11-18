from django import forms
from django.utils.text import slugify

from .models import Task, WorkflowTransition
from .workflow import STATUS_TRANSITIONS, workflow_states_for


class WorkflowConfigurationForm(forms.Form):
    states = forms.CharField(
        label="Workflow states",
        help_text="Enter one state per line, in the order shown on the board.",
        widget=forms.Textarea(attrs={"rows": 7}),
    )
    initial_state = forms.CharField(
        label="Initial state",
        help_text="New tasks start in this state.",
    )
    final_state = forms.CharField(
        label="Final state",
        help_text="Tasks in this state count as complete.",
    )
    transitions = forms.CharField(
        label="Allowed transitions",
        help_text="Enter one transition per line, for example: To Do -> In Progress.",
        widget=forms.Textarea(attrs={"rows": 8}),
    )

    def __init__(self, *args, project, **kwargs):
        self.project = project
        states = workflow_states_for(project)
        if states:
            state_names = [state.name for state in states]
            initial_name = next(
                (state.name for state in states if state.is_initial),
                state_names[0],
            )
            final_name = next(
                (state.name for state in states if state.is_final),
                state_names[-1],
            )
            transition_names = [
                f"{transition.from_state.name} -> {transition.to_state.name}"
                for transition in WorkflowTransition.objects.filter(
                    from_state__project=project
                ).select_related(
                    "from_state",
                    "to_state",
                )
            ]
        else:
            state_names = [label for _, label in Task.Status.choices]
            initial_name = dict(Task.Status.choices)[Task.Status.TODO]
            final_name = dict(Task.Status.choices)[Task.Status.DONE]
            labels_by_key = dict(Task.Status.choices)
            transition_names = [
                f"{labels_by_key[source]} -> {labels_by_key[target]}"
                for source, targets in STATUS_TRANSITIONS.items()
                for target in sorted(targets)
            ]

        initial = {
            "states": "\n".join(state_names),
            "initial_state": initial_name,
            "final_state": final_name,
            "transitions": "\n".join(transition_names),
        }
        super().__init__(*args, initial=initial, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        names = [
            name.strip()
            for name in cleaned_data.get("states", "").splitlines()
            if name.strip()
        ]
        if not 2 <= len(names) <= 20:
            self.add_error("states", "A workflow must contain between 2 and 20 states.")

        names_by_normalized = {}
        states = []
        canonical_keys = {
            label.casefold(): key for key, label in Task.Status.choices
        }
        keys = set()
        for name in names:
            normalized_name = name.casefold()
            if normalized_name in names_by_normalized:
                self.add_error("states", "Workflow state names must be unique.")
                continue
            names_by_normalized[normalized_name] = name

            key = canonical_keys.get(normalized_name)
            if key is None:
                key = slugify(name).replace("-", "_").upper()
            if not key or len(key) > 20:
                self.add_error(
                    "states",
                    f"'{name}' must produce a state key of 1 to 20 characters.",
                )
                continue
            if key in keys:
                self.add_error("states", "Workflow state names must produce unique keys.")
                continue
            keys.add(key)
            states.append({"key": key, "name": name})

        initial_name = cleaned_data.get("initial_state", "").strip()
        final_name = cleaned_data.get("final_state", "").strip()
        initial_state = names_by_normalized.get(initial_name.casefold())
        final_state = names_by_normalized.get(final_name.casefold())
        if initial_state is None:
            self.add_error("initial_state", "Choose a state from the workflow.")
        if final_state is None:
            self.add_error("final_state", "Choose a state from the workflow.")
        if initial_state and final_state and initial_state == final_state:
            self.add_error(
                "final_state",
                "The initial and final states must be different.",
            )

        states_by_name = {
            state["name"].casefold(): state["key"]
            for state in states
        }
        transitions = []
        seen_transitions = set()
        for line in cleaned_data.get("transitions", "").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.count("->") != 1:
                self.add_error(
                    "transitions",
                    f"'{line}' must use the format 'State -> State'.",
                )
                continue
            source_name, target_name = (
                part.strip().casefold() for part in line.split("->", 1)
            )
            source_key = states_by_name.get(source_name)
            target_key = states_by_name.get(target_name)
            if source_key is None or target_key is None:
                self.add_error(
                    "transitions",
                    f"Both states in '{line}' must exist in the workflow.",
                )
                continue
            if source_key == target_key:
                self.add_error("transitions", "A state cannot transition to itself.")
                continue
            if (source_key, target_key) in seen_transitions:
                self.add_error("transitions", "Transitions must be unique.")
                continue
            seen_transitions.add((source_key, target_key))
            transitions.append((source_key, target_key))

        if not transitions:
            self.add_error("transitions", "Add at least one allowed transition.")

        review_key = states_by_name.get("review")
        final_key = states_by_name.get(final_name.casefold())
        if review_key is None:
            self.add_error(
                "states",
                "A workflow must include a Review state before tasks can be completed.",
            )
        if review_key and final_key:
            final_sources = {
                source for source, target in transitions if target == final_key
            }
            if review_key not in final_sources:
                self.add_error(
                    "transitions",
                    "The final state must be reachable from Review.",
                )
            if final_sources - {review_key}:
                self.add_error(
                    "transitions",
                    "Tasks may enter the final state only from Review.",
                )

            if initial_state:
                initial_key = states_by_name.get(initial_state.casefold())
                outgoing = {}
                for source, target in transitions:
                    outgoing.setdefault(source, set()).add(target)
                reachable = {initial_key}
                pending = [initial_key]
                while pending:
                    current = pending.pop()
                    for target in outgoing.get(current, set()) - reachable:
                        reachable.add(target)
                        pending.append(target)
                if review_key not in reachable:
                    self.add_error(
                        "transitions",
                        "The Review state must be reachable from the initial state.",
                    )

        if states and not self.errors:
            state_keys = {state["key"] for state in states}
            used_states = self.project.tasks.values_list(
                "workflow_state__key",
                "status",
            )
            for workflow_key, legacy_status in used_states:
                used_key = workflow_key or legacy_status
                if used_key not in state_keys:
                    self.add_error(
                        "states",
                        "Move tasks out of a state before removing or renaming it.",
                    )
                    break

        if not self.errors:
            self.workflow_states = [
                {
                    **state,
                    "is_initial": state["name"].casefold()
                    == initial_state.casefold(),
                    "is_final": state["name"].casefold() == final_state.casefold(),
                }
                for state in states
            ]
            self.workflow_transitions = transitions
