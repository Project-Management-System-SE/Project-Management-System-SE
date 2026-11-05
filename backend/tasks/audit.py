from decimal import Decimal

from django.forms import BoundField

from .models import AuditLog, Task


def _audit_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "pk"):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_audit_value(item) for item in value]
    return value


def changes_from_form(form):
    if form is None:
        return {}
    changes = {}
    for field_name in form.changed_data:
        field = form[field_name]
        if isinstance(field, BoundField):
            changes[field_name] = {
                "from": _audit_value(form.initial.get(field_name)),
                "to": _audit_value(form.cleaned_data.get(field_name)),
            }
    return changes


def record_audit(actor, action, obj, changes=None):
    if isinstance(obj, Task):
        object_type = AuditLog.ObjectType.TASK
        object_name = obj.title
        project = obj.project
        task = obj
    else:
        object_type = AuditLog.ObjectType.PROJECT
        object_name = obj.name
        project = obj
        task = None
    authorized_user_ids = set(
        project.memberships.values_list("user_id", flat=True)
    )
    authorized_user_ids.add(project.owner_id)

    actor_name = (
        getattr(actor, "full_name", "")
        or getattr(actor, "username", "")
        or getattr(actor, "email", "")
    )
    action_label = AuditLog.Action(action).label.lower()
    description = f"{actor_name or 'Unknown actor'} {action_label} {object_type.lower()} '{object_name}'."
    if changes:
        changed_fields = ", ".join(changes)
        description += f" Changed: {changed_fields}."

    return AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        action=action,
        object_type=object_type,
        object_id=obj.pk,
        object_name=object_name,
        project_id_snapshot=project.pk,
        project=project,
        project_name=project.name,
        authorized_user_ids=sorted(authorized_user_ids),
        task=task,
        description=description,
        changes=changes or {},
    )
