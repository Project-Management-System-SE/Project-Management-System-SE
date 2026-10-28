from django import template


register = template.Library()


@register.filter
def accessible_widget(field):
    attrs = {}
    described_by = []

    existing_described_by = field.field.widget.attrs.get("aria-describedby")
    if existing_described_by:
        described_by.append(existing_described_by)

    if field.auto_id:
        if field.help_text:
            described_by.append(f"{field.auto_id}_help")
        if field.errors:
            attrs["aria-invalid"] = "true"
            described_by.append(f"{field.auto_id}_errors")

    if described_by:
        attrs["aria-describedby"] = " ".join(described_by)

    return field.as_widget(attrs=attrs)
